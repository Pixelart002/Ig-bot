#!/usr/bin/env python3
"""
browser_assist.py – Python wrapper for Lightpanda CDP actions.
All heavy lifting is delegated to Node.js scripts.
"""

import asyncio
import json
import logging
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ----- Existing functions (now stubs or implemented via Node) -----

async def capture_screenshot(filename: str = "screenshot.png") -> Optional[bytes]:
    """
    Capture screenshot of current page.
    STUB: logs a warning and returns None.
    To implement, create a Node script (screenshot.js) that uses CDP.
    """
    logger.warning("capture_screenshot() not implemented yet – returning None")
    return None

async def inspect_state() -> Dict[str, Any]:
    """
    Inspect current page state (e.g., URL, title, etc.)
    STUB: returns a dummy dictionary.
    """
    logger.warning("inspect_state() not implemented yet – returning dummy")
    return {"state": "unknown", "url": "", "title": ""}

async def start_keepalive():
    """
    Start a keep-alive mechanism (e.g., periodic page refresh).
    STUB: does nothing.
    """
    logger.info("start_keepalive() called – no-op stub")

# ----- Main signup function (uses Node script) -----

async def start_signup(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Node.js signup_flow.js with the given user data.
    Returns a dict with 'success' and 'state'.
    """
    user_json = json.dumps(user_data)
    node_script = "signup_flow.js"   # Ensure this file exists in root

    logger.info(f"🚀 Launching Node signup flow for {user_data.get('email')}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", node_script, user_json,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if stderr:
            logger.warning(f"Node stderr: {stderr.decode()}")

        output = stdout.decode().strip()
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

    except FileNotFoundError:
        logger.error("❌ Node.js not found. Please install Node.js.")
        return {"success": False, "state": "SYSTEM_ERROR", "error": "Node not found"}
    except Exception as e:
        logger.exception(f"❌ Exception: {e}")
        return {"success": False, "state": "EXCEPTION", "error": str(e)}

# ----- Synchronous wrappers (if needed) -----

def start_signup_sync(user_data: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(start_signup(user_data))

# We keep the same function names as before so telegram_bot imports work.
