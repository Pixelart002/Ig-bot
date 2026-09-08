#!/usr/bin/env python3
"""
browser_assist.py – Python wrapper for Lightpanda CDP actions.
All heavy lifting delegated to Node.js scripts.
"""

import asyncio
import json
import logging
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ----- Stub functions (to keep imports working) -----

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

# ----- Main signup function – accepts any extra positional/keyword args -----

async def start_signup(user_data: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
    """
    Call Node.js signup_flow.js with given user_data.
    Any extra positional arguments (like on_progress callback) are ignored.
    """
    # Log if a progress callback was provided (it's usually the second positional arg)
    if len(args) > 0:
        logger.info(f"Extra positional arguments provided (ignored): {args}")
    if kwargs.get("on_progress"):
        logger.info("on_progress callback provided – but ignored in this wrapper (Node handles progress)")

    user_json = json.dumps(user_data)
    node_script = "signup_flow.js"

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

# ----- Synchronous wrapper -----
def start_signup_sync(user_data: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(start_signup(user_data))
