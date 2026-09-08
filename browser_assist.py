#!/usr/bin/env python3
"""
browser_assist.py – Python wrapper for Lightpanda CDP actions.
All heavy lifting delegated to Node.js scripts.
"""

import json
import logging
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ----- Stub async functions (kept for compatibility) -----

async def capture_screenshot(filename: str = "screenshot.png") -> Optional[bytes]:
    logger.warning("capture_screenshot() not implemented – returning None")
    return None

async def inspect_state() -> Dict[str, Any]:
    logger.warning("inspect_state() not implemented – returning dummy")
    return {"state": "unknown", "url": "", "title": ""}

async def start_keepalive():
    logger.info("start_keepalive() called – no-op stub")

async def cdp_call(method: str, params: dict = None) -> Dict[str, Any]:
    logger.warning(f"cdp_call({method}, {params}) called – not implemented, returning dummy")
    return {"result": "dummy", "method": method}

# ----- Main signup function – SYNCHRONOUS (no asyncio) -----

def start_signup(user_data: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
    """
    Call Node.js signup_flow.js synchronously.
    Any extra args (e.g. on_progress) are ignored.
    Returns dict with 'success' and 'state'.
    """
    if args:
        logger.info(f"Extra positional args provided (ignored): {args}")
    if kwargs.get("on_progress"):
        logger.info("on_progress callback provided – ignored (Node handles progress)")

    user_json = json.dumps(user_data)
    node_script = "signup_flow.js"

    logger.info(f"🚀 Launching Node signup flow for {user_data.get('email')}")

    try:
        # Synchronous subprocess call
        proc = subprocess.run(
            ["node", node_script, user_json],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes max
        )

        if proc.stderr:
            logger.warning(f"Node stderr: {proc.stderr}")

        output = proc.stdout.strip()
        # Parse last line as JSON
        lines = output.splitlines()
        json_line = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                json_line = line
                break
        if not json_line:
            logger.error(f"No JSON found in output: {output}")
            return {"success": False, "state": "PARSE_ERROR", "error": "No JSON output"}

        result = json.loads(json_line)
        logger.info(f"✅ Signup result: {result}")
        return result

    except subprocess.TimeoutExpired:
        logger.error("❌ Node script timed out after 10 minutes")
        return {"success": False, "state": "TIMEOUT", "error": "Script timed out"}
    except FileNotFoundError:
        logger.error("❌ Node.js not found. Please install Node.js.")
        return {"success": False, "state": "SYSTEM_ERROR", "error": "Node not found"}
    except Exception as e:
        logger.exception(f"❌ Exception: {e}")
        return {"success": False, "state": "EXCEPTION", "error": str(e)}

# ----- (Optional) Async wrapper if someone still uses await -----
async def start_signup_async(user_data: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
    """Async wrapper for the synchronous function (rarely needed)."""
    return start_signup(user_data, *args, **kwargs)
