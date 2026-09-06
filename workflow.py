"""In-memory per-user workflow state for Telegram + Lightpanda sessions."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from run_logger import log_event, new_run_id


@dataclass
class Session:
    chat_id: int
    identity: dict[str, Any] = field(default_factory=dict)
    tab: dict[str, Any] | None = None
    started_at: float = field(default_factory=time.time)
    status: str = "created"
    run_id: str = field(default_factory=new_run_id)
    events: list[dict[str, Any]] = field(default_factory=list)
    bridge_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    expires_at: float = field(default_factory=lambda: time.time() + 1800)
    otp_polling: bool = False
    otp_thread: threading.Thread | None = field(default=None, repr=False)

    def event(self, name: str, status: str = "info", **details: Any) -> None:
        safe = {"event": name, "status": status, **details}
        self.events.append(safe)
        if len(self.events) > 100:
            del self.events[:-100]
        log_event(self.run_id, name, status, **details)


_lock = threading.RLock()
_sessions: dict[int, Session] = {}


def get(chat_id: int) -> Session | None:
    with _lock:
        session = _sessions.get(chat_id)
        if session and session.expires_at < time.time():
            session.event("session_expired", "warning")
            _sessions.pop(chat_id, None)
            return None
        return session


def create(chat_id: int, identity: dict[str, Any]) -> Session:
    with _lock:
        session = Session(chat_id=chat_id, identity=identity)
        _sessions[chat_id] = session
        session.event("run_started", "success", chat_id=chat_id)
        return session


def by_token(token: str) -> Session | None:
    with _lock:
        for session in _sessions.values():
            if session.bridge_token == token and session.expires_at >= time.time():
                return session
    return None


def clear(chat_id: int) -> None:
    with _lock:
        session = _sessions.pop(chat_id, None)
        if session:
            session.otp_polling = False


def touch(session: Session, seconds: int = 1800) -> None:
    with _lock:
        session.expires_at = time.time() + seconds
