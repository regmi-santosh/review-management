import unittest
from unittest.mock import patch

from lib import store, telegram_bot
from tests.helpers import temp_business
from tests.test_actions import FakeGoogleClient


def _make_update(chat_id=123, text="approve", reply_to_message_id=None, update_id=1, message_id=55):
    message = {"message_id": message_id, "chat": {"id": chat_id}, "text": text}
    if reply_to_message_id is not None:
        message["reply_to_message"] = {"message_id": reply_to_message_id}
    return {"update_id": update_id, "message": message}


class ClassifyReplyTests(unittest.TestCase):
    def test_approve_keywords(self):
        for text in ("approve", "Approve", " YES ", "ok"):
            self.assertEqual(telegram_bot.classify_reply(text), "approve")

    def test_reject_keywords(self):
        for text in ("reject", "Reject", " NO ", "skip"):
            self.assertEqual(telegram_bot.classify_reply(text), "reject")

    def test_anything_else_is_edit(self):
        self.assertEqual(telegram_bot.classify_reply("Thanks so much for coming in!"), "edit")


class HandleUpdateTests(unittest.TestCase):
    def _escalated_review(self, conn, business):
        rid = store.insert_review(conn, "ext-1", "Alice", 1, "bad experience", "2026-01-01T00:00:00Z")
        store.update_review(conn, rid, status="escalated", draft_reply="Sorry about that!", telegram_message_id="10")
        return rid

    def test_ignores_wrong_chat_id(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            update = _make_update(chat_id=999)
            self.assertIsNone(telegram_bot.handle_update(conn, business, update))

    def test_ignores_message_with_no_text(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            update = _make_update()
            del update["message"]["text"]
            self.assertIsNone(telegram_bot.handle_update(conn, business, update))

    def test_no_reply_to_returns_summary(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            update = _make_update(text="hi there")
            result = telegram_bot.handle_update(conn, business, update)
            self.assertIn(f"Summary for {business.name}", result)

    def test_reply_to_unmatched_message_returns_clarification(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            update = _make_update(text="approve", reply_to_message_id=999)
            result = telegram_bot.handle_update(conn, business, update)
            self.assertIn("Couldn't match this to an open escalation", result)

    def test_reply_to_already_resolved_review(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            rid = self._escalated_review(conn, business)
            store.update_review(conn, rid, status="posted")
            update = _make_update(text="approve", reply_to_message_id=10)
            result = telegram_bot.handle_update(conn, business, update)
            self.assertIn("already handled", result)
            self.assertIn("posted", result)

    def test_reply_approve_posts_draft(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            rid = self._escalated_review(conn, business)
            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                update = _make_update(text="approve", reply_to_message_id=10)
                result = telegram_bot.handle_update(conn, business, update)
            self.assertIn(f"Posted the draft reply for review {rid}", result)
            self.assertEqual(fake.posted[0][2], "Sorry about that!")
            self.assertEqual(store.get_review(conn, rid)["status"], "posted")

    def test_reply_reject_dismisses(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            rid = self._escalated_review(conn, business)
            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                update = _make_update(text="reject", reply_to_message_id=10)
                result = telegram_bot.handle_update(conn, business, update)
            self.assertIn(f"Dismissed review {rid}", result)
            self.assertEqual(fake.posted, [])
            self.assertEqual(store.get_review(conn, rid)["status"], "rejected")

    def test_reply_with_other_text_posts_that_instead_of_draft(self):
        with temp_business() as business:
            business.save_secret("TELEGRAM_CHAT_ID", "123")
            conn = store.connect()
            rid = self._escalated_review(conn, business)
            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                update = _make_update(text="So sorry - please call us at the shop.", reply_to_message_id=10)
                result = telegram_bot.handle_update(conn, business, update)
            self.assertIn(f"Posted your reply for review {rid}", result)
            self.assertEqual(fake.posted[0][2], "So sorry - please call us at the shop.")
            self.assertEqual(store.get_review(conn, rid)["posted_reply"], "So sorry - please call us at the shop.")


if __name__ == "__main__":
    unittest.main()
