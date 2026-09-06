"""Lightpanda/CDP browser workflow helpers.

The browser websocket is connection-scoped in Lightpanda, so a tab owns its
original websocket for its whole lifetime. No CDP reattach is attempted.
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
        _browser_ws_url(),
        timeout=30,
        http_proxy_host=None,
        http_proxy_port=None,
        http_no_proxy=["127.0.0.1", "localhost"],
        suppress_origin=True,
    )


def cdp_call(ws, method: str, params: dict | None = None, request_id: int = 1, session_id: str | None = None) -> dict:
    message = {"id": request_id, "method": method, "params": params or {}}
    if session_id:
        message["sessionId"] = session_id
    ws.send(json.dumps(message))
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            raw = ws.recv()
            if not raw:
                continue
            incoming = json.loads(raw)
            if "id" not in incoming:
                event = incoming.get("method", "")
                if event in {"Target.detachedFromTarget", "Inspector.targetCrashed", "Runtime.executionContextDestroyed"}:
                    logging.warning("CDP ASYNC EVENT: %s", event)
                continue
            if incoming.get("id") == request_id:
                return incoming
        except Exception as exc:
            logging.error("WebSocket recv error during %s: %s", method, exc)
            raise RuntimeError(f"WebSocket failure during {method}: {exc}") from exc
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def _prepare_page(tab: dict) -> None:
    for index, method in enumerate(("Page.enable", "Runtime.enable", "Network.enable"), start=10):
        result = cdp_call(tab["_ws"], method, request_id=index, session_id=tab["sessionId"])
        if result.get("error"):
            logging.warning("%s failed: %s", method, result["error"])


def _socket_alive(ws) -> bool:
    return bool(ws is not None and getattr(ws, "connected", True))


def _evaluate(tab: dict, expression: str) -> Any:
    lock = tab.setdefault("_lock", threading.RLock())
    with lock:
        ws = tab.get("_ws")
        session_id = tab.get("sessionId")
        if ws is None or not session_id:
            raise RuntimeError("Lightpanda CDP session is unavailable; original connection is gone")
        last_error = None
        for attempt in range(3):
            try:
                result = cdp_call(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True}, 100 + attempt, session_id)
                if not result.get("error"):
                    return result.get("result", {}).get("result", {}).get("value")
                err = result["error"]
                message = str(err.get("message", ""))
                if "BrowserContextNotLoaded" in message or "Cannot find context" in message:
                    last_error = RuntimeError(f"Lightpanda execution context unavailable: {message}")
                else:
                    last_error = RuntimeError(f"CDP Runtime.evaluate failed: {err}")
            except Exception as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(0.5)
        if not _socket_alive(ws):
            raise RuntimeError("Lightpanda CDP connection closed; connection-scoped target cannot be reattached") from last_error
        raise RuntimeError(f"CDP Runtime.evaluate failed after 3 attempts: {last_error}") from last_error


def start_keepalive(tab: dict, interval: float = 15.0):
    stop_event = tab.setdefault("_keepalive_stop", threading.Event())
    existing = tab.get("_keepalive_thread")
    if existing and existing.is_alive():
        return stop_event, existing
    ws = tab.get("_ws")
    if ws is None:
        logging.warning("Keepalive not started: original connection unavailable")
        return stop_event, threading.current_thread()

    def loop():
        logging.info("Network keepalive started for WS connection")
        while not stop_event.is_set() and tab.get("_ws") is ws:
            try:
                ws.ping()
            except Exception as exc:
                logging.warning("Keepalive ping failed: %s", exc)
                break
            stop_event.wait(interval)

    thread = threading.Thread(target=loop, name="ws-keepalive", daemon=True)
    tab["_keepalive_thread"] = thread
    thread.start()
    return stop_event, thread


def stop_keepalive(tab: dict) -> None:
    event = tab.get("_keepalive_stop")
    if event:
        event.set()


def open_url(url: str) -> dict:
    last_error = None
    for attempt in range(3):
        ws = None
        try:
            cdp_version()
            ws = _create_browser_connection()
            # Important: create the target with its final URL. Avoid Page.navigate,
            # which can replace the connection-scoped Lightpanda execution context.
            created = cdp_call(ws, "Target.createTarget", {"url": url}, request_id=1)
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
            tab = {
                "id": target_id,
                "targetId": target_id,
                "sessionId": session_id,
                "type": "page",
                "url": url,
                "browserWebSocketDebuggerUrl": _browser_ws_url(),
                "_ws": ws,
                "_lock": threading.RLock(),
            }
            _prepare_page(tab)
            return tab
        except WebSocketBadStatusException as exc:
            last_error = RuntimeError(f"Lightpanda CDP websocket handshake failed: {exc}")
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
    raise last_error or RuntimeError("Unable to open Lightpanda tab")


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
    tab["sessionId"] = None


def _username_available(tab: dict, username: str) -> bool:
    result = _evaluate(tab, """(candidate)=>{const el=document.querySelector('input[name="username"]')||document.querySelector('input[autocomplete="username"]');if(!el)return {state:'missing'};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;setter?.call(el,candidate);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return {state:'entered'};}""" f"({json.dumps(username)})")
    if not result or result.get("state") != "entered":
        return False
    unavailable = re.compile(r"username\s+(?:is\s+)?(?:not\s+available|unavailable)|username\s+(?:is\s+)?already\s+(?:taken|in use)|this username is not available|please try another username", re.I)
    available = re.compile(r"username\s+(?:is\s+)?available", re.I)
    for _ in range(8):
        state = _evaluate(tab, """(()=>{const el=document.querySelector('input[name="username"]')||document.querySelector('input[autocomplete="username"]');const box=el?.closest('form')||el?.parentElement||document.body;return {invalid:el?.getAttribute('aria-invalid')||'',text:(box?.innerText||document.body?.innerText||'').slice(0,3000)};})()""") or {}
        text = str(state.get("text", ""))
        if unavailable.search(text) or str(state.get("invalid", "")).lower() == "true":
            return False
        if available.search(text):
            return True
        time.sleep(0.75)
    return False


def select_available_username(tab: dict, identity: dict[str, Any]) -> str | None:
    seen = set()
    for value in identity.get("usernames") or []:
        candidate = str(value).strip()
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        if _username_available(tab, candidate):
            identity["selected_username"] = candidate
            identity["username"] = candidate
            return candidate
    return None


def fill_fields(tab: dict, credentials: dict[str, str] | None = None, identity: dict[str, Any] | None = None) -> bool:
    credentials = credentials or {}
    identity = identity or {}
    email = credentials.get("email") or os.getenv("IG_EMAIL")
    password = credentials.get("password") or os.getenv("IG_PASSWORD")
    username = str(identity.get("selected_username") or credentials.get("username") or "").strip()
    full_name = credentials.get("full_name", "")
    dob = identity.get("date_of_birth") or credentials.get("date_of_birth")
    if not email or not password or not username:
        logging.error("Email, password and confirmed username are required.")
        return False
    expression = """(values)=>{const setInput=(selectors,value)=>{if(!value)return false;const el=selectors.map(s=>document.querySelector(s)).find(Boolean);if(!el)return false;const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;setter?.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return el.value===value;};const setSelect=(selectors,value,alts=[])=>{if(!value)return false;const el=selectors.map(s=>document.querySelector(s)).find(Boolean);if(!el)return false;const candidates=[String(value),...alts.map(String)];const option=[...el.options].find(o=>candidates.includes(o.value)||candidates.includes(o.textContent.trim()));if(!option)return false;el.value=option.value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true;};const d=values.dob?new Date(values.dob+'T00:00:00Z'):null;const m=d?String(d.getUTCMonth()+1):'';const mn=d?d.toLocaleString('en-US',{month:'long',timeZone:'UTC'}):'';const day=d?String(d.getUTCDate()):'';const y=d?String(d.getUTCFullYear()):'';return {email:setInput(['input[name="emailOrPhone"]','input[name="email"]','input[type="email"]','input[autocomplete="email"]'],values.email),password:setInput(['input[name="password"]','input[type="password"]','input[autocomplete="new-password"]'],values.password),username:setInput(['input[name="username"]','input[autocomplete="username"]'],values.username),fullName:values.fullName?setInput(['input[name="fullName"]','input[autocomplete="name"]'],values.fullName):true,month:setSelect(['select[name="month"]','select[aria-label*="Month" i]'],m,[mn,m.padStart(2,'0')]),day:setSelect(['select[name="day"]','select[aria-label*="Day" i]'],day,[day.padStart(2,'0')]),year:setSelect(['select[name="year"]','select[aria-label*="Year" i]'],y,[])};}"""
    values = {"email": email, "password": password, "username": username, "fullName": str(full_name), "dob": str(dob or "")}
    for attempt in range(15):
        try:
            result = _evaluate(tab, f"({expression})({json.dumps(values)})")
            logging.info("Signup fields attempt %d: %s", attempt + 1, result)
            if result and result.get("email") and result.get("password") and result.get("username"):
                return True
        except Exception as exc:
            logging.warning("Signup fields evaluation error on attempt %d: %s", attempt + 1, exc)
        time.sleep(1)
    return False


def submit_signup(tab: dict) -> bool:
    return bool(_evaluate(tab, """()=>{const b=[...document.querySelectorAll('button')].find(x=>/sign up|create account/i.test((x.innerText||'').trim()));if(!b||b.disabled)return false;b.click();return true;}"""))


def fill_otp(tab: dict, otp: str) -> bool:
    otp = str(otp).strip()
    if len(otp) != 6 or not otp.isdigit():
        return False
    result = _evaluate(tab, """(code)=>{const inputs=[...document.querySelectorAll('input')];const el=inputs.find(x=>/code|otp|confirmation|security/i.test((x.name||'')+' '+(x.placeholder||'')+' '+(x.getAttribute('aria-label')||'')))||inputs.find(x=>x.inputMode==='numeric'||x.type==='number'||x.type==='tel');if(!el)return {filled:false};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;setter?.call(el,code);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));const b=[...document.querySelectorAll('button')].find(x=>/confirm|continue|next|submit|verify/i.test(x.innerText||x.getAttribute('aria-label')||''));if(b&&!b.disabled)b.click();return {filled:true};}""" f"({json.dumps(otp)})")
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
