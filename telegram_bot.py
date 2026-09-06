"""Telegram control plane for the safe Instagram browser-assist runtime.

The bot prepares and tracks workflows. CAPTCHA/OTP/verification are always manual.
Set TELEGRAM_BOT_TOKEN in the hosting provider's secret environment.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from ig_bot import generate_identity
from stats import format_stats, record

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""


def tg(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not API:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    response = requests.post(f"{API}/{method}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🆕 Create Account", "callback_data": "create"}, {"text": "🔐 Login", "callback_data": "login"}],
        [{"text": "🤖 Generate Identity", "callback_data": "identity"}, {"text": "📊 Stats", "callback_data": "stats"}],
    ]}


def answer_callback(callback_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": False})


def handle_callback(callback: dict[str, Any]) -> None:
    data = callback.get("data", "")
    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    answer_callback(callback_id, "Processing…")

    if data == "stats":
        tg("sendMessage", {"chat_id": chat_id, "text": format_stats(), "parse_mode": "Markdown", "reply_markup": keyboard()})
        return

    if data == "identity":
        identity = generate_identity()
        if not identity:
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Check HF_TOKEN."})
            return
        text = "🤖 *Identity Preview*\n\n" + json_identity(identity)
        tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "🔄 Generate Again", "callback_data": "identity"}, {"text": "🆕 Use for Signup", "callback_data": "create"}], [{"text": "📊 Stats", "callback_data": "stats"}]]}})
        return

    if data == "create":
        record("signup_started")
        identity = generate_identity()
        if not identity:
            record("signup_failed")
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Could not generate signup details."})
            return
        text = "🆕 *Review before Create*\n\n" + json_identity(identity) + "\n\nPress *Confirm & Create* to continue."
        tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "✅ Confirm & Create", "callback_data": "confirm_create"}], [{"text": "🔄 Regenerate", "callback_data": "create"}]]}})
        return

    if data == "confirm_create":
        record("signup_confirmed")
        tg("sendMessage", {"chat_id": chat_id, "text": "🌐 Signup session requested. Open the Lightpanda browser session and complete any CAPTCHA/OTP/verification manually.\n\n⚠️ The bot does not solve or bypass verification challenges."})
        return

    if data == "login":
        record("login_started")
        tg("sendMessage", {"chat_id": chat_id, "text": "🔐 Login session requested. Credentials must be supplied securely to the browser runtime; CAPTCHA/2FA/challenges remain manual."})
        return


def json_identity(identity: dict[str, Any]) -> str:
    names = identity.get("display_names", [])
    usernames = identity.get("usernames", [])
    bios = identity.get("bios", [])
    return "*Names:* " + ", ".join(map(str, names[:3])) + "\n*Usernames:* " + ", ".join(map(str, usernames[:5])) + "\n*Bios:* " + " | ".join(map(str, bios[:3]))


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    offset = 0
    while True:
        updates = tg("getUpdates", {"timeout": 25, "offset": offset}).get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                elif "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    if update["message"]["text"].strip() in ("/start", "/menu"):
                        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Instagram Assistant*\nChoose an action:", "parse_mode": "Markdown", "reply_markup": keyboard()})
            except Exception as exc:
                tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Operation failed: {type(exc).__name__}"})
        time.sleep(0.2)


if __name__ == "__main__":
    main()
