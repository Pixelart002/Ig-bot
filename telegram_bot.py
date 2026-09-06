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

from browser_assist import inspect_state, start_signup
from ig_bot import generate_identity
from otp_poller import clear_otp_file, queue_otp_code, start_otp_polling
from run_logger import log_event
from stats import format_stats, record
from workflow import clear, create, get

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
LOGIN_URL = "https://www.instagram.com/accounts/login/"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
OTP_RE = re.compile(r"^\d{6}$")


def telegram_webhook_secret() -> str:
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


def audit(chat_id: int, action: str, status: str, identity: dict[str, Any] | None = None, detail: str | None = None) -> None:
    ids = admin_ids()
    if not ids:
        return
    username = str((identity or {}).get("selected_username") or (identity or {}).get("usernames", ["—"])[0])
    name = str((identity or {}).get("display_names", ["—"])[0])
    dob = str((identity or {}).get("date_of_birth") or "—")
    detail_line = f"\n🧾 Detail: `{detail[:300]}`" if detail else ""
    text = ("👁 *Super Admin Activity*\n\n" f"👤 User ID: `{chat_id}`\n" f"⚙️ Action: *{action}*\n" f"📌 Status: *{status}*\n" f"👨 Name: `{name}`\n" f"🔹 Username: `{username}`\n" f"🎂 DOB: `{dob}`\n" "🔐 Password: `••••••••`" + detail_line)
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


def cancel_keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "🏠 Main Menu", "callback_data": "menu"}, {"text": "🛑 Cancel", "callback_data": "cancel_session"}]]}


def identity_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✅ Confirm & Create", "callback_data": "confirm_create"}],
            [{"text": "🔄 Regenerate", "callback_data": "regenerate_identity"}],
            [{"text": "🏠 Main Menu", "callback_data": "menu"}, {"text": "🛑 Cancel", "callback_data": "cancel_session"}],
        ]
    }


def verification_keyboard(session) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔍 Check Status", "callback_data": "check_status"}],
            [{"text": "🏠 Main Menu", "callback_data": "menu"}, {"text": "🛑 Cancel", "callback_data": "cancel_session"}],
        ]
    }


def answer_callback(callback_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190], "show_alert": False})


def identity_text(identity: dict[str, Any], include_password: bool = True) -> str:
    names = identity.get("display_names", [])
    usernames = identity.get("usernames", [])
    bios = identity.get("bios", [])
    lines = ["*Name:* " + str(names[0] if names else "—"), "*Username:* " + str(identity.get("selected_username") or (usernames[0] if usernames else "—")), "*DOB:* " + str(identity.get("date_of_birth", "—")), "*Bio:* " + str(bios[0] if bios else "—")]
    if include_password:
        lines.insert(2, "*Password:* `" + str(identity.get("password", "—")) + "`")
    return "\n".join(lines)


def send_email_prompt(chat_id: int) -> None:
    tg("sendMessage", {"chat_id": chat_id, "text": "📧 *Email required*\n\nSend the email address you want to use for this registration.\n\nYou can cancel anytime.", "parse_mode": "Markdown", "reply_markup": cancel_keyboard()})


def _notify_otp_result(session, ok: bool) -> None:
    """Notify Telegram after the non-blocking file poller finishes."""
    chat_id = session.chat_id
    if ok:
        audit(chat_id, "OTP", "submitted", session.identity)
        try:
            tg("sendMessage", {"chat_id": chat_id, "text": "✅ OTP entered from `otp.txt`.\n\nChecking the Instagram session…", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
            send_session_status(chat_id)
        except Exception as exc:
            session.event("otp_notification_failed", "error", error_type=type(exc).__name__, error=str(exc)[:300])
    else:
        session.status = "otp_timeout"
        audit(chat_id, "OTP", "timeout", session.identity)
        tg("sendMessage", {"chat_id": chat_id, "text": "⌛ No valid 6-digit OTP was received within 45 seconds. Send a new 6-digit code when Instagram is still waiting for verification.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})


def send_otp_prompt(chat_id: int, session, status: str = "otp_required") -> None:
    session.status = status
    clear_otp_file()
    record("otp_requested")
    session.event("otp_requested", "success")
    started = start_otp_polling(session, _notify_otp_result)
    audit(chat_id, "Create Account", "otp_required", session.identity, "File polling started" if started else "File polling already active")
    text = "🔢 *OTP required*\n\nInstagram has requested a verification code.\n\nSend the exact 6-digit code here. It will be silently written to the local `otp.txt` file and entered automatically.\n\nPolling: every 1.5s · timeout: 45s"
    tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})


def handle_create(chat_id: int) -> None:
    record("signup_started")
    audit(chat_id, "Create Account", "awaiting_email")
    create(chat_id, {"awaiting_email": True})
    send_email_prompt(chat_id)


def generate_after_email(chat_id: int, email: str) -> None:
    session = get(chat_id)
    if not session:
        session = create(chat_id, {})

    existing_identity = session.identity if isinstance(session.identity, dict) else {}
    has_identity = bool(existing_identity.get("password") and existing_identity.get("date_of_birth") and existing_identity.get("display_names") and existing_identity.get("usernames"))
    audit(chat_id, "Create Account", "email_saved", existing_identity or None)

    if has_identity:
        existing_identity["email"] = email
        session.identity = existing_identity
        session.status = "identity_ready"
        session.event("identity_reused", "success")
        audit(chat_id, "Create Account", "identity_reused", session.identity)
        tg("sendMessage", {"chat_id": chat_id, "text": "📧 Email saved.\n\n✅ Using the identity you already confirmed. No new identity was generated.\n\nReview the same account details, then continue.", "parse_mode": "Markdown", "reply_markup": identity_keyboard()})
        return

    session.status = "identity_generating"
    audit(chat_id, "Create Account", "identity_generation_started")
    tg("sendMessage", {"chat_id": chat_id, "text": "📧 Email saved.\n\n⏳ Generating account details…", "parse_mode": "Markdown"})
    identity = generate_identity()
    if not identity:
        session.status = "identity_generation_failed"
        record("signup_failed")
        audit(chat_id, "Create Account", "identity_generation_failed", session.identity)
        tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Your email is saved. Tap 🤖 Generate Identity to retry.", "reply_markup": keyboard()})
        return
    identity["email"] = email
    session.identity = identity
    session.status = "identity_ready"
    session.event("identity_generated", "success")
    audit(chat_id, "Create Account", "identity_generated", identity)
    tg("sendMessage", {"chat_id": chat_id, "text": "🆕 *Account Details*\n\n" + identity_text(identity) + f"\n*Email:* `{email}`\n\nReview the details, then continue.", "parse_mode": "Markdown", "reply_markup": identity_keyboard()})


def regenerate_identity(chat_id: int) -> None:
    session = get(chat_id)
    email = (session.identity.get("email") if session else "") or ""
    if not email:
        handle_create(chat_id)
        return
    tg("sendMessage", {"chat_id": chat_id, "text": "🔄 Generating a fresh identity…"})
    identity = generate_identity()
    if not identity:
        if session:
            session.status = "identity_generation_failed"
        tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Your email is saved. Please retry.", "reply_markup": cancel_keyboard()})
        audit(chat_id, "Create Account", "identity_regeneration_failed", session.identity if session else None)
        return
    identity["email"] = email
    session.identity = identity
    session.status = "identity_ready"
    audit(chat_id, "Create Account", "identity_regenerated", identity)
    tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Fresh Account Details*\n\n" + identity_text(identity) + f"\n*Email:* `{email}`\n\nReview and continue.", "parse_mode": "Markdown", "reply_markup": identity_keyboard()})


def send_session_status(chat_id: int) -> None:
    session = get(chat_id)
    if not session or not session.tab:
        tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ No active browser session.", "reply_markup": keyboard()})
        return
    try:
        session.event("session_check_started", "info")
        state = inspect_state(session.tab)
        if not isinstance(state, dict) or not state.get("status"):
            raise RuntimeError(f"Invalid session state returned: {state!r}")
        session.status = state["status"]
        session.event("session_check", "success", browser_status=state["status"], url=state.get("url", ""))
        if state["status"] == "otp_required":
            send_otp_prompt(chat_id, session)
        elif state["status"] == "captcha_required":
            record("verification_required")
            audit(chat_id, "Session Check", "captcha_required", session.identity or None)
            tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ *Manual verification required*\n\nComplete the CAPTCHA in the local browser process, then press *Check Status* again.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
        elif session.identity and state["status"] == "completed":
            record("signup_completed", time.time() - session.started_at)
            audit(chat_id, "Create Account", "completed", session.identity)
            tg("sendMessage", {"chat_id": chat_id, "text": "🎉 *Registration completed successfully.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
            clear(chat_id)
        elif not session.identity and state["status"] == "waiting":
            record("login_completed")
            audit(chat_id, "Login", "completed")
            tg("sendMessage", {"chat_id": chat_id, "text": "✅ *Login appears complete.*\n\n📊 Stats updated.", "parse_mode": "Markdown", "reply_markup": keyboard()})
            clear(chat_id)
        else:
            audit(chat_id, "Session Check", state["status"], session.identity or None)
            tg("sendMessage", {"chat_id": chat_id, "text": f"⏳ *Session status:* `{state['status']}`\n\nContinue the required step, then check again.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)}".replace("\n", " ")[:500]
        session.event("session_check_failed", "error", error=error)
        log_event(session.run_id, "session_check_exception", "error", error_type=type(exc).__name__, error=error)
        audit(chat_id, "Session Check", "failed", session.identity or None, error)
        tg("sendMessage", {"chat_id": chat_id, "text": "❌ Could not check the browser session.\n\nThe session has been kept alive; press *Check Status* again.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})


def handle_callback(callback: dict[str, Any]) -> None:
    data = callback.get("data", "")
    chat_id = int(callback["message"]["chat"]["id"])
    answer_callback(callback["id"], "Processing…")
    if not allowed(chat_id):
        tg("sendMessage", {"chat_id": chat_id, "text": "⛔ This bot is not enabled for your Telegram account."})
        return
    if data == "menu":
        tg("sendMessage", {"chat_id": chat_id, "text": "🏠 *Main Menu*\n\nChoose what you want to do:", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    if data == "stats":
        tg("sendMessage", {"chat_id": chat_id, "text": format_stats(), "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    if data == "cancel_session":
        clear(chat_id)
        clear_otp_file()
        audit(chat_id, "Session", "cancelled")
        tg("sendMessage", {"chat_id": chat_id, "text": "🛑 *Session cancelled.*\n\nYou are back at the main menu.", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    if data == "identity":
        session = get(chat_id)
        saved_email = str(session.identity.get("email", "")) if session else ""
        identity = generate_identity()
        if not identity:
            if session and saved_email:
                session.status = "identity_generation_failed"
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Identity generation failed. Your email is still saved. Tap 🤖 Generate Identity to retry.", "reply_markup": keyboard()})
            audit(chat_id, "Generate Identity", "failed", session.identity if session else None)
            return
        if saved_email:
            identity["email"] = saved_email
        if session:
            session.identity = identity
            session.status = "identity_ready"
        else:
            session = create(chat_id, identity)
            session.status = "identity_ready"
        audit(chat_id, "Generate Identity", "ready", identity)
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Identity Preview*\n\n" + identity_text(identity) + (f"\n*Email:* `{saved_email}`" if saved_email else ""), "parse_mode": "Markdown", "reply_markup": identity_keyboard()})
        return
    if data == "regenerate_identity":
        regenerate_identity(chat_id)
        return
    if data == "create":
        handle_create(chat_id)
        return
    if data == "check_status":
        send_session_status(chat_id)
        return
    if data == "confirm_create":
        session = get(chat_id)
        if not session or not session.identity:
            handle_create(chat_id)
            return
        record("reviewed")
        audit(chat_id, "Create Account", "confirmed", session.identity)
        try:
            credentials = {"email": str(session.identity.get("email", "")), "password": str(session.identity.get("password", "")), "username": str((session.identity.get("selected_username") or (session.identity.get("usernames") or [""])[0])), "full_name": str((session.identity.get("display_names") or [""])[0])}
            if not credentials["email"]:
                session.status = "awaiting_email"
                send_email_prompt(chat_id)
                return
            record("confirmed")
            tab, filled = start_signup(credentials, session.identity)
            session.tab = tab
            session.status = "form_filled" if filled else "waiting"
            if filled:
                record("form_filled")
            else:
                record("signup_waiting")
            send_session_status(chat_id)
        except Exception as exc:
            session.status = "failed"
            record("signup_failed", time.time() - session.started_at)
            session.event("signup_failed", "error", error_type=type(exc).__name__, error=str(exc)[:500])
            audit(chat_id, "Create Account", "failed", session.identity, f"{type(exc).__name__}: {str(exc)[:300]}")
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Signup session failed: `{type(exc).__name__}`", "parse_mode": "Markdown", "reply_markup": cancel_keyboard()})
        return
    tg("sendMessage", {"chat_id": chat_id, "text": "Unknown action. Returning to menu.", "reply_markup": keyboard()})


def handle_message(message: dict[str, Any]) -> None:
    chat_id = int(message["chat"]["id"])
    text = str(message.get("text", "")).strip()
    if not allowed(chat_id):
        return
    session = get(chat_id)
    if session and session.status in {"awaiting_email", "created"} and EMAIL_RE.fullmatch(text):
        generate_after_email(chat_id, text)
        return
    if session and session.tab and session.status == "otp_required" and OTP_RE.fullmatch(text):
        # Direct file-based OTP listener: never echo or transmit the code here.
        if queue_otp_code(text):
            session.event("otp_received_from_telegram", "success")
        return
    if text.lower() in {"/start", "start"}:
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Instagram Assistant*\n\nChoose an action:", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    tg("sendMessage", {"chat_id": chat_id, "text": "Use the buttons above or send the requested email/6-digit OTP when prompted.", "reply_markup": keyboard()})


def process_update(update: dict[str, Any]) -> None:
    if "callback_query" in update:
        handle_callback(update["callback_query"])
    elif "message" in update:
        handle_message(update["message"])


def run_polling() -> None:
    offset = 0
    try:
        tg("deleteWebhook", {"drop_pending_updates": False})
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"Telegram deleteWebhook warning: {exc}")
    while True:
        try:
            response = tg("getUpdates", {"timeout": 50, "offset": offset, "allowed_updates": ["message", "callback_query"]})
            for update in response.get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                try:
                    process_update(update)
                except Exception as exc:
                    chat_id = int(update.get("message", {}).get("chat", {}).get("id") or update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id") or 0)
                    if chat_id:
                        audit(chat_id, "Polling Update Error", "failed", get(chat_id).identity if get(chat_id) else None, f"{type(exc).__name__}: {str(exc)[:300]}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            print(f"Telegram polling error: {exc}")
            time.sleep(3)


def configure_webhook() -> None:
    raise RuntimeError("Webhook mode has been removed. Use direct Telegram getUpdates polling.")


def start_bot() -> None:
    run_polling()
