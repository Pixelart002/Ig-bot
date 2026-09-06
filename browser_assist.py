"""Lightpanda/CDP manual-assist launcher.

This helper opens Instagram's signup page in a CDP-compatible browser.
It intentionally does not solve CAPTCHA/OTP or bypass anti-bot controls.
"""

import json
import os
import sys
import time
from urllib.parse import quote

import requests

CDP_URL = os.getenv("CDP_URL", "http://127.0.0.1:9222")
SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"


def cdp_version() -> dict:
    response = requests.get(f"{CDP_URL}/json/version", timeout=5)
    response.raise_for_status()
    return response.json()


def open_signup() -> None:
    """Create a CDP tab pointing at Instagram signup."""
    response = requests.get(
        f"{CDP_URL}/json/new?{quote(SIGNUP_URL, safe=':/?=&')}",
        timeout=10,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


def main() -> int:
    try:
        version = cdp_version()
    except requests.RequestException as exc:
        print(f"CDP browser is not reachable at {CDP_URL}: {exc}", file=sys.stderr)
        print("Start a CDP-compatible browser such as Lightpanda on port 9222 first.", file=sys.stderr)
        return 1

    print(f"Connected: {version.get('Browser', 'unknown browser')}")
    open_signup()
    print("Signup page opened. Complete CAPTCHA/OTP/verification manually if requested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
