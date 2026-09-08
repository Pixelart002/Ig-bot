#!/usr/bin/env python3
"""
browser_assist.py – Compatibility wrapper for the browser runner.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[..., Any]]


async def capture_screenshot(
    filename: str = "screenshot.png",
) -> Optional[bytes]:
    logger.warning("capture_screenshot() is not implemented")
    return None


async def inspect_state() -> Dict[str, Any]:
    logger.warning("inspect_state() is not implemented")
    return {
        "state": "unknown",
        "url": "",
        "title": "",
    }


async def start_keepalive() -> None:
    logger.info("start_keepalive() compatibility no-op")


async def cdp_call(
    method: str,
    params: Optional[dict] = None,
) -> Dict[str, Any]:
    logger.warning(
        "cdp_call(%s) is not implemented in this compatibility wrapper",
        method,
    )
    return {
        "result": "dummy",
        "method": method,
    }


def start_signup(
    credentials: Dict[str, Any],
    identity: Any = None,
    on_progress: ProgressCallback = None,
) -> tuple[Optional[str], bool]:
    """
    Compatibility wrapper.

    `identity` and `on_progress` are accepted so callers using the
    newer interface do not crash with an unexpected-keyword error.
    """

    if not isinstance(credentials, dict):
        logger.error("credentials must be a dictionary")
        return None, False

    if on_progress is not None:
        logger.info("Progress callback supplied")

    user_data = {
        "email": credentials.get("email"),
        "password": credentials.get("password"),
        "birthday": credentials.get("birthday"),
        "full_name": credentials.get("full_name"),
        "username": credentials.get("username"),
    }

    required = (
        "email",
        "password",
        "birthday",
        "full_name",
        "username",
    )

    missing = [key for key in required if not user_data.get(key)]

    if missing:
        logger.error("Missing required fields: %s", ", ".join(missing))
        return None, False

    user_json = json.dumps(user_data)

    try:
        proc = subprocess.run(
            ["node", "signup_flow.js", user_json],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

    except subprocess.TimeoutExpired:
        logger.error("Node process timed out")
        return None, False

    except FileNotFoundError:
        logger.error("Node.js is not installed")
        return None, False

    except OSError:
        logger.exception("Failed to start Node process")
        return None, False

    if proc.stderr.strip():
        logger.warning("Node stderr: %s", proc.stderr.strip())

    output = proc.stdout.strip()

    if not output:
        logger.error("Node process returned no stdout")
        return None, False

    result = None

    for line in reversed(output.splitlines()):
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
        logger.error("No JSON result found in Node output")
        return None, False

    logger.info("Node result: %s", result)

    if result.get("success") is True:
        return f"node-{proc.pid}", True

    logger.error(
        "Operation failed: %s",
        result.get("error", "unknown error"),
    )
    return None, False


def start_signup_sync(
    credentials: Dict[str, Any],
    identity: Any = None,
    on_progress: ProgressCallback = None,
) -> tuple[Optional[str], bool]:
    return start_signup(
        credentials,
        identity=identity,
        on_progress=on_progress,
    )
