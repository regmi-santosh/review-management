import unittest
import urllib.error
from unittest.mock import patch

from lib import notifier
from tests.helpers import temp_business

REVIEW = {"rating": 1, "author_name": "Angela", "text": "bad experience", "draft_reply": None}


class GetConfiguredNotifiersTests(unittest.TestCase):
    def test_none_configured_returns_empty(self):
        with temp_business() as business:
            self.assertEqual(notifier.get_configured_notifiers(business), [])

    def test_telegram_only(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_BOT_TOKEN", "tok")
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            connectors = notifier.get_configured_notifiers(business)
            self.assertEqual(len(connectors), 1)
            self.assertIsInstance(connectors[0], notifier.TelegramNotifier)

    def test_slack_only(self):
        facts = {"slack_webhook_url": "https://hooks.slack.com/services/x"}
        with temp_business(business_facts=facts) as business:
            connectors = notifier.get_configured_notifiers(business)
            self.assertEqual(len(connectors), 1)
            self.assertIsInstance(connectors[0], notifier.SlackNotifier)

    def test_both_configured_returns_both(self):
        facts = {"slack_webhook_url": "https://hooks.slack.com/services/x"}
        with temp_business(business_facts=facts) as business:
            business.save_secret("TELEGRAM_BOT_TOKEN", "tok")
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            connectors = notifier.get_configured_notifiers(business)
            self.assertEqual(len(connectors), 2)

    def test_telegram_requires_both_token_and_chat_id(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_BOT_TOKEN", "tok")  # no chat id
            self.assertEqual(notifier.get_configured_notifiers(business), [])


class NotifyEscalationTests(unittest.TestCase):
    def test_falls_back_to_console_when_nothing_configured(self):
        with temp_business():
            with patch("builtins.print") as mock_print:
                notifier.notify_escalation(REVIEW, "test reason")
            printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
            self.assertIn("test reason", printed)

    def test_sends_via_every_configured_connector(self):
        facts = {"slack_webhook_url": "https://hooks.slack.com/services/x"}
        with temp_business(business_facts=facts) as business:
            business.save_secret("TELEGRAM_BOT_TOKEN", "tok")
            business.save_secret("TELEGRAM_CHAT_ID", "123")

            with patch.object(notifier.SlackNotifier, "send") as mock_slack_send:
                with patch.object(notifier.TelegramNotifier, "send") as mock_telegram_send:
                    with patch("builtins.print") as mock_print:
                        notifier.notify_escalation(REVIEW, "test reason")

            mock_slack_send.assert_called_once()
            mock_telegram_send.assert_called_once()
            self.assertIn("test reason", mock_slack_send.call_args[0][0])
            # No console fallback needed since at least one connector succeeded.
            printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
            self.assertNotIn("[notify]", printed)

    def test_falls_back_to_console_when_every_send_fails(self):
        facts = {"slack_webhook_url": "https://hooks.slack.com/services/x"}
        with temp_business(business_facts=facts):
            with patch.object(notifier.SlackNotifier, "send", side_effect=urllib.error.URLError("boom")):
                with patch("builtins.print") as mock_print:
                    notifier.notify_escalation(REVIEW, "test reason")
            printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
            self.assertIn("test reason", printed)

    def test_one_connector_failing_does_not_block_the_other(self):
        facts = {"slack_webhook_url": "https://hooks.slack.com/services/x"}
        with temp_business(business_facts=facts) as business:
            business.save_secret("TELEGRAM_BOT_TOKEN", "tok")
            business.save_secret("TELEGRAM_CHAT_ID", "123")

            with patch.object(notifier.SlackNotifier, "send", side_effect=urllib.error.URLError("boom")):
                with patch.object(notifier.TelegramNotifier, "send") as mock_telegram_send:
                    with patch("builtins.print") as mock_print:
                        notifier.notify_escalation(REVIEW, "test reason")

            mock_telegram_send.assert_called_once()
            # Telegram succeeded, so no console fallback - but the Slack failure is logged.
            printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
            self.assertIn("Slack", printed)
            self.assertNotIn("[notify] \U0001F6A8", printed)


if __name__ == "__main__":
    unittest.main()
