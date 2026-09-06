"""Lightpanda/CDP browser workflow helpers.

CAPTCHA, OTP, verification and anti-bot controls remain manual.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
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
        raise requests.HTTPError(f"{operation}: HTTP {response.status_code} {response.reason}; {detail}", response=response) from exc


def cdp_version() -> dict:
    response = requests.get(f"{CDP_URL}/json/version", timeout=5)
    _raise_for_status(response, "CDP /json/version")
    return response.json()


def _browser_ws_url() -> str:
    base = CDP_URL.rstrip("/")
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1)
    if base.startswith("http://"):
        return base.replace("http://", "ws://", 1)
    raise RuntimeError(f"Unsupported CDP_URL: {CDP_URL}")


def _create_browser_connection():
    return create_connection(
        _browser_ws_url(), timeout=30, http_proxy_host=None, http_proxy_port=None,
        http_no_proxy=["127.0.0.1", "localhost"], suppress_origin=True,
    )


def cdp_call(ws, method: str, params: dict | None = None, request_id: int = 1, session_id: str | None = None) -> dict:
    message = {"id": request_id, "method": method, "params": params or {}}
    if session_id:
        message["sessionId"] = session_id
    ws.send(json.dumps(message))
    deadline = time.time() + 30
    while time.time() < deadline:
        incoming = json.loads(ws.recv())
        if incoming.get("id") == request_id:
            return incoming
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def _prepare_page(tab: dict) -> None:
    for method in ("Page.enable", "Runtime.enable", "Network.enable"):
        result = cdp_call(tab["_ws"], method, session_id=tab["sessionId"])
        if result.get("error"):
            logging.warning("%s failed: %s", method, result["error"])


def _attach_existing_target(tab: dict) -> None:
    """Reconnect only when the transport is actually gone."""
    target_id = tab.get("targetId") or tab.get("id")
    if not target_id:
        raise RuntimeError("CDP tab has no target id")
    ws = _create_browser_connection()
    try:
        attached = cdp_call(ws, "Target.attachToTarget", {"targetId": target_id, "flatten": True}, request_id=1)
        if attached.get("error"):
            raise RuntimeError(f"CDP reattach failed: {attached['error']}")
        session_id = attached.get("result", {}).get("sessionId")
        if not session_id:
            raise RuntimeError("CDP reattach returned no sessionId")
        old_ws = tab.get("_ws")
        tab["_ws"] = ws
        tab["sessionId"] = session_id
        tab["targetId"] = target_id
        tab["id"] = target_id
        _prepare_page(tab)
        if old_ws is not None and old_ws is not ws:
            try:
                old_ws.close()
            except Exception:
                pass
        logging.info("Reattached CDP target %s", target_id)
    except Exception:
        try:
            ws.close()
        except Exception:
            pass
        raise


def _socket_alive(ws) -> bool:
    return bool(ws is not None and getattr(ws, "connected", True))


def _evaluate(tab: dict, expression: str) -> Any:
    lock = tab.setdefault("_lock", threading.RLock())
    with lock:
        ws = tab.get("_ws")
        session_id = tab.get("sessionId")
        if ws is None or not session_id:
            _attach_existing_target(tab)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = cdp_call(tab["_ws"], "Runtime.evaluate", {"expression": expression, "returnByValue": True}, session_id=tab["sessionId"], request_id=100 + attempt)
                if result.get("error"):
                    raise RuntimeError(f"CDP Runtime.evaluate failed: {result['error']}")
                return result.get("result", {}).get("result", {}).get("value")
            except Exception as exc:
                last_error = exc
                logging.warning("CDP evaluate attempt %d/3 failed: %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(0.25)
                    continue
                if not _socket_alive(tab.get("_ws")):
                    try:
                        _attach_existing_target(tab)
                        result = cdp_call(tab["_ws"], "Runtime.evaluate", {"expression": expression, "returnByValue": True}, session_id=tab["sessionId"], request_id=200)
                        if result.get("error"):
                            raise RuntimeError(f"CDP Runtime.evaluate failed after reconnect: {result['error']}")
                        return result.get("result", {}).get("result", {}).get("value")
                    except Exception as reconnect_error:
                        last_error = reconnect_error
        raise RuntimeError(f"CDP Runtime.evaluate failed: {type(last_error).__name__}: {last_error}") from last_error


def start_keepalive(tab: dict, interval: float = 1.5) -> tuple[threading.Event, threading.Thread]:
    """Keep a signup target active immediately after creation.

    All CDP evaluation is serialized by the tab lock, so this is safe to run
    alongside Telegram status checks and the OTP polling loop.
    """
    stop_event = tab.setdefault("_keepalive_stop", threading.Event())
    existing = tab.get("_keepalive_thread")
    if existing and existing.is_alive():
        return stop_event, existing

    def _loop() -> None:
        logging.info("Lightpanda keepalive started for target %s", tab.get("targetId") or tab.get("id"))
        while not stop_event.is_set():
            try:
                _evaluate(tab, "document.title")
            except Exception as exc:
                logging.warning("Lightpanda keepalive check failed: %s", exc)
            stop_event.wait(interval)
        logging.info("Lightpanda keepalive stopped for target %s", tab.get("targetId") or tab.get("id"))

    thread = threading.Thread(target=_loop, name="lightpanda-keepalive", daemon=True)
    tab["_keepalive_thread"] = thread
    thread.start()
    return stop_event, thread


def stop_keepalive(tab: dict) -> None:
    event = tab.get("_keepalive_stop")
    if event:
        event.set()


def open_url(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        ws = None
        try:
            cdp_version()
            ws = _create_browser_connection()
            created = cdp_call(ws, "Target.createTarget", {"url": "about:blank"}, request_id=1)
            if created.get("error"):
                raise RuntimeError(f"CDP Target.createTarget failed: {created['error']}")
            target_id = created.get("result", {}).get("targetId")
            if not target_id:
                raise RuntimeError("CDP Target.createTarget returned no targetId")
            attached = cdp_call(ws, "Target.attachToTarget", {"targetId": target_id, "flatten": True}, request_id=2)
            if attached.get("error"):
                raise RuntimeError(f"CDP Target.attachToTarget failed: {attached['error']}")
            session_id = attached.get("result", {}).get("sessionId")
            if not session_id:
                raise RuntimeError("CDP Target.attachToTarget returned no sessionId")
            tab = {"id": target_id, "targetId": target_id, "sessionId": session_id, "type": "page", "url": url, "browserWebSocketDebuggerUrl": _browser_ws_url(), "_ws": ws, "_lock": threading.RLock()}
            _prepare_page(tab)
            navigated = cdp_call(ws, "Page.navigate", {"url": url}, request_id=3, session_id=session_id)
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
        except (requests.RequestException, OSError, ValueError, RuntimeError, TimeoutError) as exc:
            last_error = exc
        finally:
            if ws is not None and last_error is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        if attempt < 2:
            logging.warning("Open tab attempt %d/3 failed: %s", attempt + 1, last_error)
            time.sleep(1)
    assert last_error is not None
    raise last_error


def open_signup() -> dict:
    return open_url(SIGNUP_URL)


def close_tab(tab: dict) -> None:
    stop_keepalive(tab)
    ws = tab.get("_ws")
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
        tab["_ws"] = None


def _username_available(tab: dict, username: str) -> bool:
    expression = """
    (candidate) => {
      const el = document.querySelector('input[name="username"]') || document.querySelector('input[autocomplete="username"]');
      if (!el) return {state:'missing'};
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(el, candidate);
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
      el.dispatchEvent(new Event('blur', {bubbles:true}));
      return {state:'entered'};
    }
    """
    result = _evaluate(tab, f"({expression})({json.dumps(username)})")
    if not result or result.get("state") != "entered":
        return False
    unavailable_re = re.compile(r"username\s+(?:is\s+)?(?:not\s+available|unavailable)|username\s+(?:is\s+)?already\s+(?:taken|in use)|this username is not available|please try another username", re.I)
    available_re = re.compile(r"username\s+(?:is\s+)?available", re.I)
    for _ in range(8):
        state = _evaluate(tab, """
        (() => {
          const el = document.querySelector('input[name="username"]') || document.querySelector('input[autocomplete="username"]');
          const container = el?.closest('form') || el?.parentElement || document.body;
          return {value: el?.value || '', invalid: el?.getAttribute('aria-invalid') || '', text: (container?.innerText || document.body?.innerText || '').slice(0, 3000)};
        })()
        """) or {}
        text = str(state.get("text", ""))
        if unavailable_re.search(text) or str(state.get("invalid", "")).lower() == "true":
            logging.info("Username unavailable: %s", username)
            return False
        if available_re.search(text):
            logging.info("Username available: %s", username)
            return True
        time.sleep(0.75)
    logging.warning("Username availability was not confirmed: %s", username)
    return False


def _pick_available_username(tab: dict, candidates: list[str]) -> str | None:
    seen: set[str] = set()
    for candidate in candidates:
        candidate = str(candidate).strip()
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        if _username_available(tab, candidate):
            return candidate
    return None


def select_available_username(tab: dict, identity: dict[str, Any]) -> str | None:
    candidates = [str(x) for x in (identity.get("usernames") or []) if str(x).strip()]
    selected = _pick_available_username(tab, candidates[:5]) if candidates else None
    if selected:
        identity["selected_username"] = selected
        identity["username"] = selected
    return selected


def fill_fields(tab: dict, credentials: dict[str, str] | None = None, identity: dict[str, Any] | None = None) -> bool:
    credentials = credentials or {}
    identity = identity or {}
    email = credentials.get("email") or os.getenv("IG_EMAIL")
    password = credentials.get("password") or os.getenv("IG_PASSWORD")
    username = str(identity.get("selected_username") or credentials.get("username") or "").strip()
    full_name = credentials.get("full_name", "")
    dob = identity.get("date_of_birth") or credentials.get("date_of_birth")
    if not email or not password or not username:
        logging.error("Email, password and confirmed selected username are required.")
        return False
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
    values = {"email": email, "password": password, "username": username, "fullName": str(full_name), "dob": str(dob or "")}
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
    otp = str(otp).strip()
    if not otp or len(otp) != 6 or not otp.isdigit():
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
        if identity and not identity.get("selected_username"):
            selected = select_available_username(tab, identity)
            if not selected:
                close_tab(tab)
                return tab, False
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
    except Exception as exc:
        logging.exception("Browser assistant failed: %s", exc)
        return 1
