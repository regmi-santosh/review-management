import unittest
from unittest.mock import patch

from lib import actions, store
from tests.helpers import temp_business


class FakeGoogleClient:
    def __init__(self):
        self.posted = []

    def post_reply(self, external_id, text):
        self.posted.append((external_id, text))

    def fetch_reviews(self):
        return []


class PostReviewReplyTests(unittest.TestCase):
    def test_posts_and_marks_agent_source(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e1", "A", 5, "x", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid, draft_reply="Thanks so much!")

            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                result = actions.post_review_reply(conn, rid)

            self.assertEqual(result["status"], "posted")
            self.assertEqual(result["reply_source"], "agent")
            self.assertEqual(result["posted_reply"], "Thanks so much!")
            self.assertEqual(fake.posted, [("e1", "Thanks so much!")])

    def test_text_override_wins_over_draft(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e2", "B", 5, "x", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid, draft_reply="original draft")

            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                result = actions.post_review_reply(conn, rid, text="edited by human")

            self.assertEqual(result["posted_reply"], "edited by human")
            self.assertEqual(fake.posted, [("e2", "edited by human")])

    def test_requires_some_text(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e3", "C", 3, "y", "2026-01-01T00:00:00Z")
            with self.assertRaises(ValueError):
                actions.post_review_reply(conn, rid)

    def test_missing_review_raises(self):
        with temp_business():
            conn = store.connect()
            with self.assertRaises(ValueError):
                actions.post_review_reply(conn, 999)

    def test_client_failure_propagates_and_leaves_status_untouched(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e4", "D", 5, "x", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid, draft_reply="hi", status="pending_review")

            class FailingClient:
                def post_reply(self, external_id, text):
                    raise RuntimeError("boom")

            with patch("lib.actions.get_google_client", return_value=FailingClient()):
                with self.assertRaises(RuntimeError):
                    actions.post_review_reply(conn, rid)

            row = store.get_review(conn, rid)
            self.assertEqual(row["status"], "pending_review")


class RejectReviewTests(unittest.TestCase):
    def test_reject_marks_rejected(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e5", "E", 2, "z", "2026-01-01T00:00:00Z")
            result = actions.reject_review(conn, rid)
            self.assertEqual(result["status"], "rejected")

    def test_reject_missing_review_raises(self):
        with temp_business():
            conn = store.connect()
            with self.assertRaises(ValueError):
                actions.reject_review(conn, 999)


if __name__ == "__main__":
    unittest.main()
