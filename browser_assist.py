#!/usr/bin/env python3
"""
browser_assist.py

Synchronous compatibility wrapper around the external Node.js browser
adapter. This module intentionally does not implement signup-flow logic.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
NODE_SCRIPT = BASE_DIR / "signup_flow.js"
NODE_TIMEOUT_SECONDS = 600


# ---------------------------------------------------------------------------
# Compatibility stubs
# ---------------------------------------------------------------------------

async def capture_screenshot(
    filename: str = "screenshot.png",
) -> Optional[bytes]:
    logger.warning("capture_screenshot() is not implemented")
    return None


async def inspect_state() -> Dict[str, Any]:
    logger.warning("inspect_state() is not implemented")
    return {"state": "unknown"}


async def start_keepalive() -> None:
    logger.info("start_keepalive() called - no-op")


async def cdp_call(
    method: str,
    params: Optional[dict] = None,
) -> Dict[str, Any]:
    logger.warning(
        "cdp_call(%s) is not implemented; params=%s",
        method,
        bool(params),
    )
    return {"result": "dummy", "method": method}


# ---------------------------------------------------------------------------
# Synchronous compatibility entry point
# ---------------------------------------------------------------------------

def start_signup(
    credentials: Dict[str, Any],
    identity: Any = None,
    on_progress: Any = None,
) -> tuple:
    """
    Synchronous compatibility entry point.

    Returns:
        (tab_id, True) on successful completion
        (None, False) on failure
    """

    if not isinstance(credentials, dict):
        logger.error("start_signup(): credentials must be a dict")
        return None, False

    # Keep the expected interface compatible with telegram_bot.py.
    if identity is not None:
        logger.debug("Signup identity supplied")

    if on_progress is not None:
        logger.debug("Signup progress callback supplied")

    required = (
        "email",
        "password",
        "birthday",
        "full_name",
        "username",
    )

    user_data = {
        key: credentials.get(key)
        for key in required
    }

    missing = [
        key for key, value in user_data.items()
        if not value
    ]

    if missing:
        logger.error(
            "Signup request missing required fields: %s",
            ", ".join(missing),
        )
        return None, False

    if not NODE_SCRIPT.is_file():
        logger.error(
            "Node signup adapter not found: %s",
            NODE_SCRIPT,
        )
        return None, False

    payload = json.dumps(
        user_data,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    logger.info(
        "Launching Node browser adapter: %s",
        NODE_SCRIPT.name,
    )

    try:
        proc = subprocess.run(
            ["node", str(NODE_SCRIPT), payload],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=NODE_TIMEOUT_SECONDS,
            check=False,
        )

    except subprocess.TimeoutExpired:
        logger.error(
            "Node browser adapter timed out after %ss",
            NODE_TIMEOUT_SECONDS,
        )
        return None, False

    except FileNotFoundError:
        logger.error(
            "Node.js executable was not found"
        )
        return None, False

    except OSError:
        logger.exception(
            "Failed to start Node browser adapter"
        )
        return None, False

    except Exception:
        logger.exception(
            "Unexpected error starting Node browser adapter"
        )
        return None, False

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if stderr:
        logger.warning(
            "Node adapter stderr: %s",
            stderr[-4000:],
        )

    if proc.returncode != 0:
        logger.error(
            "Node adapter exited with code %s",
            proc.returncode,
        )

        if stdout:
            logger.error(
                "Node adapter stdout: %s",
                stdout[-4000:],
            )

        return None, False

    if not stdout:
        logger.error(
            "Node adapter returned empty stdout"
        )
        return None, False

    # Find the final JSON object emitted by the adapter.
    result: Optional[Dict[str, Any]] = None

    for line in reversed(stdout.splitlines()):
        line = line.strip()

        if not line:
            continue

        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(candidate, dict):
            result = candidate
            break

    if result is None:
        logger.error(
            "Node adapter produced no valid JSON result"
        )
        logger.debug(
            "Node stdout tail: %s",
            stdout[-4000:],
        )
        return None, False

    logger.info(
        "Node adapter completed: success=%s",
        result.get("success"),
    )

    if result.get("success") is True:
        # This identifier is only a compatibility identifier for the
        # synchronous caller; the actual browser lifecycle belongs to
        # the Node adapter.
        tab_id = f"node-{proc.pid}"

        logger.info(
            "Browser adapter completed successfully: %s",
            tab_id,
        )

        return tab_id, True

    logger.error(
        "Browser adapter reported failure: %s",
        result.get("error", "unknown error"),
    )

    return None, False
