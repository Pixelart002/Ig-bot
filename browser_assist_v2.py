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

CDP_URL = os.getenv("CDP_URL", "")
SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def cdp_version() -> dict:
    base = (CDP_URL or "").strip().rstrip("/")
    if base.startswith(("ws://", "wss://")):
        return {"Browser": "Lightpanda Cloud", "webSocketDebuggerUrl": base}
    if base.startswith(("http://", "https://")):
        r = requests.get(f"{base}/json/version", timeout=5)
        r.raise_for_status()
        return r.json()
    raise RuntimeError("CDP_URL must be a Lightpanda Cloud WebSocket (ws:// or wss://).")


def _ws_url() -> str:
    base = (CDP_URL or "").strip().rstrip("/")
    if base.startswith(("ws://", "wss://")):
        return base
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1)
    if base.startswith("http://"):
        return base.replace("http://", "ws://", 1)
    raise RuntimeError("CDP_URL must be a Lightpanda Cloud WebSocket (ws:// or wss://).")


def _connect():
    return create_connection(_ws_url(), timeout=30, http_proxy_host=None, http_proxy_port=None, http_no_proxy=["127.0.0.1", "localhost"], suppress_origin=True)


def _call(ws, method, params=None, request_id=1, session_id=None):
    msg = {"id": request_id, "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    ws.send(json.dumps(msg))
    deadline = time.time() + 30
    while time.time() < deadline:
        incoming = json.loads(ws.recv())
        if incoming.get("id") == request_id:
            return incoming
    raise TimeoutError(f"CDP timeout: {method}")


def cdp_call(ws, method, params=None, request_id=1, session_id=None):
    return _call(ws, method, params, request_id=request_id, session_id=session_id)


def _eval(tab: dict, expression: str) -> Any:
    lock = tab.setdefault("_lock", threading.RLock())
    with lock:
        ws, sid = tab.get("_ws"), tab.get("sessionId")
        if ws is None or not sid:
            raise RuntimeError("Lightpanda CDP session is unavailable; connection is closed")
        last = None
        for attempt in range(3):
            try:
                result = _call(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True}, 100 + attempt, sid)
                if not result.get("error"):
                    return result.get("result", {}).get("result", {}).get("value")
                last = result["error"]
            except Exception as exc:
                last = exc
                if isinstance(exc, (BrokenPipeError, ConnectionError, OSError)):
                    tab["_connection_dead"] = True
                    tab["_ws"] = None
                    tab["sessionId"] = None
                    raise RuntimeError("Lightpanda CDP connection closed; connection-scoped target cannot be reattached") from exc
            time.sleep(0.4)
        raise RuntimeError(f"Runtime.evaluate failed: {last}")


_evaluate = _eval


def start_keepalive(tab: dict, interval: float = 10.0):
    stop = tab.setdefault("_keepalive_stop", threading.Event())
    old = tab.get("_keepalive_thread")
    if old and old.is_alive():
        return stop, old
    ws = tab.get("_ws")
    if ws is None:
        return stop, threading.current_thread()

    def loop():
        logging.info("Network keepalive started for original Lightpanda WS connection")
        while not stop.is_set() and tab.get("_ws") is ws:
            try:
                ws.ping()
            except Exception as exc:
                tab["_connection_dead"] = True
                logging.warning("Lightpanda original WS closed: %s", exc)
                try:
                    ws.close()
                except Exception:
                    pass
                tab["_ws"] = None
                tab["sessionId"] = None
                break
            stop.wait(interval)

    thread = threading.Thread(target=loop, name="lightpanda-ws-keepalive", daemon=True)
    tab["_keepalive_thread"] = thread
    thread.start()
    return stop, thread


def stop_keepalive(tab: dict):
    event = tab.get("_keepalive_stop")
    if event:
        event.set()


def open_url(url: str) -> dict:
    last = None
    for attempt in range(3):
        ws = None
        try:
            cdp_version()
            ws = _connect()
            created = _call(ws, "Target.createTarget", {"url": url}, 1)
            target = created.get("result", {}).get("targetId")
            if not target:
                raise RuntimeError(str(created.get("error") or "No targetId"))
            attached = _call(ws, "Target.attachToTarget", {"targetId": target, "flatten": True}, 2)
            sid = attached.get("result", {}).get("sessionId")
            if not sid:
                raise RuntimeError(str(attached.get("error") or "No sessionId"))
            tab = {
                "id": target,
                "targetId": target,
                "sessionId": sid,
                "type": "page",
                "url": url,
                "browserWebSocketDebuggerUrl": _ws_url(),
                "_ws": ws,
                "_lock": threading.RLock(),
                "_signup_stop": threading.Event(),
                "_signup_thread": None,
                "_attempted_usernames": set(),
                "_connection_dead": False,
            }
            for rid, method in enumerate(("Page.enable", "Runtime.enable", "Network.enable"), 10):
                _call(ws, method, request_id=rid, session_id=sid)
            logging.info("Lightpanda signup target attached; original CDP connection retained")
            start_keepalive(tab, interval=10.0)
            return tab
        except (WebSocketBadStatusException, requests.RequestException, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            last = exc
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
            if attempt < 2:
                time.sleep(1)
    raise last or RuntimeError("Unable to open Lightpanda tab")


def open_signup():
    return open_url(SIGNUP_URL)


def close_tab(tab: dict):
    stop_keepalive(tab)
    stop = tab.get("_signup_stop")
    if stop:
        stop.set()
    ws = tab.get("_ws")
    if ws:
        try:
            ws.close()
        except Exception:
            pass
    tab["_ws"] = None
    tab["sessionId"] = None


def _snapshot(tab: dict) -> dict:
    expr = "()=>({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,7000),inputs:[...document.querySelectorAll('input,select')].map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',autocomplete:e.autocomplete||'',placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',disabled:!!e.disabled}))})()"
    return _eval(tab, expr) or {}


def _match(item: dict, *words: str) -> bool:
    text = " ".join(str(item.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder", "aria")).lower()
    return any(w.lower() in text for w in words)


def _set_input(tab: dict, item: dict, value: str) -> bool:
    if not value:
        return False
    payload = json.dumps({k: str(item.get(k) or "") for k in ("name", "autocomplete", "aria", "placeholder")} | {"value": str(value)})
    expr = "(p)=>{const a=[['name',p.name],['autocomplete',p.autocomplete],['aria-label',p.aria],['placeholder',p.placeholder]];let el=null;for(const [k,v] of a){if(v){el=document.querySelector('input['+k+'=\"'+CSS.escape(v)+'\"]');if(el)break;}}if(!el)return false;const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(s)s.call(el,p.value);else el.value=p.value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return true;}"
    return bool(_eval(tab, expr + f"({payload})"))


def _click_primary(tab: dict) -> bool:
    expr = "()=>{const b=[...document.querySelectorAll('button,[role=\"button\"]')].find(x=>{const t=(x.innerText||x.textContent||x.getAttribute('aria-label')||'').trim();return !x.disabled&&/^(next|continue|confirm|sign up|create account|submit|verify)$/i.test(t);});if(!b)return false;b.click();return true;}"
    return bool(_eval(tab, expr))


def _candidates(identity: dict) -> list[str]:
    seen=set(); out=[]
    for raw in [identity.get("selected_username"), identity.get("username"), *(identity.get("usernames") or [])]:
        value=re.sub(r"[^A-Za-z0-9._]+","_",str(raw or "").strip()).strip("._")[:30]
        if 3<=len(value)<=30 and value.lower() not in seen:
            seen.add(value.lower()); out.append(value)
    return out


def _username_rejected(text: str) -> bool:
    return bool(re.search(r"(username|user name).{0,100}(not available|unavailable|already taken|taken|in use|try another)", text, re.I|re.S) or re.search(r"this username is not available|please try another username", text, re.I))


def _handle_username(tab: dict, identity: dict) -> str:
    snap=_snapshot(tab)
    item=next((i for i in snap.get("inputs",[]) if i.get("tag")=="INPUT" and _match(i,"username","user name","handle","screen name")),None)
    if not item:
        return "username_waiting"
    attempted=tab.setdefault("_attempted_usernames",set())
    for candidate in _candidates(identity):
        if candidate.lower() in attempted:
            continue
        attempted.add(candidate.lower())
        if not _set_input(tab,item,candidate):
            continue
        time.sleep(0.8)
        if _username_rejected(str(_snapshot(tab).get("text",""))):
            logging.info("Username rejected: %s",candidate)
            continue
        identity["selected_username"]=candidate; identity["username"]=candidate
        logging.info("Username selected at username step: %s",candidate)
        _click_primary(tab)
        return "username_submitted"
    return "username_waiting"


def _advance(tab: dict, credentials: dict, identity: dict) -> str:
    snap=_snapshot(tab); text=str(snap.get("text","")); low=text.lower(); inputs=snap.get("inputs",[])
    if any(x in low for x in ("confirmation code","security code","enter the code","confirm your email")):
        return "otp_required"
    if "captcha" in low or "security check" in low:
        return "captcha_required"
    if any(x in low for x in ("welcome to instagram","account created","your instagram profile")):
        return "completed"
    password=next((i for i in inputs if i.get("tag")=="INPUT" and str(i.get("type")).lower()=="password"),None)
    if password:
        if _set_input(tab,password,str(credentials.get("password") or identity.get("password") or "")):
            _click_primary(tab)
            return "progressed"
    email=next((i for i in inputs if i.get("tag")=="INPUT" and _match(i,"email")),None)
    if email:
        if _set_input(tab,email,str(credentials.get("email") or identity.get("email") or "")):
            _click_primary(tab)
            return "progressed"
    username_result=_handle_username(tab,identity)
    if username_result != "username_waiting":
        return username_result
    fullname=next((i for i in inputs if i.get("tag")=="INPUT" and _match(i,"full name","fullname","name")),None)
    if fullname and identity.get("display_names"):
        if _set_input(tab,fullname,str(identity["display_names"][0])):
            _click_primary(tab)
            return "progressed"
    return "waiting"


def _signup_worker(tab: dict, credentials: dict, identity: dict):
    logging.info("Instagram signup progression worker started")
    stop=tab.get("_signup_stop")
    while stop and not stop.is_set():
        try:
            state=_advance(tab,credentials,identity)
            tab["signup_state"]=state
            logging.info("Instagram signup state: %s",state)
            if state in {"otp_required","captcha_required","completed"}:
                return
            if tab.get("_connection_dead"):
                logging.warning("Signup progression stopped: original Lightpanda CDP connection is closed")
                return
        except Exception as exc:
            logging.warning("Signup progression iteration failed: %s",exc)
            if tab.get("_connection_dead"):
                return
        stop.wait(1.5)


def start_signup_progression(tab: dict, credentials: dict, identity: dict):
    old=tab.get("_signup_thread")
    if old and old.is_alive():
        return old
    thread=threading.Thread(target=_signup_worker,args=(tab,credentials,identity),name="instagram-signup",daemon=True)
    tab["_signup_thread"]=thread
    thread.start()
    return thread


def fill_fields(tab: dict, credentials: dict, identity: dict | None = None) -> bool:
    state=_advance(tab,credentials,identity or {})
    tab["signup_state"]=state
    return state in {"progressed","otp_required","captcha_required","completed","username_submitted"}


def submit_signup(tab: dict) -> bool:
    return _click_primary(tab)


def fill_otp(tab: dict, code: str) -> bool:
    payload=json.dumps(str(code).strip())
    expr="(code)=>{const inputs=[...document.querySelectorAll('input')].filter(x=>!x.disabled&&x.offsetParent!==null);const el=inputs.find(x=>/otp|code|confirmation|verification/i.test((x.name||'')+' '+(x.autocomplete||'')+' '+(x.placeholder||'')+' '+(x.getAttribute('aria-label')||'')))||inputs.find(x=>x.maxLength===6)||inputs[0];if(!el)return false;const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(s)s.call(el,code);else el.value=code;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));const b=[...document.querySelectorAll('button,[role=\"button\"]')].find(x=>/^(confirm|continue|next|submit|verify)$/i.test((x.innerText||x.textContent||'').trim())&&!x.disabled);if(b)b.click();return true;}"
    return bool(_eval(tab,expr+f"({payload})"))


def inspect_state(tab: dict) -> dict:
    try:
        snap=_snapshot(tab); text=str(snap.get("text","")).lower()
        if any(x in text for x in ("confirmation code","security code","enter the code","confirm your email")):
            status="otp_required"
        elif "captcha" in text or "security check" in text:
            status="captcha_required"
        elif any(x in text for x in ("welcome to instagram","account created","your instagram profile")):
            status="completed"
        else:
            status=str(tab.get("signup_state") or "waiting")
        return {"status":status,"url":snap.get("url",tab.get("url","")),"title":snap.get("title","")}
    except Exception as exc:
        return {"status":"connection_closed" if tab.get("_connection_dead") else "waiting","url":"","title":"","error":str(exc)[:300]}


def start_signup(credentials: dict, identity: dict):
    tab=open_signup()
    start_signup_progression(tab,credentials,identity)
    time.sleep(0.8)
    return tab,True


def main():
    print(cdp_version())


if __name__ == "__main__":
    main()
