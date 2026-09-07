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
    return create_connection(_ws_url(), timeout=30, http_proxy_host=None, http_proxy_port=None,
                             http_no_proxy=["127.0.0.1", "localhost"], suppress_origin=True)


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


def _mark_dead(tab: dict):
    tab["_connection_dead"] = True
    ws = tab.get("_ws")
    tab["_ws"] = None
    tab["sessionId"] = None
    if ws:
        try:
            ws.close()
        except Exception:
            pass


def _eval(tab: dict, expression: str) -> Any:
    lock = tab.setdefault("_lock", threading.RLock())
    with lock:
        ws, sid = tab.get("_ws"), tab.get("sessionId")
        if ws is None or not sid:
            raise RuntimeError("Lightpanda CDP session is unavailable; connection is closed")
        last = None
        for attempt in range(3):
            try:
                result = _call(ws, "Runtime.evaluate",
                               {"expression": expression, "returnByValue": True, "awaitPromise": True},
                               100 + attempt, sid)
                if result.get("error"):
                    last = result["error"]
                else:
                    envelope = result.get("result", {})
                    exception = envelope.get("exceptionDetails")
                    if exception:
                        last = exception
                        logging.warning("Lightpanda Runtime.evaluate JS error: %s", str(exception)[:500])
                    else:
                        value = envelope.get("result", {})
                        if value.get("subtype") == "error":
                            last = value
                        elif "value" in value:
                            return value["value"]
                        else:
                            last = {"missing_value": True, "result": value}
            except Exception as exc:
                last = exc
                if isinstance(exc, (BrokenPipeError, ConnectionError, OSError)):
                    _mark_dead(tab)
                    raise RuntimeError("Lightpanda CDP connection closed; connection-scoped target cannot be reattached") from exc
            time.sleep(0.4)
        raise RuntimeError(f"Runtime.evaluate failed: {last}")


_evaluate = _eval


def start_keepalive(tab: dict, interval: float = 5.0):
    stop = tab.setdefault("_keepalive_stop", threading.Event())
    old = tab.get("_keepalive_thread")
    if old and old.is_alive():
        return stop, old
    if tab.get("_ws") is None:
        return stop, threading.current_thread()

    def loop():
        logging.info("CDP application keepalive started on original Lightpanda connection")
        while not stop.is_set() and tab.get("_ws") is not None:
            try:
                _eval(tab, "document.readyState")
            except Exception as exc:
                if tab.get("_connection_dead"):
                    logging.warning("Lightpanda original CDP connection closed: %s", exc)
                    return
                logging.debug("CDP keepalive iteration failed: %s", exc)
            stop.wait(interval)

    thread = threading.Thread(target=loop, name="lightpanda-cdp-keepalive", daemon=True)
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
            tab = {"id": target, "targetId": target, "sessionId": sid, "type": "page", "url": url,
                   "browserWebSocketDebuggerUrl": _ws_url(), "_ws": ws, "_lock": threading.RLock(),
                   "_signup_stop": threading.Event(), "_signup_thread": None,
                   "_attempted_usernames": set(), "_connection_dead": False}
            for rid, method in enumerate(("Page.enable", "Runtime.enable", "Network.enable"), 10):
                _call(ws, method, request_id=rid, session_id=sid)
            logging.info("Lightpanda signup target attached; original CDP connection retained")
            start_keepalive(tab, interval=5.0)
            return tab
        except (WebSocketBadStatusException, requests.RequestException, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            last = exc
            logging.warning("Lightpanda open attempt %s failed: %s", attempt + 1, exc)
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
    # Keep this JS deliberately ES5/Lightpanda-friendly. The previous snapshot
    # used optional chaining and a CSS role selector that could make the whole
    # Runtime.evaluate fail, which surfaced to Python as an empty snapshot.
    expr = """(function(){
        var body=document.body;
        var text=body ? (body.innerText || body.textContent || '') : '';
        var nodes=document.getElementsByTagName('input');
        var inputs=[];
        for(var i=0;i<nodes.length;i++){
            var e=nodes[i];
            var rect=e.getBoundingClientRect ? e.getBoundingClientRect() : null;
            inputs.push({index:i,tag:e.tagName,type:e.type||'',name:e.name||'',autocomplete:e.autocomplete||'',
                placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',disabled:!!e.disabled,
                visible:!!(rect ? (rect.width||rect.height) : (e.offsetWidth||e.offsetHeight)),value:e.value||''});
        }
        var all=document.querySelectorAll('button');
        var buttons=[];
        for(var j=0;j<all.length;j++){
            var b=all[j];
            var br=b.getBoundingClientRect ? b.getBoundingClientRect() : null;
            buttons.push({index:j,text:(b.innerText||b.textContent||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim(),
                disabled:!!b.disabled,visible:!!(br ? (br.width||br.height) : (b.offsetWidth||b.offsetHeight))});
        }
        return {url:String(location.href||''),title:String(document.title||''),readyState:String(document.readyState||''),
            text:String(text).slice(0,7000),inputs:inputs,buttons:buttons};
    })()"""
    snap = _eval(tab, expr)
    if not isinstance(snap, dict):
        raise RuntimeError(f"Lightpanda snapshot returned unexpected value: {type(snap).__name__}")
    return snap


def _match(item: dict, *words: str) -> bool:
    text = " ".join(str(item.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder", "aria")).lower()
    return any(w.lower() in text for w in words)


def _set_input(tab: dict, item: dict, value: str) -> bool:
    if not value:
        return False
    payload = json.dumps({"index": item.get("index", -1), "value": str(value)})
    expr = """(function(p){
        var all=document.getElementsByTagName('input');
        var el=(p.index>=0 && p.index<all.length) ? all[p.index] : null;
        if(!el || el.disabled){
            for(var i=0;i<all.length;i++){
                var x=all[i];
                if(!x.disabled && (x.offsetWidth||x.offsetHeight) && (!x.value || x.value===p.value)){el=x;break;}
            }
        }
        if(!el)return false;
        try{el.focus();}catch(e){}
        try{
            var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
            if(d && d.set)d.set.call(el,p.value);else el.value=p.value;
        }catch(e){el.value=p.value;}
        try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}
        try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}
        return el.value===p.value;
    })(""" + payload + ")"
    return bool(_eval(tab, expr))


def _click_primary(tab: dict) -> bool:
    expr = r"""(function(){
        function norm(s){return String(s||'').replace(/\s+/g,' ').trim().toLowerCase();}
        var wanted=/^(next|continue|confirm|sign up|create account|submit|verify|finish|done)$/i;
        var buttons=document.getElementsByTagName('button');
        var fallback=null;
        for(var i=0;i<buttons.length;i++){
            var b=buttons[i];
            if(b.disabled || !(b.offsetWidth||b.offsetHeight))continue;
            var label=norm(b.innerText||b.textContent||b.getAttribute('aria-label'));
            if(wanted.test(label)){b.click();return true;}
            if(!fallback && /(next|continue|confirm|sign up|create account|verify)/i.test(label))fallback=b;
        }
        if(fallback){fallback.click();return true;}
        return false;
    })()"""
    return bool(_eval(tab, expr))


def _candidates(identity: dict) -> list[str]:
    seen=set(); out=[]
    for raw in [identity.get("selected_username"),identity.get("username"),*(identity.get("usernames") or [])]:
        value=re.sub(r"[^A-Za-z0-9._]+","_",str(raw or "").strip()).strip("._")[:30]
        if 3<=len(value)<=30 and value.lower() not in seen:
            seen.add(value.lower());out.append(value)
    return out


def _username_rejected(text: str) -> bool:
    return bool(re.search(r"(username|user name).{0,120}(not available|unavailable|already taken|taken|in use|try another)",text,re.I|re.S) or re.search(r"this username is not available|please try another username",text,re.I))


def _handle_username(tab: dict, identity: dict) -> str:
    snap=_snapshot(tab)
    item=next((i for i in snap.get("inputs",[]) if i.get("visible") and not i.get("disabled") and _match(i,"username","user name","handle","screen name")),None)
    if not item:return "username_waiting"
    candidates=_candidates(identity)
    if not candidates:
        logging.warning("Username step reached, but identity has no usable username candidates")
        return "username_waiting"
    attempted=tab.setdefault("_attempted_usernames",set())
    for candidate in candidates:
        if candidate.lower() in attempted:continue
        attempted.add(candidate.lower())
        if not _set_input(tab,item,candidate):continue
        time.sleep(0.8)
        latest=_snapshot(tab)
        if _username_rejected(str(latest.get("text",""))):
            logging.info("Username rejected: %s",candidate)
            continue
        identity["selected_username"]=candidate
        identity["username"]=candidate
        logging.info("Username selected at username step: %s",candidate)
        _click_primary(tab)
        return "username_submitted"
    return "username_waiting"


def _advance(tab: dict, credentials: dict, identity: dict) -> str:
    snap=_snapshot(tab)
    text=str(snap.get("text", "")); low=text.lower()
    inputs=[i for i in snap.get("inputs",[]) if i.get("visible") and not i.get("disabled")]
    logging.info("Signup DOM snapshot: url=%s ready=%s visible_inputs=%s", snap.get("url"), snap.get("readyState"),
                 [(i.get("index"),i.get("type"),i.get("name"),i.get("autocomplete"),i.get("placeholder"),i.get("aria")) for i in inputs])
    if snap.get("readyState")=="loading": return "waiting"
    if any(x in low for x in ("confirmation code","security code","enter the code","confirm your email","enter the 6-digit code")): return "otp_required"
    if "captcha" in low or "security check" in low: return "captcha_required"
    if any(x in low for x in ("welcome to instagram","account created","your instagram profile")): return "completed"

    email=next((i for i in inputs if _match(i,"email","e-mail","emailaddress")),None)
    if email and not str(email.get("value") or "").strip():
        value=str(credentials.get("email") or identity.get("email") or "").strip()
        if _set_input(tab,email,value):
            logging.info("Signup step: email filled")
            if _click_primary(tab): logging.info("Signup step: email submitted")
            return "progressed"

    password=next((i for i in inputs if str(i.get("type")).lower()=="password"),None)
    if password and not str(password.get("value") or "").strip():
        value=str(credentials.get("password") or identity.get("password") or "").strip()
        if _set_input(tab,password,value):
            logging.info("Signup step: password filled")
            if _click_primary(tab): logging.info("Signup step: password submitted")
            return "progressed"

    username_result=_handle_username(tab,identity)
    if username_result!="username_waiting": return username_result
    fullname=next((i for i in inputs if _match(i,"full name","fullname")),None)
    if fullname and identity.get("display_names") and not str(fullname.get("value") or "").strip():
        if _set_input(tab,fullname,str(identity["display_names"][0])):
            _click_primary(tab); return "progressed"
    if inputs:
        logging.info("Signup still waiting; visible inputs=%s",[(i.get("index"),i.get("type"),i.get("placeholder"),i.get("aria")) for i in inputs])
    else:
        logging.info("Signup still waiting; no visible input detected; url=%s",snap.get("url"))
    return "waiting"


def _signup_worker(tab: dict, credentials: dict, identity: dict):
    logging.info("Instagram signup progression worker started")
    stop=tab.get("_signup_stop")
    while stop and not stop.is_set():
        try:
            state=_advance(tab,credentials,identity); tab["signup_state"]=state
            logging.info("Instagram signup state: %s",state)
            if state in {"otp_required","captcha_required","completed"}: return
            if tab.get("_connection_dead"):
                logging.warning("Signup progression stopped: original Lightpanda CDP connection is closed"); return
        except Exception as exc:
            logging.warning("Signup progression iteration failed: %s",exc)
            if tab.get("_connection_dead"): return
        stop.wait(1.5)


def start_signup_progression(tab: dict, credentials: dict, identity: dict):
    old=tab.get("_signup_thread")
    if old and old.is_alive(): return old
    thread=threading.Thread(target=_signup_worker,args=(tab,credentials,identity),name="instagram-signup-progress",daemon=True)
    tab["_signup_thread"]=thread; thread.start(); return thread


def fill_fields(tab: dict, credentials: dict, identity: dict) -> bool:
    return _advance(tab,credentials,identity) in {"progressed","otp_required","captcha_required","completed","username_submitted"}


def submit_signup(tab: dict) -> bool:
    return _click_primary(tab)


def fill_otp(tab: dict, code: str) -> bool:
    payload=json.dumps(str(code).strip())
    expr="""(function(code){
        var all=document.getElementsByTagName('input');
        for(var i=0;i<all.length;i++){
            var el=all[i]; if(el.disabled || !(el.offsetWidth||el.offsetHeight))continue;
            var type=String(el.type||'').toLowerCase();
            var hint=(String(el.name||'')+' '+String(el.placeholder||'')+' '+String(el.getAttribute('aria-label')||'')).toLowerCase();
            if(type==='text'||type==='tel'||type==='number'||/code|otp|security|confirmation/.test(hint)){
                try{el.focus();}catch(e){}
                el.value=code;
                try{el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true));}catch(e){}
                var buttons=document.getElementsByTagName('button');
                for(var j=0;j<buttons.length;j++){
                    var b=buttons[j], label=String(b.innerText||b.textContent||b.getAttribute('aria-label')||'').trim();
                    if(!b.disabled && /^(confirm|continue|next|verify|submit)$/i.test(label)){b.click();break;}
                }
                return el.value===code;
            }
        }
        return false;
    })("""+payload+")"
    return bool(_eval(tab,expr))


def inspect_state(tab: dict) -> dict:
    try:
        snap=_snapshot(tab); text=str(snap.get("text","")).lower()
        if any(x in text for x in ("confirmation code","security code","enter the code","confirm your email","enter the 6-digit code")): status="otp_required"
        elif "captcha" in text or "security check" in text: status="captcha_required"
        elif any(x in text for x in ("welcome to instagram","account created","your instagram profile")): status="completed"
        else: status=tab.get("signup_state","waiting")
        return {"status":status,"url":snap.get("url", ""),"title":snap.get("title", "")}
    except Exception as exc:
        return {"status":"waiting","url":"","title":"","error":str(exc)[:300]}


def start_signup(credentials: dict, identity: dict):
    tab=open_signup(); start_signup_progression(tab,credentials,identity); return tab,True


__all__=[name for name in globals() if not name.startswith("_")]+["_evaluate"]
