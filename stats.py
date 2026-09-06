"""Persistent lightweight activity stats for the Telegram/Instagram assistant."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

STATS_FILE = Path(os.getenv("STATS_FILE", "data/stats.json"))
_LOCK = threading.Lock()

DEFAULT: dict[str, Any] = {
    "counters": {
        "accounts_created": 0,
        "successful": 0,
        "pending_verification": 0,
        "failed": 0,
        "identities_generated": 0,
        "login_attempts": 0,
        "successful_logins": 0,
        "failed_logins": 0,
    },
    "signup_durations": [],
    "daily": {},
    "events": [],
}


def _load() -> dict[str, Any]:
    if not STATS_FILE.exists():
        return json.loads(json.dumps(DEFAULT))
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT))


def _save(data: dict[str, Any]) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(STATS_FILE)


def record(event: str, duration_seconds: float | None = None) -> None:
    """Record an operational event; never store passwords, tokens, or CAPTCHA data."""
    with _LOCK:
        data = _load()
        counters = data["counters"]
        mapping = {
            "signup_completed": "successful",
            "signup_failed": "failed",
            "verification_required": "pending_verification",
            "identity_generated": "identities_generated",
            "login_started": "login_attempts",
            "login_completed": "successful_logins",
            "login_failed": "failed_logins",
        }
        key = mapping.get(event)
        if key:
            counters[key] += 1
        if event == "signup_completed":
            counters["accounts_created"] += 1
        if duration_seconds is not None and duration_seconds >= 0:
            data["signup_durations"].append(round(duration_seconds, 2))
            data["signup_durations"] = data["signup_durations"][-500:]
        day = time.strftime("%Y-%m-%d", time.gmtime())
        data["daily"].setdefault(day, {})
        data["daily"][day][event] = data["daily"][day].get(event, 0) + 1
        data["events"].append({"event": event, "ts": int(time.time())})
        data["events"] = data["events"][-1000:]
        _save(data)


def snapshot() -> dict[str, Any]:
    with _LOCK:
        data = _load()
    durations = data.get("signup_durations", [])
    data["average_signup_seconds"] = round(sum(durations) / len(durations), 1) if durations else 0
    today = time.strftime("%Y-%m-%d", time.gmtime())
    data["today"] = data.get("daily", {}).get(today, {})
    return data


def format_stats() -> str:
    s = snapshot()
    c = s["counters"]
    avg = s["average_signup_seconds"]
    mins, secs = divmod(int(avg), 60)
    return (
        "📊 *Stats*\n\n"
        f"👤 Accounts Created: `{c['accounts_created']}`\n"
        f"✅ Successful: `{c['successful']}`\n"
        f"⏳ Pending Verification: `{c['pending_verification']}`\n"
        f"❌ Failed: `{c['failed']}`\n"
        f"🤖 AI Identities: `{c['identities_generated']}`\n"
        f"🔐 Login Attempts: `{c['login_attempts']}`\n"
        f"🟢 Successful Logins: `{c['successful_logins']}`\n"
        f"🔴 Failed Logins: `{c['failed_logins']}`\n"
        f"⏱️ Avg Signup Time: `{mins}m {secs}s`\n"
        f"📅 Today: `{sum(s['today'].values())}` events"
    )
