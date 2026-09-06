"""Telegram control plane for the Lightpanda signup/login assistant.

CAPTCHA, OTP and account verification remain manual. The optional verification
bridge is protected by a random, expiring per-user token and never exposes CDP.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from browser_assist import inspect_state, start_signup
from ig_bot import generate_identity
from stats import format_stats, record
from verification_bridge import start_bridge
from workflow import clear, create, get

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
PUBLIC_BASE_URL = os.getenv("VERIFICATION_BASE_URL", os.getenv("PUBLIC_BASE_URL", "")).rstrip("/")
LOGIN_URL = "https://www.instagram.com/accounts/login/"


def tg(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not API:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    response = requests.post(f"{API}/{method}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def allowed(chat_id: int) -> bool:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return True
    try:
        return str(chat_id) in {x.strip() for x in raw.split(",") if x.strip()}
    except ValueError:
        return False


def keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": "🆕 Create Account", "callback_data": "create"},
        {"text": "🔐 Login", "callback_data": "login"}],
        [{"text": "🤖 Generate Identity", "callback_data": "identity"},
         {"text": "📊 Stats", "callback_data": "stats"}]]}


def answer_callback(callback_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190], "show_alert": False})


def identity_text(identity: dict[str, Any]) -> str:
    return ("*Names:* " + ", ".join(map(str, identity.get("display_names", [])[:3]))
            + "\n*Usernames:* " + ", ".join(map(str, identity.get("usernames", [])[:5]))
            + "\n*Bios:* " + " | ".join(map(str, identity.get("bios", [])[:3])))


def verification_link(session) -> str:
    if not PUBLIC_BASE_URL:
        return ""
    return f"{PUBLIC_BASE_URL}/v/{session.bridge_token}"


def send_verification(chat_id: int, session) -> None:
    link = verification_link(session)
    text = "⚠️ *Manual verification required.*\n\nComplete CAPTCHA/OTP/verification yourself. Then send `/completed` here."
    markup = {"inline_keyboard": []}
    if link:
        markup["inline_keyboard"].append([{"text": "🔗 Open Verification Session", "url": link}])
    markup["inline_keyboard"].append([{"text": "📊 Stats", "callback_data": "stats"}])
    tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup})


def handle_create(chat_id: int) -> None:
    record("signup_started")
    identity = generate_identity()
    if not identity:
        record("signup_failed")
        tg("sendMessage", {"chat_id": chat_id, "text": "❌ Could not generate signup details."})
        return
    create(chat_id, identity)
    tg("sendMessage", {"chat_id": chat_id, "text": "🆕 *Review before Create*\n\n" + identity_text(identity) + "\n\nPress *Confirm & Create* to continue.", "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "✅ Confirm & Create", "callback_data": "confirm_create"}], [{"text": "🔄 Regenerate", "callback_data": "create"}]]}})


def handle_callback(callback: dict[str, Any]) -> None:
    data = callback.get("data", "")
    chat_id = int(callback["message"]["chat"]["id"])
    answer_callback(callback["id"], "Processing…")
    if not allowed(chat_id):
        tg("sendMessage", {"chat_id": chat_id, "text": "⛔ This bot is not enabled for your Telegram account."})
        return

    if data == "stats":
        tg("sendMessage", {"chat_id": chat_id, "text": format_stats(), "parse_mode": "Markdown", "reply_markup": keyboard()})
        return

    if data == "identity":
        identity = generate_identity()
        if not identity:
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Check HF_TOKEN."})
            return
        create(chat_id, identity)
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Identity Preview*\n\n" + identity_text(identity), "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "🔄 Generate Again", "callback_data": "identity"}, {"text": "🆕 Use for Signup", "callback_data": "confirm_create"}]]}})
        return

    if data == "create":
        handle_create(chat_id)
        return

    if data == "confirm_create":
        session = get(chat_id)
        if not session:
            handle_create(chat_id)
            return
        record("reviewed")
        record("confirmed")
        try:
            tab, filled = start_signup(session.identity)
            session.tab = tab
            session.status = "form_filled" if filled else "waiting"
            if filled:
                record("form_filled")
            session.started_at = time.time()
            state = inspect_state(tab)
            if state["status"] == "verification_required":
                session.status = "verification_required"
                record("verification_required")
                send_verification(chat_id, session)
            else:
                tg("sendMessage", {"chat_id": chat_id, "text": "🌐 Signup session is ready. Continue in the verification session if prompted, then send `/completed`." + ("\n\n" + verification_link(session) if verification_link(session) else ""), "parse_mode": "Markdown"})
        except Exception as exc:
            session.status = "failed"
            record("signup_failed", time.time() - session.started_at)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Signup session failed: {type(exc).__name__}"})
        return

    if data == "login":
        record("login_started")
        session = create(chat_id, {})
        try:
            from browser_assist import open_url
            session.tab = open_url(LOGIN_URL)
            session.status = "login_pending"
            text = "🔐 *Login session started.*\n\nUse the verification session for manual CAPTCHA/2FA if required. After login, send `/completed`."
            link = verification_link(session)
            markup = {"inline_keyboard": []}
            if link:
                markup["inline_keyboard"].append([{"text": "🔗 Open Login Session", "url": link}])
            tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup})
        except Exception as exc:
            record("login_failed")
            clear(chat_id)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Login session failed: {type(exc).__name__}"})


def handle_message(message: dict[str, Any]) -> None:
    chat_id = int(message["chat"]["id"])
    text = message.get("text", "").strip()
    if not allowed(chat_id):
        tg("sendMessage", {"chat_id": chat_id, "text": "⛔ This bot is not enabled for your Telegram account."})
        return
    if text in ("/start", "/menu"):
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Instagram Assistant*\nChoose an action:", "parse_mode": "Markdown", "reply_markup": keyboard()})
    elif text == "/completed":
        session = get(chat_id)
        if not session or not session.tab:
            tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ No active browser session."})
            return
        try:
            state = inspect_state(session.tab)
            session.status = state["status"]
            if state["status"] == "verification_required":
                record("verification_required")
                tg("sendMessage", {"chat_id": chat_id, "text": "⏳ Verification is still required. Finish CAPTCHA/OTP/verification, then send `/completed` again."})
            elif session.identity and state["status"] == "completed":
                record("signup_completed", time.time() - session.started_at)
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ *Signup completed.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
                clear(chat_id)
            elif not session.identity and state["status"] == "waiting":
                record("login_completed")
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ *Login appears complete.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
                clear(chat_id)
            else:
                tg("sendMessage", {"chat_id": chat_id, "text": f"⏳ Session state: `{state['status']}`\nURL: {state['url']}", "parse_mode": "Markdown"})
        except Exception as exc:
            if session.identity:
                record("signup_failed", time.time() - session.started_at)
            else:
                record("login_failed")
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Could not verify session: {type(exc).__name__}"})
    elif text == "/cancel":
        clear(chat_id)
        tg("sendMessage", {"chat_id": chat_id, "text": "🛑 Session cancelled.", "reply_markup": keyboard()})


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    start_bridge()
    offset = 0
    while True:
        for update in tg("getUpdates", {"timeout": 25, "offset": offset}).get("result", []):
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                elif "message" in update:
                    handle_message(update["message"])
            except Exception as exc:
                chat_id = update.get("message", {}).get("chat", {}).get("id") or update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id")
                if chat_id:
                    tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Operation failed: {type(exc).__name__}"})
        time.sleep(0.2)


if __name__ == "__main__":
    main()
