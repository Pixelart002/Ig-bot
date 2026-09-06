"""Render entrypoint using direct Telegram getUpdates polling."""
from __future__ import annotations

import logging

import telegram_bot as bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    logging.info("Starting direct Telegram polling")
    bot.run_polling()


if __name__ == "__main__":
    main()
