"""Regression tests for deterministic signup progression helpers."""
from __future__ import annotations

import unittest
from threading import Event
from unittest.mock import patch

import requests
import signup_flow
import telegram_bot
import workflow
from ig_bot import _validate_identity, generate_identity


class UsernameProgressionTests(unittest.TestCase):
    def test_keeps_an_already_accepted_username(self) -> None:
        tab: dict = {}
        identity: dict = {"usernames": ["first_choice", "second_choice"]}
        snapshot = {
            "url": "https://www.instagram.com/accounts/signup/",
            "readyState": "complete",
            "text": "Choose a username",
            "inputs": [
                {
                    "index": 0,
                    "visible": True,
                    "disabled": False,
                    "type": "text",
                    "name": "username",
                    "value": "accepted_name",
                }
            ],
            "buttons": [],
        }

        with (
            patch.object(signup_flow.cdp, "_snapshot", return_value=snapshot),
            patch.object(signup_flow, "_click_action", return_value=True) as click,
            patch.object(signup_flow, "_wait_change", return_value=True),
            patch.object(signup_flow, "_fill_verify") as fill,
        ):
            result = signup_flow._username(tab, identity)

        self.assertEqual("progressed", result)
        self.assertEqual("accepted_name", identity["selected_username"])
        self.assertEqual("accepted_name", identity["username"])
        click.assert_called_once_with(tab)
        fill.assert_not_called()


class SessionCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        with workflow._lock:
            workflow._sessions.clear()

    def tearDown(self) -> None:
        with workflow._lock:
            workflow._sessions.clear()

    def test_clear_closes_the_owned_browser_tab(self) -> None:
        session = workflow.Session(chat_id=123, tab={"_ws": object(), "_signup_stop": Event()})
        with workflow._lock:
            workflow._sessions[session.chat_id] = session

        with patch("browser_assist_v2.close_tab") as close_tab:
            workflow.clear(session.chat_id)

        close_tab.assert_called_once_with(session.tab)
        self.assertFalse(session.otp_polling)


class IdentityFallbackTests(unittest.TestCase):
    def test_invalid_ai_identity_uses_a_valid_local_fallback(self) -> None:
        incomplete = '{"display_names":["One"],"usernames":["one"],"bios":["Bio"]}'
        with patch("ig_bot.ai_chat", return_value=incomplete):
            identity = generate_identity()

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual("local_fallback", identity["source"])
        self.assertEqual(5, len(identity["usernames"]))
        self.assertEqual(identity, _validate_identity(identity))


class TelegramFormattingTests(unittest.TestCase):
    def test_identity_text_escapes_html_sensitive_values(self) -> None:
        text = telegram_bot.identity_text({"display_names": ["A < B"], "usernames": ["name_with_underscore"], "bios": ["Use & share"], "password": "a<>&"})

        self.assertIn("A &lt; B", text)
        self.assertIn("Use &amp; share", text)
        self.assertIn("a&lt;&gt;&amp;", text)

    def test_expired_callback_acknowledgement_does_not_abort_handling(self) -> None:
        with patch.object(telegram_bot, "tg", side_effect=requests.HTTPError("expired")):
            telegram_bot.answer_callback("callback", "Processing")


if __name__ == "__main__":
    unittest.main()
