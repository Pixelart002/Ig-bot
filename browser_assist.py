"""Execution adapter for the real Lightpanda CDP signup flow."""
from __future__ import annotations

import time

import browser_assist_v2 as _cdp
from browser_assist_v2 import *
from browser_assist_v2 import _evaluate
from signup_flow import advance as _deterministic_advance

# Keep the existing CDP transport/helpers, but replace the old field-order
# heuristic with the deterministic screen-by-screen state machine.
_cdp._advance = _deterministic_advance


def start_signup(credentials: dict, identity: dict):
    """Open Instagram and execute the first real CDP signup action."""
    tab = open_signup()
    tab["_credentials"] = dict(credentials)
    tab["_identity"] = identity

    deadline = time.time() + 12.0
    state = "waiting"
    while time.time() < deadline:
        try:
            ready = _evaluate(tab, "document.readyState")
            if ready != "loading":
                state = _deterministic_advance(tab, credentials, identity)
                tab["signup_state"] = state
                break
        except Exception:
            if tab.get("_connection_dead"):
                raise
        time.sleep(0.5)

    # start_signup_progression resolves _advance from browser_assist_v2 at
    # runtime, so the patched deterministic implementation is used while the
    # same original Lightpanda websocket/session remains alive.
    start_signup_progression(tab, credentials, identity)
    return tab, state in {"progressed", "otp_required", "captcha_required", "completed", "username_submitted"}


__all__ = [name for name in globals() if not name.startswith("_")] + ["_evaluate"]
