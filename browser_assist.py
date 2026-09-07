"""Execution adapter for the real Lightpanda CDP signup flow."""
from __future__ import annotations

import time

from browser_assist_v2 import *
from browser_assist_v2 import _advance, _evaluate


def start_signup(credentials: dict, identity: dict):
    """Open Instagram and perform the first real CDP form action immediately.

    The worker continues the same browser target/session while the page is in
    waiting state. There is no frontend-only success path here: every form
    action goes through the original Lightpanda CDP websocket.
    """
    tab = open_signup()

    # Wait briefly for the real document to leave the loading state, then
    # execute the first available signup action synchronously. This prevents
    # Telegram/UI state from reporting "started" while CDP has not actually
    # touched the page yet.
    deadline = time.time() + 12.0
    state = "waiting"
    while time.time() < deadline:
        try:
            ready = _evaluate(tab, "document.readyState")
            if ready != "loading":
                state = _advance(tab, credentials, identity)
                tab["signup_state"] = state
                break
        except Exception:
            if tab.get("_connection_dead"):
                raise
        time.sleep(0.5)

    # Keep actively executing against the same CDP target while waiting for
    # the next Instagram screen/field. No reattach/new browser connection.
    start_signup_progression(tab, credentials, identity)
    return tab, state in {"progressed", "otp_required", "captcha_required", "completed", "username_submitted"}


__all__ = [name for name in globals() if not name.startswith("_")] + ["_evaluate"]
