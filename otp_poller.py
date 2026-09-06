"""File-based OTP polling with a Lightpanda keep-alive loop."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

from browser_assist import _evaluate, fill_otp, inspect_state

OTP_FILE = Path(os.getenv("OTP_FILE", "otp.txt"))
OTP_INTERVAL = 1.5
OTP_TIMEOUT = 45.0
OTP_PATTERN_LENGTH = 6
_file_lock = threading.RLock()


def _secure_write_code(code: str) -> None:
    with _file_lock:
        OTP_FILE.write_text(code, encoding="utf-8")
        try:
            os.chmod(OTP_FILE, 0o600)
        except OSError:
            pass


def queue_otp_code(code: str) -> bool:
    normalized = str(code).strip()
    if len(normalized) != OTP_PATTERN_LENGTH or not normalized.isdigit():
        return False
    _secure_write_code(normalized)
    return True


def _read_and_delete_code() -> str | None:
    with _file_lock:
        try:
            code = OTP_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logging.warning("OTP file read failed: %s", exc)
            return None
        try:
            OTP_FILE.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("OTP file delete failed: %s", exc)
            return None
    return code if len(code) == OTP_PATTERN_LENGTH and code.isdigit() else None


def clear_otp_file() -> None:
    with _file_lock:
        try:
            OTP_FILE.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("Could not clear stale OTP file: %s", exc)


class CDPPage:
    """Async page adapter over the existing Lightpanda CDP tab."""

    def __init__(self, tab: dict[str, Any]):
        self.tab = tab

    async def evaluate(self, expression: str) -> Any:
        return await asyncio.to_thread(_evaluate, self.tab, expression)


async def wait_for_otp(session) -> bool:
    """Poll otp.txt every 1.5 seconds for up to 45 seconds."""
    tab = session.tab
    if not tab:
        session.event("otp_poll_failed", "error", error="Browser tab unavailable")
        return False

    page = CDPPage(tab)
    session.event("otp_poll_started", "success", interval_seconds=OTP_INTERVAL, timeout_seconds=OTP_TIMEOUT)
    for iteration in range(int(OTP_TIMEOUT / OTP_INTERVAL)):
        try:
            # Keep Lightpanda active on every polling iteration.
            await page.evaluate("document.title")
            code = _read_and_delete_code()
            if code:
                session.event("otp_file_detected", "success", iteration=iteration + 1)
                session.event("otp_file_deleted", "success")
                ok = await asyncio.to_thread(fill_otp, tab, code)
                if ok:
                    session.event("otp_submitted", "success")
                    await asyncio.sleep(1.0)
                    state = await asyncio.to_thread(inspect_state, tab)
                    session.status = state.get("status", "waiting")
                    session.event("otp_post_check", "success", browser_status=session.status)
                    return True
                session.event("otp_submit_failed", "error")
                return False
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:300]}".replace("\n", " ")
            session.event("otp_poll_iteration_failed", "error", iteration=iteration + 1, error=error)
        await asyncio.sleep(OTP_INTERVAL)

    session.event("otp_poll_timeout", "warning", timeout_seconds=OTP_TIMEOUT)
    return False


def _worker(session, notify_callback) -> None:
    try:
        ok = asyncio.run(wait_for_otp(session))
        notify_callback(session, ok)
    finally:
        session.otp_polling = False


def start_otp_polling(session, notify_callback) -> bool:
    if session.otp_polling:
        return False
    session.otp_polling = True
    worker = threading.Thread(target=_worker, args=(session, notify_callback), name=f"otp-poller-{session.chat_id}", daemon=True)
    session.otp_thread = worker
    worker.start()
    return True
