"""Lightpanda/CDP browser workflow helpers.

Account credentials are supplied per workflow and are never written to the repo.
CAPTCHA, OTP, verification, and anti-bot controls remain manual.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from typing import Any
from urllib.parse import quote

import requests
from websocket import create_connection

CDP_URL = os.getenv("CDP_URL", "http://127.0.0.1:9222")
SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def cdp_version() -> dict:
    response = requests.get(f"{CDP_URL}/json/version", timeout=5)
    response.raise_for_status()
    return response.json()


def open_url(url: str) -> dict:
    response = requests.get(f"{CDP_URL}/json/new?{quote(url, safe=':/?=&')}", timeout=10)
    response.raise_for_status()
    return response.json()


def open_signup() -> dict:
    return open_url(SIGNUP_URL)


def cdp_call(ws, method: str, params: dict | None = None, request_id: int = 1) -> dict:
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    deadline = time.time() + 15
    while time.time() < deadline:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            return message
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def _evaluate(tab: dict, expression: str) -> Any:
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("CDP tab has no websocket debugger URL")
    ws = create_connection(ws_url, timeout=15)
    try:
        result = cdp_call(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result.get("result", {}).get("result", {}).get("value")
    finally:
        ws.close()


def fill_fields(tab: dict, credentials: dict[str, str] | None = None, identity: dict[str, Any] | None = None) -> bool:
    credentials = credentials or {}
    email = credentials.get("email") or os.getenv("IG_EMAIL")
    password = credentials.get("password") or os.getenv("IG_PASSWORD")
    username = credentials.get("username")
    full_name = credentials.get("full_name", "")
    dob = (identity or {}).get("date_of_birth") or credentials.get("date_of_birth")

    if identity:
        username = username or ((identity.get("usernames") or [None])[0])
        full_name = full_name or ((identity.get("display_names") or [None])[0] or "")

    if not email or not password or not username:
        logging.error("Per-account email, password and username are required.")
        return False

    expression = """
    (values) => {
      const setInput = (selector, value) => {
        const el = document.querySelector(selector);
        if (!el || !value) return false;
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
        setter?.call(el, value);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
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
      const result = {
        email: setInput('input[name="emailOrPhone"], input[name="email"]', values.email),
        password: setInput('input[name="password"]', values.password),
        username: setInput('input[name="username"]', values.username),
        fullName: values.fullName ? setInput('input[name="fullName"]', values.fullName) : false,
        month: setSelect(['select[name="month"]','select[aria-label*="Month" i]'], month, [monthName, month.padStart(2,'0')]),
        day: setSelect(['select[name="day"]','select[aria-label*="Day" i]'], day, [day.padStart(2,'0')]),
        year: setSelect(['select[name="year"]','select[aria-label*="Year" i]'], year, [])
      };
      return result;
    }
    """
    values = {"email": email, "password": password, "username": str(username), "fullName": str(full_name), "dob": str(dob or "")}
    result = _evaluate(tab, f"({expression})({json.dumps(values)})")
    logging.info("Signup fields filled: %s", result)
    return bool(result and result.get("email") and result.get("password") and result.get("username"))


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
    filled = fill_fields(tab, credentials, identity)
    return tab, filled


def main() -> int:
    try:
        version = cdp_version()
        credentials = {"email": os.getenv("IG_EMAIL", ""), "password": os.getenv("IG_PASSWORD", ""), "username": os.getenv("IG_USERNAME", ""), "full_name": os.getenv("IG_FULL_NAME", "")}
        tab, filled = start_signup(credentials)
        print(f"Connected: {version.get('Browser', 'unknown browser')}")
        print(f"Signup tab: {tab.get('url', SIGNUP_URL)}")
        print(f"Form fields filled: {filled}")
        print("CAPTCHA/OTP/verification remain manual.")
        return 0
    except (requests.RequestException, OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Signup assistant failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
