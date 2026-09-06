"""Render entrypoint using direct Telegram getUpdates polling.

Telegram updates are fetched directly from the Bot API. No Telegram webhook or
public verification URL is required. Render still expects a bound HTTP port,
so a tiny health endpoint is started locally only to satisfy the platform.
"""
from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telegram_bot as bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
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

    def log_message(self, format, *args):  # noqa: A002
        logging.info("Health: " + format, *args)


def start_health_server() -> ThreadingHTTPServer:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="render-health", daemon=True)
    thread.start()
    logging.info("Render health server listening on 0.0.0.0:%d", port)
    return server


def main() -> None:
    if not bot.TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    start_health_server()
    logging.info("Starting direct Telegram polling")
    bot.run_polling()


if __name__ == "__main__":
    main()
