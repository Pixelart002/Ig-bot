"""Telegram control plane for the Lightpanda signup/login assistant.

CAPTCHA and anti-bot controls remain manual. User-supplied OTP is handed to
Lightpanda only to fill the active verification field and continue the flow.
"""
from __future__ import annotations

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
    return {"inline_keyboard": [[{"text": "🆕 Create Account", "callback_data": "create"}, {"text": "🔐 Login", "callback_data": "login"}], [{"text": "🤖 Generate Identity", "callback_data": "identity"}, {"text": "📊 Stats", "callback_data": "stats"}]]}


def answer_callback(callback_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190], "show_alert": False})


def identity_text(identity: dict[str, Any], include_password: bool = True) -> str:
    names = identity.get("display_names", [])
    usernames = identity.get("usernames", [])
    bios = identity.get("bios", [])
    lines = ["*Name:* " + str(names[0] if names else "—"), "*Username:* " + str(usernames[0] if usernames else "—"), "*DOB:* " + str(identity.get("date_of_birth", "—")), "*Bio:* " + str(bios[0] if bios else "—")]
    if include_password:
        lines.insert(2, "*Password:* `" + str(identity.get("password", "—")) + "`")
    return "\n".join(lines)


def verification_link(session) -> str:
    if not PUBLIC_BASE_URL:
        return ""
    return f"{PUBLIC_BASE_URL}/v/{session.bridge_token}"


def send_otp_prompt(chat_id: int, session, status: str = "otp_required") -> None:
    session.status = status
    record("otp_requested")
    audit(chat_id, "Create Account", "otp_required", session.identity)
    link = verification_link(session)
    text = "🔢 *OTP required.*\n\nInstagram has requested a verification code. Send the OTP here as a message; I will enter the code into the active Lightpanda session and continue."
    markup = {"inline_keyboard": []}
    if link:
        markup["inline_keyboard"].append([{"text": "🔗 Open Verification Session", "url": link}])
    markup["inline_keyboard"].append([{"text": "🛑 Cancel", "callback_data": "cancel_session"}])
    tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup})


def handle_create(chat_id: int) -> None:
    record("signup_started")
    audit(chat_id, "Create Account", "identity_generation_started")
    identity = generate_identity()
    if not identity:
        record("signup_failed")
        audit(chat_id, "Create Account", "identity_generation_failed")
        tg("sendMessage", {"chat_id": chat_id, "text": "❌ Could not generate signup details."})
        return
    create(chat_id, identity)
    audit(chat_id, "Create Account", "identity_generated", identity)
    tg("sendMessage", {"chat_id": chat_id, "text": "🆕 *Account Details*\n\n" + identity_text(identity) + "\n\nPress *Confirm & Create* to continue.", "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "✅ Confirm & Create", "callback_data": "confirm_create"}], [{"text": "🔄 Regenerate", "callback_data": "create"}]]}})


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
    if data == "cancel_session":
        clear(chat_id)
        audit(chat_id, "Session", "cancelled")
        tg("sendMessage", {"chat_id": chat_id, "text": "🛑 Session cancelled.", "reply_markup": keyboard()})
        return
    if data == "identity":
        identity = generate_identity()
        if not identity:
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Check HF_TOKEN."})
            audit(chat_id, "Generate Identity", "failed")
            return
        create(chat_id, identity)
        audit(chat_id, "Generate Identity", "ready", identity)
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
        audit(chat_id, "Create Account", "confirmed", session.identity)
        try:
            credentials = {"email": os.getenv("IG_EMAIL", ""), "password": str(session.identity.get("password", "")), "username": str((session.identity.get("usernames") or [""])[0]), "full_name": str((session.identity.get("display_names") or [""])[0])}
            tab, filled = start_signup(credentials, session.identity)
            session.tab = tab
            session.status = "form_filled" if filled else "waiting"
            if filled:
                record("form_filled")
                audit(chat_id, "Create Account", "form_filled", session.identity)
            session.started_at = time.time()
            state = inspect_state(tab)
            if state["status"] == "otp_required":
                send_otp_prompt(chat_id, session)
            elif state["status"] == "captcha_required":
                session.status = "captcha_required"
                record("verification_required")
                audit(chat_id, "Create Account", "captcha_required", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ CAPTCHA is required. Complete it manually in the verification session, then send `/completed`." + (("\n\n" + verification_link(session)) if verification_link(session) else ""), "parse_mode": "Markdown"})
            else:
                audit(chat_id, "Create Account", "waiting_for_manual_step", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "🌐 Signup session is ready. Continue in the verification session if prompted, then send `/completed`." + (("\n\n" + verification_link(session)) if verification_link(session) else ""), "parse_mode": "Markdown"})
        except Exception as exc:
            session.status = "failed"
            record("signup_failed", time.time() - session.started_at)
            audit(chat_id, "Create Account", "failed", session.identity)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Signup session failed: {type(exc).__name__}"})
        return
    if data == "login":
        record("login_started")
        audit(chat_id, "Login", "started")
        session = create(chat_id, {})
        try:
            from browser_assist import open_url
            session.tab = open_url(LOGIN_URL)
            session.status = "login_pending"
            audit(chat_id, "Login", "browser_session_ready")
            text = "🔐 *Login session started.*\n\nUse the verification session for manual CAPTCHA/2FA if required. After login, send `/completed`."
            link = verification_link(session)
            markup = {"inline_keyboard": []}
            if link:
                markup["inline_keyboard"].append([{"text": "🔗 Open Login Session", "url": link}])
            tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup})
        except Exception as exc:
            record("login_failed")
            audit(chat_id, "Login", "failed")
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
        return
    if text == "/completed":
        session = get(chat_id)
        if not session or not session.tab:
            tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ No active browser session."})
            return
        try:
            state = inspect_state(session.tab)
            session.status = state["status"]
            if state["status"] == "otp_required":
                send_otp_prompt(chat_id, session)
            elif state["status"] == "captcha_required":
                tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ CAPTCHA is still required. Complete it manually, then send `/completed`."})
            elif session.identity and state["status"] == "completed":
                record("signup_completed", time.time() - session.started_at)
                audit(chat_id, "Create Account", "completed", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ *Signup completed.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
                clear(chat_id)
            elif not session.identity and state["status"] == "waiting":
                record("login_completed")
                audit(chat_id, "Login", "completed")
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ *Login appears complete.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
                clear(chat_id)
            else:
                audit(chat_id, "Session Check", state["status"], session.identity or None)
                tg("sendMessage", {"chat_id": chat_id, "text": f"⏳ Session state: `{state['status']}`\nURL: {state['url']}", "parse_mode": "Markdown"})
        except Exception as exc:
            if session.identity:
                record("signup_failed", time.time() - session.started_at)
                audit(chat_id, "Create Account", "session_check_failed", session.identity)
            else:
                record("login_failed")
                audit(chat_id, "Login", "session_check_failed")
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Could not verify session: {type(exc).__name__}"})
        return
    if text == "/cancel":
        session = get(chat_id)
        audit(chat_id, "Session", "cancelled", session.identity if session else None)
        clear(chat_id)
        tg("sendMessage", {"chat_id": chat_id, "text": "🛑 Session cancelled.", "reply_markup": keyboard()})
        return

    session = get(chat_id)
    if session and session.tab and session.status == "otp_required" and re.fullmatch(r"[A-Za-z0-9]{4,32}", text):
        try:
            if fill_otp(session.tab, text):
                session.status = "otp_submitted"
                record("otp_submitted")
                audit(chat_id, "Create Account", "otp_submitted", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ OTP entered into the active Lightpanda session. Checking the next step…"})
                time.sleep(2)
                state = inspect_state(session.tab)
                session.status = state["status"]
                if state["status"] == "completed":
                    record("signup_completed", time.time() - session.started_at)
                    audit(chat_id, "Create Account", "completed", session.identity)
                    tg("sendMessage", {"chat_id": chat_id, "text": "🎉 *Registration completed successfully.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
                    clear(chat_id)
                elif state["status"] == "captcha_required":
                    audit(chat_id, "Create Account", "captcha_required", session.identity)
                    tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ OTP accepted, but CAPTCHA/another manual verification step is required. Complete it manually, then send `/completed`."})
                elif state["status"] == "otp_required":
                    tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ The page still requests a verification code. Send the current OTP again."})
                else:
                    tg("sendMessage", {"chat_id": chat_id, "text": "⏳ OTP submitted. Continue any remaining manual step, then send `/completed`."})
            else:
                audit(chat_id, "Create Account", "otp_field_not_found", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "❌ I couldn't find the OTP field. Open the verification session and send `/completed` once the OTP screen is visible."})
        except Exception as exc:
            audit(chat_id, "Create Account", "otp_submit_failed", session.identity)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ OTP handoff failed: {type(exc).__name__}"})
        return


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
                    audit(int(chat_id), "Unhandled Error", type(exc).__name__)
                    tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Operation failed: {type(exc).__name__}"})
        time.sleep(0.2)


if __name__ == "__main__":
    main()
