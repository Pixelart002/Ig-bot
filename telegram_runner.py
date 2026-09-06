"""Single Render entrypoint using Telegram webhooks instead of getUpdates polling."""
from __future__ import annotations

import logging
import os
import time

import requests

import telegram_bot as bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _public_base_url() -> str:
    return (
        os.getenv("VERIFICATION_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or ""
    ).rstrip("/")


def _bridge_port() -> int:
    return int(os.getenv("PORT", os.getenv("VERIFICATION_PORT", "8080")))


def wait_for_bridge(timeout: int = 30) -> None:
    """Wait until the local FastAPI bridge is serving before registering Telegram webhook."""
    health_url = f"http://127.0.0.1:{_bridge_port()}/health"
    deadline = time.time() + timeout
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=2)
            response.raise_for_status()
            data = response.json()
            if data.get("ok") is True:
                logging.info("Verification bridge is ready: %s", health_url)
                return
            last_error = RuntimeError(f"Unexpected bridge health response: {data}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
        time.sleep(0.5)

    raise RuntimeError(f"Verification bridge did not become ready within {timeout}s: {last_error}")


def configure_webhook() -> None:
    base_url = _public_base_url()
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
    wait_for_bridge()
    configure_webhook()

    # Keep the Render web service alive. Telegram pushes updates to FastAPI;
    # there is intentionally no getUpdates loop, so 409 conflicts cannot occur.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
