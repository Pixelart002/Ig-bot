"""Render entrypoint using direct Telegram getUpdates polling.

Telegram updates are fetched directly from the Bot API. No Telegram webhook or
public verification URL is required. Render still expects a bound HTTP port,
so a tiny health endpoint is started locally only to satisfy the platform.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

import telegram_bot as bot
from otp_poller import queue_otp_code
from workflow import get

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/health"}:
            self.send_response(404)
            self.end_headers()
            return
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        if self.path not in {"/", "/health"}:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "2")
        self.end_headers()

    def log_message(self, format, *args):
        logging.info("Health: " + format, *args)


def start_health_server() -> ThreadingHTTPServer:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="render-health", daemon=True)
    thread.start()
    logging.info("Render health server listening on 0.0.0.0:%d", port)
    return server


def _send_start(chat_id: int) -> None:
    bot.tg("sendMessage", {"chat_id": chat_id, "text": "🏠 *Main Menu*\n\nChoose what you want to do:", "parse_mode": "Markdown", "reply_markup": bot.keyboard()})


def _handle_message(message: dict) -> None:
    chat = message.get("chat") or {}
    chat_id = int(chat.get("id"))
    text = str(message.get("text") or "").strip()
    if not text or not bot.allowed(chat_id):
        return
    if text.startswith("/start"):
        _send_start(chat_id)
        return
    session = get(chat_id)
    if not session:
        bot.tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ No active session. Tap Create Account to start.", "reply_markup": bot.keyboard()})
        return
    if session.status == "awaiting_email":
        if not bot.EMAIL_RE.fullmatch(text):
            bot.tg("sendMessage", {"chat_id": chat_id, "text": "❌ Please send a valid email address.", "reply_markup": bot.cancel_keyboard()})
            return
        bot.generate_after_email(chat_id, text)
        return
    if session.status == "otp_required" or session.otp_polling:
        if queue_otp_code(text):
            session.event("otp_received_from_telegram", "success")
            return
        bot.tg("sendMessage", {"chat_id": chat_id, "text": "❌ OTP must be exactly 6 digits.", "reply_markup": bot.verification_keyboard(session)})
        return
    if text.isdigit() and len(text) == 6 and queue_otp_code(text):
        session.event("otp_received_from_telegram", "success")
        return
    bot.tg("sendMessage", {"chat_id": chat_id, "text": "ℹ️ Use the buttons above to continue.", "reply_markup": bot.verification_keyboard(session) if session.tab else bot.keyboard()})


def _handle_update(update: dict) -> None:
    callback = update.get("callback_query")
    if callback:
        try:
            bot.handle_callback(callback)
        except Exception:
            logging.exception("Telegram callback handling failed")
        return
    message = update.get("message")
    if message:
        try:
            _handle_message(message)
        except Exception:
            logging.exception("Telegram message handling failed")


def run_polling() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")

    try:
        bot.tg("deleteWebhook", {"drop_pending_updates": False})
        logging.info("Telegram webhook cleared; direct polling enabled")
    except Exception as exc:
        logging.warning("Could not clear Telegram webhook: %s", exc)

    # Render may briefly run the old and new web-service instances during a
    # deploy. Only one process may own getUpdates, so let the old instance exit
    # before this instance starts polling. No webhook is used.
    startup_delay = int(os.getenv("TELEGRAM_POLL_START_DELAY", "65"))
    if startup_delay > 0:
        logging.info("Waiting %ds for previous Render poller to release Telegram polling ownership", startup_delay)
        time.sleep(startup_delay)

    offset = 0
    backoff = 2.0
    while True:
        try:
            result = bot.tg("getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": ["message", "callback_query"]})
            updates = result.get("result", []) if isinstance(result, dict) else []
            backoff = 2.0
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                _handle_update(update)
        except requests.RequestException as exc:
            message = str(exc)
            if "409" in message or "Conflict" in message:
                logging.warning("Telegram polling ownership conflict (409); retrying in %ss", int(backoff))
            else:
                logging.warning("Telegram polling network error: %s", exc)
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
        except Exception as exc:
            logging.exception("Telegram polling error: %s", exc)
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)


def main() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    start_health_server()
    logging.info("Starting direct Telegram polling")
    run_polling()


if __name__ == "__main__":
    main()
