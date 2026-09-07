"""Deterministic Instagram signup progression on one Lightpanda CDP session."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import browser_assist_v2 as cdp

EMAIL_STEP = "email"
OTP_STEP = "otp"
PASSWORD_STEP = "password"
PROFILE_STEP = "profile"
DONE_STEP = "done"


def _visible_inputs(snap: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in snap.get("inputs", []) if i.get("visible") and not i.get("disabled")]


def _is_email(i: dict[str, Any]) -> bool:
    text = " ".join(str(i.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder", "aria")).lower()
    return str(i.get("type", "")).lower() == "email" or any(x in text for x in ("email", "e-mail", "emailaddress"))


def _is_username(i: dict[str, Any]) -> bool:
    text = " ".join(str(i.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder", "aria")).lower()
    return any(x in text for x in ("username", "user name", "handle", "screen name"))


def _is_name(i: dict[str, Any]) -> bool:
    text = " ".join(str(i.get(k, "")) for k in ("name", "autocomplete", "placeholder", "aria")).lower()
    return any(x in text for x in ("full name", "fullname", "display name"))


def _value(i: dict[str, Any]) -> str:
    return str(i.get("value") or "").strip()


def _signature(snap: dict[str, Any]) -> tuple:
    inputs = tuple((i.get("index"), i.get("type"), i.get("placeholder"), i.get("aria"), _value(i)) for i in _visible_inputs(snap))
    buttons = tuple(str(b.get("text") or "").strip().lower() for b in snap.get("buttons", []) if b.get("visible") and not b.get("disabled"))
    return (snap.get("url"), snap.get("readyState"), inputs, buttons, str(snap.get("text", ""))[:1500])


def _fill_verify(tab: dict[str, Any], item: dict[str, Any], value: str) -> bool:
    value = str(value or "").strip()
    if not value or not cdp._set_input(tab, item, value):
        return False
    latest = cdp._snapshot(tab)
    match = next((i for i in latest.get("inputs", []) if i.get("index") == item.get("index")), None)
    ok = bool(match and _value(match) == value)
    logging.info("Signup field verified index=%s type=%s ok=%s", item.get("index"), item.get("type"), ok)
    return ok


def _click_action(tab: dict[str, Any]) -> bool:
    return bool(cdp._eval(tab, r'''(function(){
function n(s){return String(s||'').replace(/\s+/g,' ').trim().toLowerCase();}
function ok(s){return /^(next|continue|confirm|sign up|create account|submit|verify|finish|done|complete|register)$/i.test(n(s));}
function fire(e){try{e.focus();}catch(x){}try{e.click();return true;}catch(x){}try{e.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));return true;}catch(x){return false;}}
var bs=document.getElementsByTagName('button');
for(var i=0;i<bs.length;i++){var b=bs[i];if(b.disabled||!(b.offsetWidth||b.offsetHeight))continue;if(ok(b.innerText||b.textContent||b.getAttribute('aria-label')))return fire(b);}
var rs=document.querySelectorAll?document.querySelectorAll('[role="button"]'):[];
for(var j=0;j<rs.length;j++){var r=rs[j];if(r.getAttribute('aria-disabled')==='true'||!(r.offsetWidth||r.offsetHeight))continue;if(ok(r.innerText||r.textContent||r.getAttribute('aria-label')))return fire(r);}
return false;})()'''))


def _wait_change(tab: dict[str, Any], before: tuple, timeout: float = 6.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(.35)
        if _signature(cdp._snapshot(tab)) != before:
            return True
    return False


def _username_rejected(text: str) -> bool:
    return bool(re.search(r"(username|user name).{0,160}(not available|unavailable|already taken|taken|in use|try another)", text, re.I | re.S) or re.search(r"this username is not available|please try another username", text, re.I))


def _username(tab: dict[str, Any], identity: dict[str, Any]) -> str:
    snap = cdp._snapshot(tab)
    item = next((i for i in _visible_inputs(snap) if _is_username(i)), None)
    if not item:
        return "waiting"
    candidates=[]; seen=set()
    for raw in [identity.get("selected_username"), identity.get("username"), *(identity.get("usernames") or [])]:
        value=re.sub(r"[^A-Za-z0-9._]+","_",str(raw or "").strip()).strip("._")[:30]
        if 3 <= len(value) <= 30 and value.lower() not in seen:
            seen.add(value.lower()); candidates.append(value)
    attempted=tab.setdefault("_attempted_usernames",set())
    for candidate in candidates:
        if candidate.lower() in attempted: continue
        if not _fill_verify(tab,item,candidate): continue
        attempted.add(candidate.lower())
        latest=cdp._snapshot(tab)
        if _username_rejected(str(latest.get("text", ""))): continue
        identity["selected_username"]=candidate; identity["username"]=candidate
        before=_signature(latest)
        if _click_action(tab): _wait_change(tab,before); return "progressed"
    return "waiting"


def advance(tab: dict[str, Any], credentials: dict[str, Any], identity: dict[str, Any]) -> str:
    snap=cdp._snapshot(tab)
    low=str(snap.get("text", "")).lower()
    inputs=_visible_inputs(snap)
    logging.info("Signup deterministic DOM: url=%s ready=%s inputs=%s buttons=%s", snap.get("url"), snap.get("readyState"), [(i.get("index"),i.get("type"),i.get("name"),i.get("autocomplete"),i.get("placeholder"),i.get("aria"),bool(_value(i))) for i in inputs], [str(b.get("text") or "").strip() for b in snap.get("buttons",[]) if b.get("visible") and not b.get("disabled")])
    # Lightpanda may report document.readyState=loading while the usable form
    # controls are already exposed. Never block a real form just because the
    # document lifecycle flag has not settled yet.
    if snap.get("readyState") == "loading" and not inputs:
        return "waiting"
    if any(x in low for x in ("confirmation code","security code","enter the code","confirm your email","enter the 6-digit code")):
        tab["signup_step"]=OTP_STEP; return "otp_required"
    if "captcha" in low or "security check" in low:
        tab["signup_step"]="manual_verification"; return "captcha_required"
    if any(x in low for x in ("welcome to instagram","account created","your instagram profile")):
        tab["signup_step"]=DONE_STEP; return "completed"

    step=tab.setdefault("signup_step",EMAIL_STEP)

    if step == EMAIL_STEP:
        email=next((i for i in inputs if _is_email(i)), None)
        # Instagram/Lightpanda can expose the email control as a generic text
        # input with no name/placeholder/autocomplete metadata. Since this is
        # the explicit EMAIL_STEP, safely fall back to the first non-password,
        # non-username text-like control instead of skipping to password.
        if not email:
            email=next((i for i in inputs if str(i.get("type","")).lower() in ("text","email","tel") and not _is_username(i)), None)
            if email:
                logging.info("Signup email field matched by generic text-input fallback: index=%s", email.get("index"))
        if not email: return "waiting"
        value=str(credentials.get("email") or identity.get("email") or "").strip()
        if _value(email) != value and not _fill_verify(tab,email,value): return "waiting"
        latest=cdp._snapshot(tab); before=_signature(latest)
        if _click_action(tab):
            tab["signup_step"]="email_transition"
            _wait_change(tab,before)
            return "progressed"
        return "waiting"

    if step == "email_transition":
        if any(x in low for x in ("confirmation code","security code","enter the code","confirm your email","enter the 6-digit code")):
            tab["signup_step"]=OTP_STEP; return "otp_required"
        email=next((i for i in inputs if _is_email(i)), None)
        if email is not None:
            logging.info("Signup waiting at email transition: email control still visible")
            return "waiting"
        if any(str(i.get("type")).lower()=="password" for i in inputs):
            tab["signup_step"]=PASSWORD_STEP; return "waiting"
        logging.info("Signup waiting at email transition: no password/profile controls detected yet")
        tab["signup_step"]=PROFILE_STEP; return "waiting"

    if step == OTP_STEP: return "otp_required"

    if step == PASSWORD_STEP:
        password=next((i for i in inputs if str(i.get("type")).lower()=="password"),None)
        if not password:return "waiting"
        value=str(credentials.get("password") or identity.get("password") or "").strip()
        if _value(password) != value and not _fill_verify(tab,password,value): return "waiting"
        latest=cdp._snapshot(tab); before=_signature(latest)
        if _click_action(tab):
            tab["signup_step"]="profile_transition"
            _wait_change(tab,before)
            return "progressed"
        return "waiting"

    if step == "profile_transition":
        if any(_is_username(i) or _is_name(i) for i in inputs): tab["signup_step"]=PROFILE_STEP
        else: return "waiting"
        step=PROFILE_STEP

    if step == PROFILE_STEP:
        username_result=_username(tab,identity)
        if username_result != "waiting": return username_result
        snap=cdp._snapshot(tab); name=next((i for i in _visible_inputs(snap) if _is_name(i)),None)
        names=identity.get("display_names") or []
        if name and names and not _value(name):
            if _fill_verify(tab,name,str(names[0])):
                latest=cdp._snapshot(tab); before=_signature(latest)
                if _click_action(tab): _wait_change(tab,before); return "progressed"
        return "waiting"

    return "waiting"
