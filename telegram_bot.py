"""Telegram control plane for the safe Instagram browser-assist runtime.

CAPTCHA/OTP/verification remain manual. Set TELEGRAM_BOT_TOKEN in hosting secrets.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

import requests

from ig_bot import generate_identity
from stats import format_stats, record

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
LOGIN_URL = "https://www.instagram.com/accounts/login/"


def tg(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not API:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    response = requests.post(f"{API}/{method}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": "🆕 Create Account", "callback_data": "create"},
        {"text": "🔐 Login", "callback_data": "login"}],
        [{"text": "🤖 Generate Identity", "callback_data": "identity"},
         {"text": "📊 Stats", "callback_data": "stats"}]]}


def answer_callback(callback_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": False})


def identity_text(identity: dict[str, Any]) -> str:
    return ("*Names:* " + ", ".join(map(str, identity.get("display_names", [])[:3]))
            + "\n*Usernames:* " + ", ".join(map(str, identity.get("usernames", [])[:5]))
            + "\n*Bios:* " + " | ".join(map(str, identity.get("bios", [])[:3])))


def launch_browser_assist() -> tuple[bool, str]:
    try:
        p = subprocess.run([sys.executable, "browser_assist.py"], capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stdout or p.stderr).strip()[-1600:]
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def handle_callback(callback: dict[str, Any]) -> None:
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    answer_callback(callback["id"], "Processing…")

    if data == "stats":
        tg("sendMessage", {"chat_id": chat_id, "text": format_stats(), "parse_mode": "Markdown", "reply_markup": keyboard()})
        return

    if data == "identity":
        identity = generate_identity()
        if not identity:
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Check HF_TOKEN."})
            return
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Identity Preview*\n\n" + identity_text(identity), "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "🔄 Generate Again", "callback_data": "identity"}, {"text": "🆕 Use for Signup", "callback_data": "create"}]]}})
        return

    if data == "create":
        record("signup_started")
        identity = generate_identity()
        if not identity:
            record("signup_failed")
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Could not generate signup details."})
            return
        tg("sendMessage", {"chat_id": chat_id, "text": "🆕 *Review before Create*\n\n" + identity_text(identity) + "\n\nPress *Confirm & Create* to continue.", "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "✅ Confirm & Create", "callback_data": "confirm_create"}], [{"text": "🔄 Regenerate", "callback_data": "create"}]]}})
        return

    if data == "confirm_create":
        record("signup_confirmed")
        ok, output = launch_browser_assist()
        if ok:
            record("signup_browser_started")
            text = "🌐 *Signup browser started.*\n\nComplete the remaining signup action manually. CAPTCHA/OTP/verification must be completed by you.\n\n" + (output or "Lightpanda/CDP session started.")
        else:
            record("signup_failed")
            text = "❌ Browser assistant could not start.\n\n" + output
        tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "📊 Stats", "callback_data": "stats"}], [{"text": "🆕 Create Again", "callback_data": "create"}]]}})
        return

    if data == "login":
        record("login_started")
        tg("sendMessage", {"chat_id": chat_id, "text": f"🔐 *Login*\n\nLogin page: {LOGIN_URL}\n\nUse the secure browser/runtime for credentials. CAPTCHA, 2FA and verification remain manual.", "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "📊 Stats", "callback_data": "stats"}]]}})


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    offset = 0
    while True:
        for update in tg("getUpdates", {"timeout": 25, "offset": offset}).get("result", []):
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                elif "message" in update and update["message"].get("text", "").strip() in ("/start", "/menu"):
                    tg("sendMessage", {"chat_id": update["message"]["chat"]["id"], "text": "🤖 *Instagram Assistant*\nChoose an action:", "parse_mode": "Markdown", "reply_markup": keyboard()})
            except Exception as exc:
                tg("sendMessage", {"chat_id": update.get("message", {}).get("chat", {}).get("id"), "text": f"❌ Operation failed: {type(exc).__name__}"})
        time.sleep(0.2)


if __name__ == "__main__":
    main()
