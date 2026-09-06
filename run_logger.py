"""Structured and persistent workflow logging.

All application logs are copied to daily JSONL files under run_logs/. Render's
stdout still receives the normal logs. Secrets, passwords and OTP values are
never intentionally recorded here.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.getenv("RUN_LOG_DIR", "run_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.RLock()
_LOG = logging.getLogger("run_logger")


def _log_path() -> Path:
    return LOG_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"


class _DailyFileHandler(logging.Handler):
    """Mirror normal Python application logs into a daily JSONL file."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            with _LOCK:
                with _log_path().open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _install_file_handler() -> None:
    root = logging.getLogger()
    if any(isinstance(h, _DailyFileHandler) for h in root.handlers):
        return
    handler = _DailyFileHandler()
    handler.setLevel(logging.INFO)
    root.addHandler(handler)


_install_file_handler()


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def log_event(run_id: str, event: str, status: str = "info", **details: Any) -> dict[str, Any]:
    """Record a safe, explicitly correlated workflow event."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        "event": str(event),
        "status": str(status),
        **details,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    _LOG.info("RUN %s | %s | %s | %s", run_id, event, status, details or "-")
    return entry
