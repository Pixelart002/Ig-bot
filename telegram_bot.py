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
    rows: list[list[dict[str, str]]] = []
    link = verification_link(session)
    if link:
        rows.append([{"text": "🔗 Open Verification Session", "url": link}])
    rows.append([{"text": "🔍 Check Status", "callback_data": "check_status"}])
    rows.append([{"text": "🏠 Main Menu", "callback_data": "menu"}, {"text": "🛑 Cancel", "callback_data": "cancel_session"}])
    return {"inline_keyboard": rows}


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


def send_email_prompt(chat_id: int) -> None:
    tg("sendMessage", {"chat_id": chat_id, "text": "📧 *Email required*\n\nSend the email address you want to use for this registration.\n\nYou can cancel anytime.", "parse_mode": "Markdown", "reply_markup": cancel_keyboard()})


def send_otp_prompt(chat_id: int, session, status: str = "otp_required") -> None:
    session.status = status
    record("otp_requested")
    audit(chat_id, "Create Account", "otp_required", session.identity)
    text = "🔢 *OTP required*\n\nInstagram has requested a verification code.\n\nSend the OTP here and I will enter only the code you provide into the active verification field."
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

    # The identity shown to the user before email collection is authoritative.
    # Never silently replace a confirmed identity after the email arrives.
    existing_identity = session.identity if isinstance(session.identity, dict) else {}
    has_identity = bool(
        existing_identity.get("password")
        and existing_identity.get("date_of_birth")
        and existing_identity.get("display_names")
        and existing_identity.get("usernames")
    )

    audit(chat_id, "Create Account", "email_saved", existing_identity or None)

    if has_identity:
        existing_identity["email"] = email
        session.identity = existing_identity
        session.status = "identity_ready"
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
        state = inspect_state(session.tab)
        session.status = state["status"]
        if state["status"] == "otp_required":
            send_otp_prompt(chat_id, session)
        elif state["status"] == "captcha_required":
            record("verification_required")
            audit(chat_id, "Session Check", "captcha_required", session.identity or None)
            tg("sendMessage", {"chat_id": chat_id, "text": "⚠️ *Manual verification required*\n\nComplete the CAPTCHA in the verification session, then press *Check Status* again.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
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
            tg("sendMessage", {"chat_id": chat_id, "text": f"⏳ *Session status:* `{state['status']}`\n\nContinue the required step in the verification session, then check again.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
    except Exception as exc:
        audit(chat_id, "Session Check", "failed", session.identity or None)
        tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Could not check the session: `{type(exc).__name__}`", "parse_mode": "Markdown", "reply_markup": cancel_keyboard()})


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
            credentials = {"email": str(session.identity.get("email", "")), "password": str(session.identity.get("password", "")), "username": str((session.identity.get("usernames") or [""])[0]), "full_name": str((session.identity.get("display_names") or [""])[0])}
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
                audit(chat_id, "Create Account", "form_filled", session.identity)
            session.started_at = time.time()
            send_session_status(chat_id)
        except Exception as exc:
            session.status = "failed"
            record("signup_failed", time.time() - session.started_at)
            audit(chat_id, "Create Account", "failed", session.identity)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Signup session failed: `{type(exc).__name__}`", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    if data == "login":
        record("login_started")
        audit(chat_id, "Login", "started")
        create(chat_id, {})
        try:
            from browser_assist import open_url
            session = get(chat_id)
            session.tab = open_url(LOGIN_URL)
            session.status = "login_pending"
            audit(chat_id, "Login", "browser_session_ready")
            tg("sendMessage", {"chat_id": chat_id, "text": "🔐 *Login session started*\n\nContinue in the verification session. If Instagram asks for CAPTCHA/2FA, complete it manually.\n\nWhen done, press *Check Status*.", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
        except Exception as exc:
            record("login_failed")
            audit(chat_id, "Login", "failed")
            clear(chat_id)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Login session failed: `{type(exc).__name__}`", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return


def handle_message(message: dict[str, Any]) -> None:
    chat_id = int(message["chat"]["id"])
    text = message.get("text", "").strip()
    if not allowed(chat_id):
        tg("sendMessage", {"chat_id": chat_id, "text": "⛔ This bot is not enabled for your Telegram account."})
        return
    if text in ("/start", "/menu"):
        tg("sendMessage", {"chat_id": chat_id, "text": "🤖 *Instagram Assistant*\n\nChoose an action:", "parse_mode": "Markdown", "reply_markup": keyboard()})
        return
    if text == "/completed":
        send_session_status(chat_id)
        return
    if text == "/cancel":
        session = get(chat_id)
        audit(chat_id, "Session", "cancelled", session.identity if session else None)
        clear(chat_id)
        tg("sendMessage", {"chat_id": chat_id, "text": "🛑 *Session cancelled.*", "reply_markup": keyboard()})
        return

    session = get(chat_id)
    if session and session.status == "awaiting_email":
        if not EMAIL_RE.fullmatch(text):
            tg("sendMessage", {"chat_id": chat_id, "text": "❌ Invalid email format.\n\nPlease send a valid email address or press *Cancel*.", "parse_mode": "Markdown", "reply_markup": cancel_keyboard()})
            return
        email = text.lower()
        audit(chat_id, "Create Account", "email_received")
        generate_after_email(chat_id, email)
        return

    if session and session.tab and session.status == "otp_required" and OTP_RE.fullmatch(text):
        try:
            if fill_otp(session.tab, text):
                session.status = "otp_submitted"
                record("otp_submitted")
                audit(chat_id, "Create Account", "otp_submitted", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "✅ OTP entered into the active verification session.\n\n⏳ Checking the next step…"})
                time.sleep(2)
                send_session_status(chat_id)
            else:
                audit(chat_id, "Create Account", "otp_field_not_found", session.identity)
                tg("sendMessage", {"chat_id": chat_id, "text": "❌ OTP field not found. Open the verification session, reach the code screen, then try again.", "reply_markup": verification_keyboard(session)})
        except Exception as exc:
            audit(chat_id, "Create Account", "otp_submit_failed", session.identity)
            tg("sendMessage", {"chat_id": chat_id, "text": f"❌ OTP submission failed: `{type(exc).__name__}`", "parse_mode": "Markdown", "reply_markup": verification_keyboard(session)})
        return

    if text:
        tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ Use the buttons below to control the current flow.", "reply_markup": keyboard()})


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
                    tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Operation failed: `{type(exc).__name__}`", "parse_mode": "Markdown"})
        time.sleep(0.2)


if __name__ == "__main__":
    main()
