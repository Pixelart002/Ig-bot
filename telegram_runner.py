"""Single Render entrypoint using Telegram webhooks instead of getUpdates polling."""
from __future__ import annotations

import logging
import os
import time

import telegram_bot as bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def configure_webhook() -> None:
    base_url = (
        os.getenv("VERIFICATION_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or ""
    ).rstrip("/")
    if not base_url:
        raise SystemExit("Set VERIFICATION_BASE_URL to the Render public URL")

    webhook_url = f"{base_url}/telegram/webhook"
    secret = bot.telegram_webhook_secret()
    if not secret:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")

    result = bot.tg(
        "setWebhook",
        {
            "url": webhook_url,
            "secret_token": secret,
            "drop_pending_updates": False,
            "allowed_updates": ["message", "callback_query"],
        },
    )
    if not result.get("ok"):
        raise RuntimeError(f"Telegram setWebhook failed: {result}")
    logging.info("Telegram webhook configured: %s", webhook_url)


def main() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")

    bot.start_bridge()
    time.sleep(1)
    configure_webhook()

    # Keep the Render web service alive. Telegram pushes updates to FastAPI;
    # there is intentionally no getUpdates loop, so 409 conflicts cannot occur.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
