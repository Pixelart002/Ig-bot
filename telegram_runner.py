"""Single long-polling entrypoint with safe Telegram 409 recovery."""
from __future__ import annotations

import logging
import os
import time

import requests

import telegram_bot as bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def clear_webhook() -> None:
    try:
        bot.tg("deleteWebhook", {"drop_pending_updates": False})
        logging.info("Telegram webhook cleared; using getUpdates polling")
    except Exception as exc:
        logging.warning("Could not clear Telegram webhook: %s", exc)


def poll() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")

    bot.start_bridge()
    clear_webhook()
    offset = 0
    conflict_wait = 2

    while True:
        try:
            result = bot.tg("getUpdates", {"timeout": 25, "offset": offset})
            conflict_wait = 2
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    if "callback_query" in update:
                        bot.handle_callback(update["callback_query"])
                    elif "message" in update:
                        bot.handle_message(update["message"])
                except Exception as exc:
                    chat_id = (
                        update.get("message", {}).get("chat", {}).get("id")
                        or update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id")
                    )
                    if chat_id:
                        bot.audit(int(chat_id), "Unhandled Error", type(exc).__name__)
                        try:
                            bot.tg("sendMessage", {"chat_id": chat_id, "text": f"❌ Operation failed: `{type(exc).__name__}`", "parse_mode": "Markdown"})
                        except Exception:
                            pass
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 409:
                logging.warning("Telegram 409 Conflict: another getUpdates consumer is active; retrying in %ss", conflict_wait)
                time.sleep(conflict_wait)
                conflict_wait = min(30, conflict_wait * 2)
                continue
            logging.error("Telegram HTTP error: %s", exc)
            time.sleep(5)
        except requests.RequestException as exc:
            logging.warning("Telegram network error; retrying: %s", exc)
            time.sleep(5)
        except Exception as exc:
            logging.exception("Telegram poller crashed; restarting loop: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    poll()
