import unittest

from lib import store
from lib.summary import build_summary_text
from tests.helpers import temp_business


class BuildSummaryTextTests(unittest.TestCase):
    def test_no_runs_yet(self):
        with temp_business() as business:
            conn = store.connect()
            text = build_summary_text(conn, business)
            self.assertIn("No runs logged yet.", text)
            self.assertIn(business.name, text)

    def test_includes_last_run_tallies(self):
        with temp_business() as business:
            conn = store.connect()
            store.log_run(conn, fetched=10, already_replied=8, processed=2, posted=1, escalated=1, queued=0)
            text = build_summary_text(conn, business)
            self.assertIn("1 posted, 1 escalated, 0 queued", text)

    def test_includes_current_queue_counts(self):
        with temp_business() as business:
            conn = store.connect()
            rid1 = store.insert_review(conn, "a", "A", 5, "x", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid1, status="pending_review")
            rid2 = store.insert_review(conn, "b", "B", 1, "y", "2026-01-02T00:00:00Z")
            store.update_review(conn, rid2, status="escalated")
            text = build_summary_text(conn, business)
            self.assertIn("1 pending review, 1 escalated", text)

    def test_highlights_included_when_given(self):
        with temp_business() as business:
            conn = store.connect()
            text = build_summary_text(conn, business, highlights="a great review came in")
            self.assertIn("Highlights: a great review came in", text)

    def test_highlights_omitted_when_not_given(self):
        with temp_business() as business:
            conn = store.connect()
            text = build_summary_text(conn, business)
            self.assertNotIn("Highlights:", text)


if __name__ == "__main__":
    unittest.main()
