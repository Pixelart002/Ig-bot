"""Lightpanda CDP helpers for the Instagram signup workflow.

One signup session owns one original browser websocket for its whole lifetime.
No CDP reattach/reconnect is attempted. CAPTCHA and other anti-bot controls
remain manual; this module only fills normal signup fields and user-provided OTPs.
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


def _raise(response, operation):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip().replace("\n", " ")[:300]
        raise requests.HTTPError(f"{operation}: HTTP {response.status_code} {detail}", response=response) from exc


def cdp_version():
    if CDP_URL.startswith(("ws://", "wss://")):
        return {"Browser": "Lightpanda Cloud", "webSocketDebuggerUrl": CDP_URL}
    response = requests.get(f"{CDP_URL.rstrip('/')}/json/version", timeout=5)
    _raise(response, "CDP /json/version")
    return response.json()


def _browser_ws_url():
    value = CDP_URL.rstrip("/")
    if value.startswith(("ws://", "wss://")):
        return value
    if value.startswith("https://"):
        return value.replace("https://", "wss://", 1)
    if value.startswith("http://"):
        return value.replace("http://", "ws://", 1)
    raise RuntimeError(f"Unsupported CDP_URL: {CDP_URL}")


def _connect():
    return create_connection(
        _browser_ws_url(),
        timeout=30,
        http_proxy_host=None,
        http_proxy_port=None,
        http_no_proxy=["127.0.0.1", "localhost"],
        suppress_origin=True,
    )


def cdp_call(ws, method, params=None, request_id=1, session_id=None):
    message = {"id": request_id, "method": method, "params": params or {}}
    if session_id:
        message["sessionId"] = session_id
    ws.send(json.dumps(message))
    deadline = time.time() + 30
    while time.time() < deadline:
        raw = ws.recv()
        if not raw:
            continue
        incoming = json.loads(raw)
        if "id" not in incoming:
            continue
        if incoming.get("id") == request_id:
            return incoming
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def _prepare_page(tab):
    for request_id, method in enumerate(("Page.enable", "Runtime.enable", "Network.enable"), start=10):
        result = cdp_call(tab["_ws"], method, request_id=request_id, session_id=tab["sessionId"])
        if result.get("error"):
            logging.warning("%s failed: %s", method, result["error"])


def _evaluate(tab, expression):
    lock = tab.setdefault("_lock", threading.RLock())
    with lock:
        ws = tab.get("_ws")
        session_id = tab.get("sessionId")
        if ws is None or not session_id:
            raise RuntimeError("Lightpanda CDP session is unavailable; original connection is gone")
        last = None
        for attempt in range(3):
            try:
                result = cdp_call(
                    ws,
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": True},
                    100 + attempt,
                    session_id,
                )
                if not result.get("error"):
                    return result.get("result", {}).get("result", {}).get("value")
                last = RuntimeError(f"CDP Runtime.evaluate failed: {result['error']}")
            except Exception as exc:
                last = exc
            if attempt < 2:
                time.sleep(0.5)
        if not getattr(ws, "connected", True):
            raise RuntimeError("Lightpanda CDP connection closed; connection-scoped target cannot be reattached") from last
        raise RuntimeError(f"CDP Runtime.evaluate failed after 3 attempts: {last}") from last


def start_keepalive(tab, interval=15.0):
    stop = tab.setdefault("_keepalive_stop", threading.Event())
    existing = tab.get("_keepalive_thread")
    if existing and existing.is_alive():
        return stop, existing
    ws = tab.get("_ws")
    if ws is None:
        logging.warning("Keepalive not started: original connection unavailable")
        return stop, threading.current_thread()

    def loop():
        logging.info("Network keepalive started for WS connection")
        while not stop.is_set() and tab.get("_ws") is ws:
            try:
                ws.ping()
            except Exception as exc:
                logging.warning("Keepalive ping failed: %s", exc)
                break
            stop.wait(interval)

    thread = threading.Thread(target=loop, name="ws-keepalive", daemon=True)
    tab["_keepalive_thread"] = thread
    thread.start()
    return stop, thread


def stop_keepalive(tab):
    event = tab.get("_keepalive_stop")
    if event:
        event.set()


def open_url(url):
    last_error = None
    for attempt in range(3):
        ws = None
        try:
            cdp_version()
            ws = _connect()
            created = cdp_call(ws, "Target.createTarget", {"url": url}, 1)
            if created.get("error"):
                raise RuntimeError(f"Target.createTarget failed: {created['error']}")
            target_id = created.get("result", {}).get("targetId")
            if not target_id:
                raise RuntimeError("Target.createTarget returned no targetId")
            attached = cdp_call(
                ws,
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
                2,
            )
            if attached.get("error"):
                raise RuntimeError(f"Target.attachToTarget failed: {attached['error']}")
            session_id = attached.get("result", {}).get("sessionId")
            if not session_id:
                raise RuntimeError("Target.attachToTarget returned no sessionId")
            tab = {
                "id": target_id,
                "targetId": target_id,
                "sessionId": session_id,
                "type": "page",
                "url": url,
                "browserWebSocketDebuggerUrl": _browser_ws_url(),
                "_ws": ws,
                "_lock": threading.RLock(),
                "_signup_thread": None,
                "_signup_stop": threading.Event(),
            }
            _prepare_page(tab)
            logging.info("Lightpanda signup target attached; original CDP connection retained")
            return tab
        except (WebSocketBadStatusException, requests.RequestException, OSError, ValueError, RuntimeError, TimeoutError) as exc:
            last_error = exc
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        if attempt < 2:
            logging.warning("Open tab attempt %d/3 failed: %s", attempt + 1, last_error)
            time.sleep(1)
    raise last_error or RuntimeError("Unable to open Lightpanda tab")


def open_signup():
    return open_url(SIGNUP_URL)


def close_tab(tab):
    stop_keepalive(tab)
    stop = tab.get("_signup_stop")
    if stop:
        stop.set()
    ws = tab.get("_ws")
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
    tab["_ws"] = None
    tab["sessionId"] = None


def _set_input(tab, selectors, value):
    if not value:
        return False
    payload = {"selectors": selectors, "value": str(value)}
    expression = """(p)=>{const el=p.selectors.map(s=>document.querySelector(s)).find(Boolean);if(!el)return false;const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(setter)setter.call(el,p.value);else el.value=p.value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return el.value===p.value;}"""
    return bool(_evaluate(tab, expression + f"({json.dumps(payload)})"))


def _click_next(tab):
    expression = """()=>{const buttons=[...document.querySelectorAll('button')];const b=buttons.find(x=>!x.disabled&&/^(next|continue|confirm|sign up|create account|submit|verify)$/i.test((x.innerText||'').trim()));if(!b)return false;b.click();return true;}"""
    return bool(_evaluate(tab, expression))


def _username_available(tab, username):
    if not _set_input(tab, ['input[name="username"]', 'input[autocomplete="username"]'], username):
        return False
    unavailable = re.compile(r"username.*(?:not available|unavailable|already.*(?:taken|use))|please try another username", re.I)
    expression = """(()=>{const el=document.querySelector('input[name="username"]')||document.querySelector('input[autocomplete="username"]');const box=el?.closest('form')||el?.parentElement||document.body;return {invalid:el?.getAttribute('aria-invalid')||'',text:(box?.innerText||document.body?.innerText||'').slice(0,3000)};})()"""
    for _ in range(8):
        state = _evaluate(tab, expression) or {}
        if str(state.get("invalid", "")).lower() == "true" or unavailable.search(str(state.get("text", ""))):
            logging.info("Username rejected by Instagram: %s", username)
            return False
        time.sleep(0.75)
    logging.info("Username has no negative signal; proceeding: %s", username)
    return True


def select_available_username(tab, identity):
    seen = set()
    for value in identity.get("usernames") or []:
        candidate = str(value).strip()
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        try:
            if _username_available(tab, candidate):
                identity["selected_username"] = candidate
                identity["username"] = candidate
                return candidate
        except Exception as exc:
            logging.warning("Username check failed for %s: %s", candidate, exc)
    return None


def _dob_parts(value):
    if not value:
        return "", "", ""
    try:
        year, month, day = str(value).split("-")
        return month.lstrip("0"), day.lstrip("0"), year
    except ValueError:
        return "", "", ""


def _page_snapshot(tab):
    expression = """()=>({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,5000),inputs:[...document.querySelectorAll('input')].map(x=>({name:x.name,type:x.type,placeholder:x.placeholder,autocomplete:x.autocomplete,value:x.value})),selects:[...document.querySelectorAll('select')].map(x=>({name:x.name,aria:x.getAttribute('aria-label'),value:x.value}))})()"""
    return _evaluate(tab, expression) or {}


def _fill_dob(tab, dob):
    month, day, year = _dob_parts(dob)
    if not (month and day and year):
        return False
    payload = json.dumps({"m": month, "d": day, "y": year})
    expression = """(v)=>{const pick=(selectors,val)=>{const el=selectors.map(s=>document.querySelector(s)).find(Boolean);if(!el)return false;const option=[...el.options].find(x=>x.value===String(val)||x.textContent.trim()===String(val));if(!option)return false;el.value=option.value;el.dispatchEvent(new Event('change',{bubbles:true}));return true;};return {month:pick(['select[name=month]','select[aria-label*="Month" i]'],v.m),day:pick(['select[name=day]','select[aria-label*="Day" i]'],v.d),year:pick(['select[name=year]','select[aria-label*="Year" i]'],v.y)};}"
    return bool(_evaluate(tab, expression + f"({payload})"))


def _fill_visible_signup_step(tab, credentials, identity):
    email = credentials.get("email") or identity.get("email")
    password = credentials.get("password") or identity.get("password")
    username = identity.get("selected_username") or identity.get("username")
    full_name = credentials.get("full_name") or identity.get("display_name") or ((identity.get("display_names") or [""])[0])
    dob = identity.get("date_of_birth") or credentials.get("date_of_birth")
    snapshot = _page_snapshot(tab)
    text = str(snapshot.get("text", "")).lower()

    if any(k in text for k in ("confirmation code", "security code", "enter the code", "confirm your email")):
        return "otp_required"
    if "captcha" in text:
        return "captcha_required"
    if any(k in text for k in ("welcome to instagram", "your instagram profile", "account created")):
        return "completed"

    changed = False
    changed |= _set_input(tab, ['input[name="emailOrPhone"]', 'input[name="email"]', 'input[type="email"]', 'input[autocomplete="email"]'], email)
    changed |= _set_input(tab, ['input[name="password"]', 'input[type="password"]', 'input[autocomplete="new-password"]'], password)
    changed |= _set_input(tab, ['input[name="fullName"]', 'input[autocomplete="name"]'], full_name)
    changed |= _set_input(tab, ['input[name="username"]', 'input[autocomplete="username"]'], username)
    changed |= _fill_dob(tab, dob)

    if changed:
        try:
            _click_next(tab)
        except Exception as exc:
            logging.debug("Next click deferred: %s", exc)
        return "progressed"
    return "waiting"


def _signup_worker(tab, credentials, identity):
    logging.info("Signup progression worker started on existing Lightpanda session")
    deadline = time.time() + float(os.getenv("SIGNUP_FLOW_TIMEOUT", "900"))
    last_state = None
    while not tab.get("_signup_stop").is_set() and time.time() < deadline:
        try:
            state = _fill_visible_signup_step(tab, credentials, identity)
            tab["signup_state"] = state
            if state != last_state:
                logging.info("Instagram signup state: %s", state)
                last_state = state
            if state == "completed":
                tab["signup_done"] = True
                return
            # OTP/CAPTCHA are intentionally not automated. Keep the same tab
            # alive and let OTP polling/manual CAPTCHA handling take over.
            time.sleep(1.5 if state in {"otp_required", "captcha_required"} else 2.0)
        except Exception as exc:
            logging.warning("Signup progression iteration failed: %s", exc)
            time.sleep(2)
    logging.info("Signup progression worker stopped")


def start_signup_progression(tab, credentials, identity):
    existing = tab.get("_signup_thread")
    if existing and existing.is_alive():
        return existing
    thread = threading.Thread(
        target=_signup_worker,
        args=(tab, credentials or {}, identity or {}),
        name="instagram-signup-flow",
        daemon=True,
    )
    tab["_signup_thread"] = thread
    thread.start()
    return thread


def fill_fields(tab, credentials=None, identity=None):
    credentials = credentials or {}
    identity = identity or {}
    email = credentials.get("email") or identity.get("email") or os.getenv("IG_EMAIL")
    password = credentials.get("password") or identity.get("password") or os.getenv("IG_PASSWORD")
    username = str(identity.get("selected_username") or identity.get("username") or credentials.get("username") or os.getenv("IG_USERNAME") or "").strip()
    if not email or not password or not username:
        logging.error("Email, password and confirmed username are required")
        return False
    for _ in range(15):
        state = _fill_visible_signup_step(tab, credentials, identity)
        if state in {"progressed", "otp_required", "captcha_required", "completed"}:
            return True
        time.sleep(1)
    return False


def submit_signup(tab):
    try:
        return _click_next(tab)
    except Exception:
        return False


def fill_otp(tab, otp):
    otp = str(otp).strip()
    if len(otp) != 6 or not otp.isdigit():
        return False
    payload = json.dumps(otp)
    expression = """(code)=>{const inputs=[...document.querySelectorAll('input')];const el=inputs.find(x=>/code|otp|confirmation|security/i.test((x.name||'')+' '+(x.placeholder||'')+' '+(x.getAttribute('aria-label')||'')))||inputs.find(x=>x.inputMode==='numeric'||x.type==='number'||x.type==='tel');if(!el)return {filled:false};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(setter)setter.call(el,code);else el.value=code;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));const b=[...document.querySelectorAll('button')].find(x=>!x.disabled&&/confirm|continue|next|submit|verify/i.test(x.innerText||x.getAttribute('aria-label')||''));if(b)b.click();return {filled:true};}"""
    result = _evaluate(tab, expression + f"({payload})")
    return bool(result and result.get("filled"))


def inspect_state(tab):
    value = _evaluate(tab, "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,5000)})")
    data = json.loads(value or "{}")
    text = str(data.get("text", "")).lower()
    if any(x in text for x in ("security code", "confirmation code", "enter the code", "confirm your email")):
        status = "otp_required"
    elif "captcha" in text:
        status = "captcha_required"
    elif tab.get("signup_done") or any(x in text for x in ("welcome to instagram", "your instagram profile", "account created")):
        status = "completed"
    elif tab.get("signup_state") in {"progressed", "waiting", "otp_required", "captcha_required"}:
        status = tab["signup_state"]
    else:
        status = "waiting"
    return {"status": status, "url": data.get("url", ""), "title": data.get("title", "")}


def start_signup(credentials, identity=None):
    cdp_version()
    tab = open_signup()
    try:
        identity = identity or {}
        if identity and not identity.get("selected_username"):
            selected = select_available_username(tab, identity)
            if not selected:
                # Keep the original session alive so the user can regenerate
                # the identity without leaving a dead tab in Session.
                logging.warning("No username candidate was accepted; keeping browser session open")
                return tab, False
        filled = fill_fields(tab, credentials, identity)
        start_signup_progression(tab, credentials or {}, identity)
        return tab, filled
    except Exception:
        close_tab(tab)
        raise


def main():
    try:
        version = cdp_version()
        credentials = {
            "email": os.getenv("IG_EMAIL", ""),
            "password": os.getenv("IG_PASSWORD", ""),
            "username": os.getenv("IG_USERNAME", ""),
            "full_name": os.getenv("IG_FULL_NAME", ""),
        }
        tab, filled = start_signup(credentials)
        print(f"Connected: {version.get('Browser', 'unknown browser')}")
        print(f"Signup tab: {tab.get('url', SIGNUP_URL)}")
        print(f"Initial fields handled: {filled}")
        time.sleep(5)
        close_tab(tab)
        return 0
    except Exception as exc:
        logging.exception("Browser assistant failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
