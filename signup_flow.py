"""Deterministic Instagram signup progression on one Lightpanda CDP session.

The flow is intentionally stateful: it never fills a later field merely because
that field happens to exist in the DOM. Each screen is handled as:
fill -> verify value -> locate enabled action -> click -> wait for DOM change.
CAPTCHA/security checks are surfaced for manual handling.
"""
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
USERNAME_STEP = "username"
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


def _snapshot_signature(snap: dict[str, Any]) -> tuple:
    inputs = tuple((i.get("index"), i.get("type"), i.get("placeholder"), i.get("aria"), bool(_value(i))) for i in _visible_inputs(snap))
    buttons = tuple(str(b.get("text") or "").strip().lower() for b in snap.get("buttons", []) if b.get("visible") and not b.get("disabled"))
    return (snap.get("url"), snap.get("readyState"), inputs, buttons, str(snap.get("text", ""))[:1200])


def _fill_and_verify(tab: dict[str, Any], item: dict[str, Any], value: str) -> bool:
    value = str(value or "").strip()
    if not value:
        return False
    if not cdp._set_input(tab, item, value):
        return False
    check = cdp._snapshot(tab)
    matched = next((i for i in check.get("inputs", []) if i.get("index") == item.get("index")), None)
    ok = bool(matched and _value(matched) == value)
    logging.info("Signup field verified: index=%s type=%s ok=%s", item.get("index"), item.get("type"), ok)
    return ok


def _action_label(text: str) -> bool:
    return bool(re.fullmatch(r"next|continue|confirm|sign up|create account|submit|verify|finish|done|complete|register", re.sub(r"\s+", " ", text or "").strip().lower()))


def _click_action(tab: dict[str, Any]) -> bool:
    # Prefer an enabled visible button whose complete label represents the
    # current form action. Do not click arbitrary buttons such as Log in.
    return bool(cdp._eval(tab, r'''(function(){
function norm(s){return String(s||'').replace(/\s+/g,' ').trim().toLowerCase();}
function ok(s){return /^(next|continue|confirm|sign up|create account|submit|verify|finish|done|complete|register)$/i.test(norm(s));}
function fire(el){try{el.focus();}catch(e){}try{el.click();return true;}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));return true;}catch(e){return false;}}
var bs=document.getElementsByTagName('button');
for(var i=0;i<bs.length;i++){var b=bs[i];if(b.disabled||!(b.offsetWidth||b.offsetHeight))continue;var t=norm(b.innerText||b.textContent||b.getAttribute('aria-label'));if(ok(t))return fire(b);}
var rs=document.querySelectorAll?document.querySelectorAll('[role="button"]'):[];
for(var j=0;j<rs.length;j++){var r=rs[j];if(r.getAttribute('aria-disabled')==='true'||!(r.offsetWidth||r.offsetHeight))continue;var rt=norm(r.innerText||r.textContent||r.getAttribute('aria-label'));if(ok(rt))return fire(r);}
return false;})()'''))


def _wait_after_click(tab: dict[str, Any], before: tuple, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.35)
        snap = cdp._snapshot(tab)
        if _snapshot_signature(snap) != before:
            logging.info("Signup screen changed after action: url=%s", snap.get("url"))
            return True
    logging.info("Signup action clicked but DOM did not visibly change within %.1fs", timeout)
    return False


def _username_rejected(text: str) -> bool:
    return bool(re.search(r"(username|user name).{0,160}(not available|unavailable|already taken|taken|in use|try another)", text, re.I | re.S) or re.search(r"this username is not available|please try another username", text, re.I))


def _profile_step(tab: dict[str, Any], credentials: dict[str, Any], identity: dict[str, Any], snap: dict[str, Any]) -> str:
    inputs = _visible_inputs(snap)
    username = next((i for i in inputs if _is_username(i)), None)
    if username:
        candidates=[]
        seen=set()
        for raw in [identity.get("selected_username"), identity.get("username"), *(identity.get("usernames") or [])]:
            value=re.sub(r"[^A-Za-z0-9._]+", "_", str(raw or "").strip()).strip("._")[:30]
            if 3 <= len(value) <= 30 and value.lower() not in seen:
                seen.add(value.lower()); candidates.append(value)
        attempted=tab.setdefault("_attempted_usernames", set())
        for candidate in candidates:
            if candidate.lower() in attempted: continue
            if _fill_and_verify(tab, username, candidate):
                attempted.add(candidate.lower())
                latest=cdp._snapshot(tab)
                if _username_rejected(str(latest.get("text", ""))):
                    continue
                identity["selected_username"]=candidate
                identity["username"]=candidate
                before=_snapshot_signature(latest)
                if _click_action(tab):
                    _wait_after_click(tab, before)
                    tab["signup_step"]=PROFILE_STEP
                    return "progressed"
                return "waiting"
        return "waiting"

    name=next((i for i in inputs if _is_name(i)), None)
    display_names=identity.get("display_names") or []
    if name and display_names and not _value(name):
        if _fill_and_verify(tab, name, str(display_names[0])):
            latest=cdp._snapshot(tab); before=_snapshot_signature(latest)
            if _click_action(tab): _wait_after_click(tab, before)
            return "progressed"

    return "waiting"


def advance(tab: dict[str, Any], credentials: dict[str, Any], identity: dict[str, Any]) -> str:
    snap=cdp._snapshot(tab)
    text=str(snap.get("text", "")); low=text.lower()
    if snap.get("readyState") == "loading": return "waiting"
    if any(x in low for x in ("confirmation code", "security code", "enter the code", "confirm your email", "enter the 6-digit code")):
        tab["signup_step"]=OTP_STEP
        return "otp_required"
    if "captcha" in low or "security check" in low:
        tab["signup_step"]="manual_verification"
        return "captcha_required"
    if any(x in low for x in ("welcome to instagram", "account created", "your instagram profile")):
        tab["signup_step"]=DONE_STEP
        return "completed"

    step=tab.setdefault("signup_step", EMAIL_STEP)
    inputs=_visible_inputs(snap)

    # IMPORTANT: password may already exist in Instagram's DOM while the email
    # screen is active. The explicit state prevents skipping email submission.
    if step == EMAIL_STEP:
        email=next((i for i in inputs if _is_email(i)), None)
        if not email:
            return "waiting"
        value=str(credentials.get("email") or identity.get("email") or "").strip()
        if not _value(email):
            if not _fill_and_verify(tab, email, value): return "waiting"
            snap=cdp._snapshot(tab)
        elif _value(email) != value:
            if not _fill_and_verify(tab, email, value): return "waiting"
            snap=cdp._snapshot(tab)
        before=_snapshot_signature(snap)
        if _click_action(tab):
            tab["signup_step"]="awaiting_email_transition"
            _wait_after_click(tab, before)
            return "progressed"
        logging.info("Signup email filled and verified; primary submit button not available yet")
        return "waiting"

    if step == "awaiting_email_transition":
        # Rescan until Instagram exposes the next screen. Never fill password
        # during this transition merely because its input is present.
        if any(x in low for x in ("confirmation code", "security code", "enter the code", "confirm your email", "enter the 6-digit code")):
            tab["signup_step"]=OTP_STEP; return "otp_required"
        email=next((i for i in inputs if _is_email(i)), None)
        if email is not None and not _value(email):
            tab["signup_step"]=EMAIL_STEP; return "waiting"
        if email is None:
            tab["signup_step"]=PASSWORD_STEP if any(str(i.get("type")).lower()=="password" for i in inputs) else PROFILE_STEP
            step=tab["signup_step"]
        else:
            return "waiting"

    if step == OTP_STEP:
        return "otp_required"

    if step == PASSWORD_STEP:
        password=next((i for i in inputs if str(i.get("type")).lower()=="password"), None)
        if not password: return "waiting"
        value=str(credentials.get("password") or identity.get("password") or "").strip()
        if not _value(password):
            if not _fill_and_verify(tab,password,value): return "waiting"
        elif _value(password) != value:
            if not _fill_and_verify(tab,password,value): return "waiting"
        latest=cdp._snapshot(tab); before=_snapshot_signature(latest)
        if _click_action(tab):
            tab["signup_step"]="profile_transition"
            _wait_after_click(tab,before)
            return "progressed"
        logging.info("Signup password filled and verified; primary submit button not available yet")
        return "waiting"

    if step == "profile_transition":
        if any(str(i.get("type")).lower()=="password" for i in inputs):
            tab["signup_step"]=PASSWORD_STEP; return "waiting"
        tab["signup_step"]=PROFILE_STEP
        step=PROFILE_STEP

    if step in (PROFILE_STEP, USERNAME_STEP):
        return _profile_step(tab,credentials,identity,snap)

    return "waiting"
