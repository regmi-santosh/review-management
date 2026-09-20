import io
import unittest

from PIL import Image

from lib import config, social_image, store
from lib.milestones import check_milestones
from tests.helpers import temp_business


def _seed_reviews(conn, ratings_in_order):
    for i, rating in enumerate(ratings_in_order):
        store.insert_review(
            conn, f"ext-{i}", f"Author {i}", rating, "text", f"2026-01-{i + 1:02d}T00:00:00Z"
        )


class ReviewCountMilestoneTests(unittest.TestCase):
    def test_crosses_configured_threshold(self):
        facts = {"milestone_thresholds": [3]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 4, 5])
            crossed = check_milestones(conn, business)
            self.assertEqual(len(crossed), 1)
            self.assertEqual(crossed[0]["type"], "review_count")
            self.assertEqual(crossed[0]["threshold"], 3)

    def test_is_idempotent_across_repeated_calls(self):
        facts = {"milestone_thresholds": [2]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5])
            first = check_milestones(conn, business)
            second = check_milestones(conn, business)
            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])

    def test_batch_crossing_multiple_thresholds_attributes_each_correctly(self):
        """A single run inserting several reviews at once can jump straight
        past more than one threshold - each should be recorded against the
        specific review that actually reached it, not all against the last
        one in the batch."""
        facts = {"milestone_thresholds": [2, 4]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5, 5, 5])
            crossed = check_milestones(conn, business)
            by_threshold = {c["threshold"]: c["reached_review_id"] for c in crossed}
            self.assertEqual(set(by_threshold), {2, 4})
            self.assertNotEqual(by_threshold[2], by_threshold[4])

    def test_defaults_to_generic_list_when_unset(self):
        with temp_business() as business:
            self.assertIn(500, business.milestone_thresholds)


class RatingStreakMilestoneTests(unittest.TestCase):
    def test_no_op_when_not_configured(self):
        with temp_business() as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5, 5, 5, 5])
            crossed = check_milestones(conn, business)
            self.assertEqual(business.rating_streak_milestones, [])
            self.assertEqual([c for c in crossed if c["type"] == "rating_streak"], [])

    def test_crosses_streak_threshold(self):
        facts = {"rating_streak_milestones": [3]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5, 5])
            crossed = check_milestones(conn, business)
            streak_events = [c for c in crossed if c["type"] == "rating_streak"]
            self.assertEqual(len(streak_events), 1)
            self.assertEqual(streak_events[0]["threshold"], 3)

    def test_streak_resets_on_non_five_star(self):
        facts = {"rating_streak_milestones": [3]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5, 3, 5, 5])
            crossed = check_milestones(conn, business)
            self.assertEqual([c for c in crossed if c["type"] == "rating_streak"], [])

    def test_streak_that_spikes_and_breaks_within_one_batch_is_still_caught(self):
        """A streak can reset and rebuild within a single check_milestones()
        call (e.g. one day's fetch brings in a mixed batch) - detection
        walks reviews chronologically rather than only inspecting the final
        state, so a threshold crossed mid-batch is still recorded even
        though the streak has since broken."""
        facts = {"rating_streak_milestones": [3]}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            _seed_reviews(conn, [5, 5, 5, 3, 5])
            crossed = check_milestones(conn, business)
            streak_events = [c for c in crossed if c["type"] == "rating_streak"]
            self.assertEqual(len(streak_events), 1)


class AnniversaryMilestoneTests(unittest.TestCase):
    def test_no_op_when_founded_date_unset(self):
        with temp_business() as business:
            conn = store.connect()
            self.assertIsNone(business.founded_date)
            crossed = check_milestones(conn, business)
            self.assertEqual([c for c in crossed if c["type"] == "anniversary"], [])

    def test_crosses_anniversary_years_when_founded_date_set(self):
        facts = {"founded_date": "2020-01-01"}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            crossed = check_milestones(conn, business)
            anniversary_events = [c for c in crossed if c["type"] == "anniversary"]
            # 2020-01-01 to "today" (test runs post-2026) is at least 5 full years.
            self.assertGreaterEqual(len(anniversary_events), 5)
            self.assertIn(1, {c["threshold"] for c in anniversary_events})

    def test_anniversary_is_idempotent(self):
        facts = {"founded_date": "2020-01-01"}
        with temp_business(business_facts=facts) as business:
            conn = store.connect()
            first = check_milestones(conn, business)
            second = check_milestones(conn, business)
            self.assertGreater(len([c for c in first if c["type"] == "anniversary"]), 0)
            self.assertEqual([c for c in second if c["type"] == "anniversary"], [])


class StoreMilestoneHelperTests(unittest.TestCase):
    def test_record_and_list_milestones(self):
        with temp_business():
            conn = store.connect()
            milestone_id = store.record_milestone(conn, "review_count", 100, None)
            milestone = store.get_milestone(conn, milestone_id)
            self.assertEqual(milestone["type"], "review_count")
            self.assertEqual(milestone["threshold"], 100)
            self.assertEqual(milestone["status"], "drafted")
            self.assertIn(100, store.get_recorded_milestone_thresholds(conn, "review_count"))

    def test_milestone_posts_upsert_and_mark_posted(self):
        with temp_business():
            conn = store.connect()
            milestone_id = store.record_milestone(conn, "review_count", 100, None)
            store.save_milestone_posts(
                conn, milestone_id, {"facebook": "100 reviews!"}, {"facebook": "/tmp/x.png"}
            )
            posts = store.list_milestone_posts(conn, milestone_id)
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["status"], "drafted")

            store.mark_milestone_post_posted(conn, milestone_id, "facebook", "ext-post-1")
            posts = store.list_milestone_posts(conn, milestone_id)
            self.assertEqual(posts[0]["status"], "posted")
            self.assertEqual(posts[0]["external_post_id"], "ext-post-1")


class RenderMilestoneCardTests(unittest.TestCase):
    def test_produces_valid_png_at_requested_size(self):
        with temp_business() as business:
            png_bytes = social_image.render_milestone_card(business, "500+ Reviews!", business.name, (1200, 630))
            image = Image.open(io.BytesIO(png_bytes))
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1200, 630))

    def test_handles_empty_subline_without_error(self):
        with temp_business() as business:
            png_bytes = social_image.render_milestone_card(business, "5 Years Strong!", "", (1080, 1080))
            self.assertGreater(len(png_bytes), 0)


if __name__ == "__main__":
    unittest.main()
