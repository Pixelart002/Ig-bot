"""Telegram control plane for the Lightpanda signup/login assistant.

CAPTCHA and anti-bot controls remain manual. User-supplied OTP is handed to
Lightpanda only to fill the active verification field and continue the flow.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Any

import requests

from browser_assist import fill_otp, inspect_state, start_signup
from ig_bot import generate_identity
from stats import format_stats, record
from verification_bridge import start_bridge
from workflow import clear, create, get

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
PUBLIC_BASE_URL = os.getenv("VERIFICATION_BASE_URL", os.getenv("PUBLIC_BASE_URL", "")).rstrip("/")
LOGIN_URL = "https://www.instagram.com/accounts/login/"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
OTP_RE = re.compile(r"^[A-Za-z0-9]{4,32}$")


def telegram_webhook_secret() -> str:
    """Derive a Telegram-accepted secret without storing another credential."""
    if not TOKEN:
        return ""
    return hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()


def tg(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not API:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    response = requests.post(f"{API}/{method}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_ids(name: str) -> set[str]:
    return {x.strip() for x in os.getenv(name, "").split(",") if x.strip()}


def allowed(chat_id: int) -> bool:
    ids = parse_ids("TELEGRAM_ALLOWED_USER_IDS")
    return not ids or str(chat_id) in ids


def admin_ids() -> set[str]:
    return parse_ids("SUPER_ADMIN_USER_IDS")


def audit(chat_id: int, action: str, status: str, identity: dict[str, Any] | None = None) -> None:
    ids = admin_ids()
    if not ids:
        return
    username = str((identity or {}).get("usernames", ["—"])[0])
    name = str((identity or {}).get("display_names", ["—"])[0])
    dob = str((identity or {}).get("date_of_birth") or "—")
    text = ("👁 *Super Admin Activity*\n\n" f"👤 User ID: `{chat_id}`\n" f"⚙️ Action: *{action}*\n" f"📌 Status: *{status}*\n" f"👨 Name: `{name}`\n" f"🔹 Username: `{username}`\n" f"🎂 DOB: `{dob}`\n" "🔐 Password: `••••••••`")
    for admin_id in ids:
        try:
            tg("sendMessage", {"chat_id": int(admin_id), "text": text, "parse_mode": "Markdown"})
        except (requests.RequestException, ValueError):
            pass


def keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🆕 Create Account", "callback_data": "create"}, {"text": "🔐 Login", "callback_data": "login"}],
            [{"text": "🤖 Generate Identity", "callback_data": "identity"}, {"text": "📊 Stats", "callback_data": "stats"}],
        ]
    }

