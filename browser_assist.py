"""Lightpanda/CDP signup assistant.

Safe profile fields may be filled automatically. CAPTCHA, OTP, verification,
and anti-bot controls remain manual.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
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


def fill_fields(tab: dict, identity: dict | None = None) -> bool:
    email = os.getenv("IG_EMAIL")
    password = os.getenv("IG_PASSWORD")
    username = ((identity or {}).get("usernames") or [None])[0] or os.getenv("IG_USERNAME")
    full_name = ((identity or {}).get("display_names") or [None])[0] or os.getenv("IG_FULL_NAME", "")
    if not email or not password or not username:
        logging.error("IG_EMAIL, IG_USERNAME and IG_PASSWORD are required for automatic field filling.")
        return False
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        logging.error("CDP tab did not provide a websocket debugger URL.")
        return False
    ws = create_connection(ws_url, timeout=15)
    try:
        time.sleep(3)
        expression = """
        (values) => {
          const setValue = (selector, value) => {
            const el = document.querySelector(selector);
            if (!el || !value) return false;
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
            setter?.call(el, value);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
          };
          return {
            email: setValue('input[name="emailOrPhone"], input[name="email"]', values.email),
            password: setValue('input[name="password"]', values.password),
            username: setValue('input[name="username"]', values.username),
            fullName: values.fullName ? setValue('input[name="fullName"]', values.fullName) : false
          };
        }
        """
        values = {"email": email, "password": password, "username": username, "fullName": full_name}
        result = cdp_call(ws, "Runtime.evaluate", {"expression": f"({expression})({json.dumps(values)})", "returnByValue": True})
        filled = result.get("result", {}).get("result", {}).get("value", {})
        logging.info("Signup fields filled: %s", filled)
        return bool(filled.get("email") and filled.get("password") and filled.get("username"))
    finally:
        ws.close()


def inspect_state(tab: dict) -> dict:
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("CDP tab has no websocket debugger URL")
    ws = create_connection(ws_url, timeout=15)
    try:
        result = cdp_call(ws, "Runtime.evaluate", {"expression": "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,4000)})", "returnByValue": True})
        value = result.get("result", {}).get("result", {}).get("value", "{}")
        data = json.loads(value)
        text = data.get("text", "").lower()
        if any(x in text for x in ("security code", "confirmation code", "enter the code", "captcha", "confirm your email")):
            status = "verification_required"
        elif "welcome to instagram" in text:
            status = "completed"
        else:
            status = "waiting"
        return {"status": status, "url": data.get("url", ""), "title": data.get("title", "")}
    finally:
        ws.close()


def start_signup(identity: dict | None = None) -> tuple[dict, bool]:
    cdp_version()
    tab = open_signup()
    filled = fill_fields(tab, identity)
    return tab, filled


def main() -> int:
    try:
        version = cdp_version()
        tab, filled = start_signup()
        print(f"Connected: {version.get('Browser', 'unknown browser')}")
        print(f"Signup tab: {tab.get('url', SIGNUP_URL)}")
        print(f"Form fields filled: {filled}")
        print("CAPTCHA/OTP/verification and final submission remain manual.")
        return 0
    except (requests.RequestException, OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Signup assistant failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
