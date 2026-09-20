import unittest
import unittest.mock
from unittest.mock import patch

from lib import actions, store
from lib.google_client import RawReview
from tests.helpers import temp_business


class FakeGoogleClient:
    def __init__(self, reviews=None):
        self.posted = []
        self._reviews = reviews or []

    def post_reply(self, external_id, location_id, text):
        self.posted.append((external_id, location_id, text))

    def fetch_reviews(self):
        return self._reviews


class PostReviewReplyTests(unittest.TestCase):
    def test_posts_and_marks_agent_source(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(
                conn, "e1", "A", 5, "x", "2026-01-01T00:00:00Z", location_id="loc-1"
            )
            store.update_review(conn, rid, draft_reply="Thanks so much!")

            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                result = actions.post_review_reply(conn, rid)

            self.assertEqual(result["status"], "posted")
            self.assertEqual(result["reply_source"], "agent")
            self.assertEqual(result["posted_reply"], "Thanks so much!")
            self.assertEqual(fake.posted, [("e1", "loc-1", "Thanks so much!")])

    def test_text_override_wins_over_draft(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e2", "B", 5, "x", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid, draft_reply="original draft")

            fake = FakeGoogleClient()
            with patch("lib.actions.get_google_client", return_value=fake):
                result = actions.post_review_reply(conn, rid, text="edited by human")

            self.assertEqual(result["posted_reply"], "edited by human")
            self.assertEqual(fake.posted, [("e2", None, "edited by human")])

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
                def post_reply(self, external_id, location_id, text):
                    raise RuntimeError("boom")

            with patch("lib.actions.get_google_client", return_value=FailingClient()):
                with self.assertRaises(RuntimeError):
                    actions.post_review_reply(conn, rid)

            row = store.get_review(conn, rid)
            self.assertEqual(row["status"], "pending_review")


class FetchAndStoreNewReviewsTests(unittest.TestCase):
    def test_returns_new_reviews_and_counts(self):
        with temp_business():
            conn = store.connect()
            client = FakeGoogleClient(
                reviews=[
                    RawReview("ext-1", "A", 5, "great", "2026-01-01T00:00:00Z"),
                    RawReview("ext-2", "B", 4, "good", "2026-01-02T00:00:00Z", existing_reply="Thanks!"),
                ]
            )
            result = actions.fetch_and_store_new_reviews(conn, client)
            self.assertEqual(result["fetched"], 2)
            self.assertEqual(result["already_replied"], 1)
            self.assertEqual(len(result["new"]), 1)
            self.assertEqual(result["new"][0]["external_id"], "ext-1")
            self.assertNotIn("batch_too_large", result)

    def test_resurfaces_previously_stored_new_reviews_not_just_this_batch(self):
        with temp_business():
            conn = store.connect()
            store.insert_review(conn, "ext-old", "Old", 5, "x", "2026-01-01T00:00:00Z")
            result = actions.fetch_and_store_new_reviews(conn, FakeGoogleClient(reviews=[]))
            self.assertEqual(result["fetched"], 0)
            self.assertEqual(len(result["new"]), 1)
            self.assertEqual(result["new"][0]["external_id"], "ext-old")

    def test_batch_too_large_returns_flag_without_raising(self):
        with temp_business():
            conn = store.connect()
            reviews = [
                RawReview(f"ext-{i}", "A", 5, "x", "2026-01-01T00:00:00Z") for i in range(5)
            ]
            result = actions.fetch_and_store_new_reviews(conn, FakeGoogleClient(reviews=reviews), max_batch=3)
            self.assertTrue(result["batch_too_large"])
            self.assertEqual(result["actionable_count"], 5)
            self.assertEqual(result["new"], [])

    def test_allow_large_batch_bypasses_the_guardrail(self):
        with temp_business():
            conn = store.connect()
            reviews = [
                RawReview(f"ext-{i}", "A", 5, "x", "2026-01-01T00:00:00Z") for i in range(5)
            ]
            result = actions.fetch_and_store_new_reviews(
                conn, FakeGoogleClient(reviews=reviews), max_batch=3, allow_large_batch=True
            )
            self.assertNotIn("batch_too_large", result)
            self.assertEqual(len(result["new"]), 5)


class DraftSocialPostForReviewTests(unittest.TestCase):
    def test_renders_and_saves_for_enabled_platform(self):
        with temp_business(business_facts={"social_platforms": ["facebook"]}):
            conn = store.connect()
            rid = store.insert_review(conn, "e10", "A", 5, "Loved it!", "2026-01-01T00:00:00Z")
            result = actions.draft_social_post_for_review(conn, rid, "Great review, thanks!")
            self.assertIn("facebook", result["rendered"])
            self.assertIn("facebook", result["images"])
            self.assertIsNone(result["warning"])
            posts = store.list_social_posts(conn, rid)
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["status"], "drafted")

    def test_missing_review_raises(self):
        with temp_business():
            conn = store.connect()
            with self.assertRaises(ValueError):
                actions.draft_social_post_for_review(conn, 999, "caption")

    def test_warns_on_unknown_platform_typo(self):
        with temp_business(business_facts={"social_platforms": ["facebok"]}):
            conn = store.connect()
            rid = store.insert_review(conn, "e11", "B", 5, "great", "2026-01-01T00:00:00Z")
            result = actions.draft_social_post_for_review(conn, rid, "caption")
            self.assertIsNotNone(result["warning"])
            self.assertEqual(result["rendered"], {})


class DraftSocialPostForMilestoneTests(unittest.TestCase):
    def test_renders_and_saves_for_enabled_platform(self):
        with temp_business(business_facts={"social_platforms": ["facebook"]}):
            conn = store.connect()
            milestone_id = store.record_milestone(conn, "review_count", 100, None)
            result = actions.draft_social_post_for_milestone(conn, milestone_id, "100 reviews!")
            self.assertIn("facebook", result["rendered"])
            self.assertIn("facebook", result["images"])
            posts = store.list_milestone_posts(conn, milestone_id)
            self.assertEqual(len(posts), 1)

    def test_missing_milestone_raises(self):
        with temp_business():
            conn = store.connect()
            with self.assertRaises(ValueError):
                actions.draft_social_post_for_milestone(conn, 999, "caption")


class PublishSocialPostTests(unittest.TestCase):
    def test_requires_exactly_one_target(self):
        with temp_business():
            conn = store.connect()
            with self.assertRaises(ValueError):
                actions.publish_social_post(conn, "facebook")
            with self.assertRaises(ValueError):
                actions.publish_social_post(conn, "facebook", review_id=1, milestone_id=1)

    def test_publishes_drafted_review_post_and_marks_posted(self):
        with temp_business(business_facts={"social_platforms": ["facebook"]}):
            conn = store.connect()
            rid = store.insert_review(conn, "e12", "C", 5, "great", "2026-01-01T00:00:00Z")
            actions.draft_social_post_for_review(conn, rid, "caption")

            fake_platform = unittest.mock.Mock()
            fake_platform.post.return_value = "external-id-123"
            with patch("lib.actions.social_platforms.get_platform", return_value=fake_platform):
                external_id = actions.publish_social_post(conn, "facebook", review_id=rid)

            self.assertEqual(external_id, "external-id-123")
            posts = store.list_social_posts(conn, rid)
            self.assertEqual(posts[0]["status"], "posted")
            self.assertEqual(posts[0]["external_post_id"], "external-id-123")

    def test_raises_when_no_draft_exists(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "e13", "D", 5, "great", "2026-01-01T00:00:00Z")
            with self.assertRaises(ValueError):
                actions.publish_social_post(conn, "facebook", review_id=rid)

    def test_raises_when_already_posted(self):
        with temp_business(business_facts={"social_platforms": ["facebook"]}):
            conn = store.connect()
            rid = store.insert_review(conn, "e14", "E", 5, "great", "2026-01-01T00:00:00Z")
            actions.draft_social_post_for_review(conn, rid, "caption")
            fake_platform = unittest.mock.Mock()
            fake_platform.post.return_value = "ext-1"
            with patch("lib.actions.social_platforms.get_platform", return_value=fake_platform):
                actions.publish_social_post(conn, "facebook", review_id=rid)
                with self.assertRaises(ValueError):
                    actions.publish_social_post(conn, "facebook", review_id=rid)


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
