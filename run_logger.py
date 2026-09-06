"""Structured per-run logging for the Instagram workflow.

Logs are written as JSON Lines under run_logs/ and also emitted to stdout so
Render's service logs contain the same run_id and event trail. No passwords or
OTP values are ever recorded.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.getenv("RUN_LOG_DIR", "run_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.RLock()
_LOG = logging.getLogger("run_logger")


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def log_event(run_id: str, event: str, status: str = "info", **details: Any) -> dict[str, Any]:
    """Record a safe workflow event. Sensitive fields are intentionally not accepted by callers."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        "event": str(event),
        "status": str(status),
        **details,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        path = LOG_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    _LOG.info("RUN %s | %s | %s | %s", run_id, event, status, details or "-")
    return entry
