"""Lightpanda/CDP signup assistant.

Opens Instagram signup and fills safe profile fields from environment variables.
CAPTCHA, OTP, verification, and anti-bot controls remain manual.
"""

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


def open_signup() -> dict:
    """Create a CDP tab pointing at Instagram signup."""
    response = requests.get(
        f"{CDP_URL}/json/new?{quote(SIGNUP_URL, safe=':/?=&')}",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def cdp_call(ws, method: str, params: dict | None = None, request_id: int = 1) -> dict:
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    deadline = time.time() + 15
    while time.time() < deadline:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            return message
    raise TimeoutError(f"Timed out waiting for CDP response: {method}")


def fill_fields(tab: dict) -> None:
    email = os.getenv("IG_EMAIL")
    password = os.getenv("IG_PASSWORD")
    username = os.getenv("IG_USERNAME")
    full_name = os.getenv("IG_FULL_NAME", "")

    if not email or not password or not username:
        logging.info("IG_EMAIL, IG_USERNAME and IG_PASSWORD are required for automatic field filling.")
        logging.info("No credentials are stored in the repository; provide them as environment variables.")
        return

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        logging.error("CDP tab did not provide a websocket debugger URL.")
        return

    ws = create_connection(ws_url, timeout=15)
    try:
        # Give Instagram time to render its signup form.
        time.sleep(3)
        expression = """
        (values) => {
          const setValue = (selector, value) => {
            const el = document.querySelector(selector);
            if (!el || !value) return false;
            const setter = Object.getOwnPropertyDescriptor(
              HTMLInputElement.prototype, 'value'
            )?.set;
            setter?.call(el, value);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
          };
          return {
            email: setValue('input[name="emailOrPhone"], input[name="email"]', values.email),
            password: setValue('input[name="password"]', values.password),
            username: setValue('input[name="username"]', values.username),
            fullName: values.fullName
              ? setValue('input[name="fullName"]', values.fullName)
              : false
          };
        }
        """
        result = cdp_call(
            ws,
            "Runtime.evaluate",
            {
                "expression": f"({expression})({json.dumps({'email': email, 'password': password, 'username': username, 'fullName': full_name})})",
                "returnByValue": True,
            },
        )
        logging.info("Signup fields filled: %s", result.get("result", {}).get("result", {}).get("value"))
    finally:
        ws.close()


def main() -> int:
    try:
        version = cdp_version()
        tab = open_signup()
        print(f"Connected: {version.get('Browser', 'unknown browser')}")
        print(f"Signup tab: {tab.get('url', SIGNUP_URL)}")
        fill_fields(tab)
        print("CAPTCHA/OTP/verification and final submission remain manual.")
        return 0
    except (requests.RequestException, OSError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Signup assistant failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
