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


def _eval(tab: dict, expression: str) -> Any:
    with tab.setdefault("_lock", threading.RLock()):
        ws, sid = tab.get("_ws"), tab.get("sessionId")
        if ws is None or not sid:
            raise RuntimeError("Lightpanda CDP session is unavailable")
        last = None
        for attempt in range(3):
            try:
                result = _call(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True}, 100 + attempt, sid)
                if not result.get("error"):
                    return result.get("result", {}).get("result", {}).get("value")
                last = result["error"]
            except Exception as exc:
                last = exc
            time.sleep(0.4)
        raise RuntimeError(f"Runtime.evaluate failed: {last}")


def start_keepalive(tab: dict, interval: float = 15.0):
    stop = tab.setdefault("_keepalive_stop", threading.Event())
    old = tab.get("_keepalive_thread")
    if old and old.is_alive():
        return stop, old
    ws = tab.get("_ws")
    if ws is None:
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
            tab = {"id": target, "targetId": target, "sessionId": sid, "type": "page", "url": url, "browserWebSocketDebuggerUrl": _ws_url(), "_ws": ws, "_lock": threading.RLock(), "_signup_stop": threading.Event(), "_signup_thread": None, "_attempted_usernames": set()}
            for rid, method in enumerate(("Page.enable", "Runtime.enable", "Network.enable"), 10):
                _call(ws, method, request_id=rid, session_id=sid)
            logging.info("Lightpanda signup target attached; original CDP connection retained")
            return tab
        except (WebSocketBadStatusException, requests.RequestException, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            last = exc
            if ws:
                try: ws.close()
                except Exception: pass
            if attempt < 2: time.sleep(1)
    raise last or RuntimeError("Unable to open Lightpanda tab")


def open_signup():
    return open_url(SIGNUP_URL)


def close_tab(tab: dict):
    stop_keepalive(tab)
    stop = tab.get("_signup_stop")
    if stop: stop.set()
    ws = tab.get("_ws")
    if ws:
        try: ws.close()
        except Exception: pass
    tab["_ws"] = None
    tab["sessionId"] = None


def _snapshot(tab: dict) -> dict:
    expr = "()=>({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,7000),inputs:[...document.querySelectorAll('input,select')].map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',autocomplete:e.autocomplete||'',placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',disabled:!!e.disabled}))})()"
    return _eval(tab, expr) or {}


def _match(item: dict, *words: str) -> bool:
    text = " ".join(str(item.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder", "aria")).lower()
    return any(w.lower() in text for w in words)


def _set_input(tab: dict, item: dict, value: str) -> bool:
    if not value: return False
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
    if not item: return "username_waiting"
    attempted=tab.setdefault("_attempted_usernames",set())
    for candidate in _candidates(identity):
        if candidate.lower() in attempted: continue
        attempted.add(candidate.lower())
        if not _set_input(tab,item,candidate): continue
        time.sleep(0.8)
        if _username_rejected(str(_snapshot(tab).get("text",""))):
            logging.info("Username rejected: %s",candidate); continue
        identity["selected_username"]=candidate; identity["username"]=candidate
        logging.info("Username selected at username step: %s",candidate)
        _click_primary(tab)
        return "username_submitted"
    return "username_waiting"


def _advance(tab: dict, credentials: dict, identity: dict) -> str:
    snap=_snapshot(tab); text=str(snap.get("text","")); low=text.lower(); inputs=snap.get("inputs",[])
    if any(x in low for x in ("confirmation code","security code","enter the code","confirm your email")): return "otp_required"
    if "captcha" in low or "security check" in low: return "captcha_required"
    if any(x in low for x in ("welcome to instagram","account created","your instagram profile")): return "completed"
    email=str(credentials.get("email") or identity.get("email") or "")
    password=str(credentials.get("password") or identity.get("password") or "")
    email_item=next((i for i in inputs if i.get("tag")=="INPUT" and _match(i,"email","emailorphone","e-mail")),None)
    password_item=next((i for i in inputs if i.get("tag")=="INPUT" and _match(i,"password","new-password")),None)
    username_item=next((i for i in inputs if i.get("tag")=="INPUT" and _match(i,"username","user name","handle","screen name")),None)
    if email_item and email and not password_item:
        if _set_input(tab,email_item,email): _click_primary(tab); return "email_submitted"
    if password_item and password:
        if _set_input(tab,password_item,password): _click_primary(tab); return "password_submitted"
    if username_item and not identity.get("selected_username"):
        return _handle_username(tab,identity)
    return "waiting"


def _worker(tab: dict, credentials: dict, identity: dict):
    logging.info("Instagram signup progression worker started")
    deadline=time.time()+float(os.getenv("SIGNUP_FLOW_TIMEOUT","900")); last=None
    while not tab.get("_signup_stop",threading.Event()).is_set() and time.time()<deadline:
        try:
            state=_advance(tab,credentials,identity); tab["signup_state"]=state
            if state!=last: logging.info("Instagram signup state: %s",state); last=state
            if state=="completed": tab["signup_done"]=True; return
        except Exception as exc:
            logging.warning("Signup progression iteration failed: %s: %s",type(exc).__name__,str(exc)[:300])
        time.sleep(1.5)


def start_signup_progression(tab: dict, credentials: dict, identity: dict):
    old=tab.get("_signup_thread")
    if old and old.is_alive(): return old
    thread=threading.Thread(target=_worker,args=(tab,credentials or {},identity or {}),name="instagram-signup-flow",daemon=True)
    tab["_signup_thread"]=thread; thread.start(); return thread


def fill_fields(tab: dict, credentials: dict|None=None, identity: dict[str,Any]|None=None) -> bool:
    state=_advance(tab,credentials or {},identity or {})
    logging.info("Signup initial UI state: %s",state)
    return state not in {"waiting","username_waiting"}


def submit_signup(tab: dict) -> bool:
    return _click_primary(tab)


def fill_otp(tab: dict, otp: str) -> bool:
    otp=str(otp).strip()
    if len(otp)!=6 or not otp.isdigit(): return False
    payload=json.dumps(otp)
    expr="(code)=>{const el=[...document.querySelectorAll('input')].find(x=>/code|otp|confirmation|security/i.test((x.name||'')+' '+(x.placeholder||'')+' '+(x.getAttribute('aria-label')||'')))||[...document.querySelectorAll('input')].find(x=>x.inputMode==='numeric'||x.type==='number'||x.type==='tel');if(!el)return {filled:false};const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(s)s.call(el,code);else el.value=code;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));const b=[...document.querySelectorAll('button,[role=\"button\"]')].find(x=>!x.disabled&&/confirm|continue|next|submit|verify/i.test(x.innerText||x.textContent||x.getAttribute('aria-label')||''));if(b)b.click();return {filled:true};}"
    result=_eval(tab,expr+f"({payload})")
    return bool(result and result.get("filled"))


def inspect_state(tab: dict) -> dict:
    value=_eval(tab,"JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,4000)})")
    data=json.loads(value or "{}"); text=str(data.get("text"," ")).lower()
    if any(x in text for x in ("security code","confirmation code","enter the code","confirm your email")): status="otp_required"
    elif "captcha" in text or "security check" in text: status="captcha_required"
    elif tab.get("signup_done") or any(x in text for x in ("welcome to instagram","account created","your instagram profile")): status="completed"
    else: status=tab.get("signup_state","waiting")
    return {"status":status,"url":data.get("url",""),"title":data.get("title","")}


def start_signup(credentials: dict[str,str], identity: dict[str,Any]|None=None):
    cdp_version(); tab=open_signup()
    try:
        start_signup_progression(tab,credentials or {},identity or {}); time.sleep(0.8); return tab,True
    except Exception:
        close_tab(tab); raise
