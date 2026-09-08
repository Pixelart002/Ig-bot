#!/usr/bin/env python3
"""
Python wrapper for Lightpanda signup flow using Node.js subprocess.
"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def start_signup(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Node.js signup_flow.js with the given user data.
    Returns a dict with 'success' and 'state' (and optionally 'error').
    """
    # Convert user_data to JSON string
    user_json = json.dumps(user_data)
    
    # Path to Node script (adjust if needed)
    node_script = "signup_flow.js"
    
    logger.info(f"🚀 Launching Node signup flow for {user_data.get('email')}")
    
    # Run the Node script as a subprocess
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", node_script, user_json,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        # Log any stderr (warnings etc.) but don't fail yet
        if stderr:
            logger.warning(f"Node stderr: {stderr.decode()}")
        
        # Parse stdout JSON
        output = stdout.decode().strip()
        # The script might log extra lines, but we assume the last line is JSON.
        # Better: we wrote the script to output ONLY the JSON as the last line.
        # To be safe, find the last line that looks like JSON.
        lines = output.splitlines()
        json_line = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                json_line = line
                break
        if not json_line:
            logger.error(f"No JSON found in output: {output}")
            return {"success": False, "state": "PARSE_ERROR", "error": "No JSON output from Node"}
        
        result = json.loads(json_line)
        logger.info(f"✅ Signup result: {result}")
        return result
        
    except FileNotFoundError:
        logger.error("❌ Node.js not found. Please install Node.js.")
        return {"success": False, "state": "SYSTEM_ERROR", "error": "Node not found"}
    except Exception as e:
        logger.exception(f"❌ Exception while calling Node script: {e}")
        return {"success": False, "state": "EXCEPTION", "error": str(e)}

# Optional: synchronous wrapper if needed
def start_signup_sync(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous version for non-async contexts."""
    return asyncio.run(start_signup(user_data))
