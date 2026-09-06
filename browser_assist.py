"""Lightpanda/CDP browser workflow helpers.

Account credentials are supplied per workflow and are never written to the repo.
CAPTCHA, OTP, verification, and anti-bot controls remain manual.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any

import requests
from websocket import WebSocketBadStatusException, create_connection

CDP_URL = os.getenv("CDP_URL", "http://127.0.0.1:9222")
SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _raise_for_status(response: requests.Response, operation: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip().replace("\n", " ")[:300]
        raise requests.HTTPError(
            f"{operation}: HTTP {response.status_code} {response.reason}; {detail}",
            response=response,
        ) from exc


def cdp_version() -> dict:
    response = requests.get(f"{CDP_URL}/json/version", timeout=5)
    _raise_for_status(response, "CDP /json/version")
    return response.json()


def _browser_ws_url() -> str:
    """Return the documented Lightpanda local browser CDP endpoint."""
    cdp_url = CDP_URL.rstrip("/")
    if cdp_url.startswith("https://"):
        return cdp_url.replace("https://", "wss://", 1)
    if cdp_url.startswith("http://"):
        return cdp_url.replace("http://", "ws://", 1)
    raise RuntimeError(f"Unsupported CDP_URL: {CDP_URL}")


def _create_browser_connection():
    """Open a direct Lightpanda websocket without proxy or Origin interference."""
    return create_connection(
        _browser_ws_url(),
        timeout=20,
        http_proxy_host=None,
        http_proxy_port=None,
        http_no_proxy=["127.0.0.1", "localhost"],
        suppress_origin=True,
    )


def open_url(url: str) -> dict:
    """Create, prepare, then navigate a Lightpanda page through browser-level CDP."""
    last_error: Exception | None = None
    for attempt in range(3):
        ws = None
        try:
            cdp_version()
            browser_ws_url = _browser_ws_url()
            ws = _create_browser_connection()

            # Start from a blank target so Page/Runtime/Network are enabled before
            # Instagram navigation begins. This gives the browser a clean load cycle.
            created = cdp_call(ws, "Target.createTarget", {"url": "about:blank"}, request_id=1)
            if created.get("error"):
                raise RuntimeError(f"CDP Target.createTarget failed: {created['error']}")
            target_id = created.get("result", {}).get("targetId")
            if not target_id:
                raise RuntimeError("CDP Target.createTarget returned no targetId")

            attached = cdp_call(
                ws,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
                request_id=2,
            )
            if attached.get("error"):
                raise RuntimeError(f"CDP Target.attachToTarget failed: {attached['error']}")
            session_id = attached.get("result", {}).get("sessionId")
            if not session_id:
                raise RuntimeError("CDP Target.attachToTarget returned no sessionId")

            tab = {
                "id": target_id,
                "targetId": target_id,
                "sessionId": session_id,
                "type": "page",
                "url": url,
                "browserWebSocketDebuggerUrl": browser_ws_url,
                "_ws": ws,
            }
            _prepare_page(tab)

            navigated = cdp_call(
                ws,
                "Page.navigate",
                {"url": url},
                request_id=3,
                session_id=session_id,
            )
            if navigated.get("error"):
                raise RuntimeError(f"CDP Page.navigate failed: {navigated['error']}")
            time.sleep(5)
            return tab
        except WebSocketBadStatusException as exc:
            status = getattr(exc, "status_code", None)
            headers = getattr(exc, "resp_headers", None)
            detail = f" status={status}" if status is not None else ""
            if headers:
                detail += f" headers={dict(headers)}"
            last_error = RuntimeError(f"Lightpanda CDP websocket handshake failed.{detail} {exc}")
            logging.warning("Open tab attempt %d/3 failed: %s", attempt + 1, last_error)
            if attempt < 2:
                time.sleep(1)
        except (requests.RequestException, OSError, ValueError, RuntimeError, TimeoutError) as exc:
            last_error = exc
            logging.warning("Open tab attempt %d/3 failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(1)
        finally:
            if ws is not None and last_error is not None:
                try:
                    ws.close()
                except Exception:
                    pass
    assert last_error is not None
    raise last_error


def open_signup() -> dict:
    return open_url(SIGNUP_URL)


def cdp_call(
    ws,
    method: str,
    params: dict | None = None,
    request_id: int = 1,
    session_id: str | None = None,
) -> dict:
    message = {"id": request_id, "method": method, "params": params or {}}
    if session_id:
        message["sessionId"] = session_id
    ws.send(json.dumps(message))
    deadline = time.time() + 15
    while time.time() < deadline:
        incoming = json.loads(ws.recv())
        if incoming.get("id") == request_id:
            return incoming
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def _evaluate(tab: dict, expression: str) -> Any:
    ws = tab.get("_ws")
    session_id = tab.get("sessionId")
    if ws is None or not session_id:
        raise RuntimeError("CDP tab has no live browser websocket/session")
    result = cdp_call(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        session_id=session_id,
    )
    if result.get("error"):
        raise RuntimeError(f"CDP Runtime.evaluate failed: {result['error']}")
    return result.get("result", {}).get("result", {}).get("value")


def _prepare_page(tab: dict) -> None:
    """Enable the page/runtime/network domains before real navigation."""
    ws = tab.get("_ws")
    session_id = tab.get("sessionId")
    if ws is None or not session_id:
        raise RuntimeError("Cannot prepare page without a live CDP session")
    for method in ("Page.enable", "Runtime.enable", "Network.enable"):
        result = cdp_call(ws, method, {}, session_id=session_id)
        if result.get("error"):
            raise RuntimeError(f"CDP {method} failed: {result['error']}")


def _wait_for_username_field(tab: dict, attempts: int = 20, delay: float = 0.5) -> bool:
    """Do not proceed until the real signup username input exists in the page DOM."""
    for _ in range(attempts):
        found = _evaluate(
            tab,
            "Boolean(document.querySelector('input[name=\"username\"]') || document.querySelector('input[autocomplete=\"username\"]'))",
        )
        if found:
            return True
        time.sleep(delay)
    return False


def close_tab(tab: dict) -> None:
    ws = tab.get("_ws")
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
        tab["_ws"] = None


def _username_available(tab: dict, username: str) -> bool:
    """Confirm availability only through the normal visible signup UI.

    No private/internal Instagram endpoint is queried. Absence of an error is
    never treated as proof of availability; the flow advances only when the
    UI explicitly reports availability.
    """
    expression = """
    (candidate) => {
      const el = document.querySelector('input[name="username"]') || document.querySelector('input[autocomplete="username"]');
      if (!el) return {state:'missing'};
      el.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(el, candidate);
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
      el.dispatchEvent(new Event('blur', {bubbles:true}));
      return {state:'entered', value:el.value || ''};
    }
    """
    result = _evaluate(tab, f"({expression})({json.dumps(username)})")
    if not result or result.get("state") != "entered" or result.get("value") != username:
        return False

    unavailable_re = re.compile(
        r"username\s+(?:is\s+)?(?:not\s+available|unavailable)|"
        r"username\s+(?:is\s+)?already\s+(?:taken|in use)|"
        r"this username is not available|"
        r"please try another username|"
        r"username .*?(?:taken|in use)",
        re.I,
    )
    available_re = re.compile(r"username\s+(?:is\s+)?available", re.I)

    for _ in range(12):
        state = _evaluate(
            tab,
            """
            (() => {
              const el = document.querySelector('input[name="username"]') || document.querySelector('input[autocomplete="username"]');
              const described = el?.getAttribute('aria-describedby') || '';
              const describedText = described
                .split(/\\s+/)
                .map(id => document.getElementById(id)?.innerText || document.getElementById(id)?.textContent || '')
                .join(' ');
              const container = el?.closest('form') || el?.parentElement || document.body;
              const alerts = [...document.querySelectorAll('[role="alert"], [aria-live="polite"], [aria-live="assertive"]')]
                .map(x => x.innerText || x.textContent || '').join(' ');
              const text = [container?.innerText || '', describedText, alerts].join(' ').slice(0, 5000);
              return {
                value: el?.value || '',
                invalid: el?.getAttribute('aria-invalid') || '',
                text
              };
            })()
            """,
        ) or {}
        if state.get("value") != username:
            return False
        text = str(state.get("text", ""))
        invalid = str(state.get("invalid", "")).lower()
        if unavailable_re.search(text) or invalid == "true":
            logging.info("Username unavailable: %s", username)
            return False
        if available_re.search(text):
            logging.info("Username confirmed available: %s", username)
            return True
        time.sleep(0.75)

    logging.warning("Username availability was not explicitly confirmed by the normal signup UI: %s", username)
    return False


def _pick_available_username(tab: dict, candidates: list[str]) -> str | None:
    if not _wait_for_username_field(tab):
        logging.error("Signup username field never became available; refusing to continue.")
        return None

    seen: set[str] = set()
    for candidate in candidates:
        candidate = str(candidate).strip()
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        logging.info("Checking username before any other signup field: %s", candidate)
        if _username_available(tab, candidate):
            return candidate
        logging.info("Rejected username candidate; trying next: %s", candidate)
    return None


def fill_fields(tab: dict, credentials: dict[str, str] | None = None, identity: dict[str, Any] | None = None) -> bool:
    credentials = credentials or {}
    email = credentials.get("email") or os.getenv("IG_EMAIL")
    password = credentials.get("password") or os.getenv("IG_PASSWORD")
    username = credentials.get("username")
    full_name = credentials.get("full_name", "")
    dob = (identity or {}).get("date_of_birth") or credentials.get("date_of_birth")

    candidates: list[str] = []
    if identity:
        candidates.extend(str(x) for x in (identity.get("usernames") or []) if x)
    if username:
        candidates.append(str(username))

    if identity:
        full_name = full_name or ((identity.get("display_names") or [None])[0] or "")

    if not email or not password or not candidates:
        logging.error("Per-account email, password and at least one username candidate are required.")
        return False

    # Hard gate: username availability is the FIRST signup operation.
    selected_username = _pick_available_username(tab, candidates[:5])
    if not selected_username:
        logging.error("No username candidate was explicitly confirmed available; signup will not be initiated or populated.")
        return False
    username = selected_username
    logging.info("Username gate passed; selected available username: %s", username)

    expression = """
    (values) => {
      const setInput = (selectors, value) => {
        if (!value) return false;
        const el = selectors.map(s => document.querySelector(s)).find(Boolean);
        if (!el) return false;
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
        setter?.call(el, value);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('blur', {bubbles: true}));
        return el.value === value;
      };
      const setSelect = (selectors, value, alternatives=[]) => {
        if (!value) return false;
        const el = selectors.map(s => document.querySelector(s)).find(Boolean);
        if (!el) return false;
        const candidates = [String(value), ...alternatives.map(String)];
        const option = [...el.options].find(o => candidates.includes(o.value) || candidates.includes(o.textContent.trim()));
        if (!option) return false;
        el.value = option.value;
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
      };
      const dob = values.dob ? new Date(values.dob + 'T00:00:00Z') : null;
      const month = dob ? String(dob.getUTCMonth() + 1) : '';
      const monthName = dob ? dob.toLocaleString('en-US', {month:'long', timeZone:'UTC'}) : '';
      const day = dob ? String(dob.getUTCDate()) : '';
      const year = dob ? String(dob.getUTCFullYear()) : '';
      return {
        email: setInput(['input[name="emailOrPhone"]','input[name="email"]','input[type="email"]','input[autocomplete="email"]'], values.email),
        password: setInput(['input[name="password"]','input[type="password"]','input[autocomplete="new-password"]'], values.password),
        username: setInput(['input[name="username"]','input[autocomplete="username"]'], values.username),
        fullName: values.fullName ? setInput(['input[name="fullName"]','input[autocomplete="name"]'], values.fullName) : true,
        month: setSelect(['select[name="month"]','select[aria-label*="Month" i]'], month, [monthName, month.padStart(2,'0')]),
        day: setSelect(['select[name="day"]','select[aria-label*="Day" i]'], day, [day.padStart(2,'0')]),
        year: setSelect(['select[name="year"]','select[aria-label*="Year" i]'], year, [])
      };
    }
    """
    values = {"email": email, "password": password, "username": str(username), "fullName": str(full_name), "dob": str(dob or "")}

    last_result = None
    for attempt in range(15):
        result = _evaluate(tab, f"({expression})({json.dumps(values)})")
        last_result = result
        logging.info("Signup fields attempt %d: %s", attempt + 1, result)
        if result and result.get("email") and result.get("password") and result.get("username"):
            return True
        time.sleep(1)

    logging.error("Signup fields could not be filled after 15 attempts: %s", last_result)
    return False


def submit_signup(tab: dict) -> bool:
    """Click the normal Instagram signup action only; CAPTCHA/OTP remains manual."""
    expression = """
    () => {
      const buttons = [...document.querySelectorAll('button')];
      const button = buttons.find(b => /sign up|create account/i.test((b.innerText || '').trim()));
      if (!button || button.disabled) return false;
      button.click();
      return true;
    }
    """
    return bool(_evaluate(tab, expression))


def fill_otp(tab: dict, otp: str) -> bool:
    """Fill only a user-supplied verification code; never obtain or generate it."""
    otp = str(otp).strip()
    if not otp or len(otp) > 32 or not otp.isalnum():
        return False
    expression = """
    (code) => {
      const inputs = [...document.querySelectorAll('input')];
      const el = inputs.find(x => /code|otp|confirmation|security/i.test((x.name || '') + ' ' + (x.placeholder || '') + ' ' + (x.getAttribute('aria-label') || ''))) || inputs.find(x => x.inputMode === 'numeric' || x.type === 'number' || x.type === 'tel');
      if (!el) return {filled:false, submitted:false};
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(el, code);
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
      const button = [...document.querySelectorAll('button')].find(b => /confirm|continue|next|submit|verify/i.test(b.innerText || b.getAttribute('aria-label') || ''));
      if (button && !button.disabled) { button.click(); return {filled:true, submitted:true}; }
      return {filled:true, submitted:false};
    }
    """
    result = _evaluate(tab, f"({expression})({json.dumps(otp)})")
    logging.info("OTP field result: %s", result)
    return bool(result and result.get("filled"))


def inspect_state(tab: dict) -> dict:
    value = _evaluate(tab, "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,4000)})")
    data = json.loads(value or "{}")
    text = data.get("text", "").lower()
    if any(x in text for x in ("security code", "confirmation code", "enter the code", "confirm your email")):
        status = "otp_required"
    elif "captcha" in text:
        status = "captcha_required"
    elif "welcome to instagram" in text:
        status = "completed"
    else:
        status = "waiting"
    return {"status": status, "url": data.get("url", ""), "title": data.get("title", "")}


def start_signup(credentials: dict[str, str], identity: dict[str, Any] | None = None) -> tuple[dict, bool]:
    cdp_version()
    tab = open_signup()
    try:
        filled = fill_fields(tab, credentials, identity)
        if filled:
            submit_signup(tab)
        return tab, filled
    except Exception:
        close_tab(tab)
        raise


def main() -> int:
    try:
        version = cdp_version()
        credentials = {"email": os.getenv("IG_EMAIL", ""), "password": os.getenv("IG_PASSWORD", ""), "username": os.getenv("IG_USERNAME", ""), "full_name": os.getenv("IG_FULL_NAME", "")}
        tab, filled = start_signup(credentials)
        try:
            print(f"Connected: {version.get('Browser', 'unknown browser')}")
            print(f"Signup tab: {tab.get('url', SIGNUP_URL)}")
            print(f"Form fields filled: {filled}")
            print("CAPTCHA/OTP/verification remain manual.")
            return 0
        finally:
            close_tab(tab)
    except (requests.RequestException, OSError, TimeoutError, json.JSONDecodeError, RuntimeError, WebSocketBadStatusException) as exc:
        print(f"Signup assistant failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
