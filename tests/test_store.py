import sqlite3
import unittest

from lib import store
from tests.helpers import temp_business


class InsertAndGetTests(unittest.TestCase):
    def test_insert_and_get(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "ext-1", "Alice", 5, "great", "2026-01-01T00:00:00Z")
            self.assertIsNotNone(rid)
            row = store.get_review(conn, rid)
            self.assertEqual(row["external_id"], "ext-1")
            self.assertEqual(row["status"], "new")
            self.assertIsNone(row["reply_source"])

    def test_insert_duplicate_returns_none(self):
        with temp_business():
            conn = store.connect()
            store.insert_review(conn, "ext-1", "Alice", 5, "great", "2026-01-01T00:00:00Z")
            second = store.insert_review(conn, "ext-1", "Alice", 5, "great", "2026-01-01T00:00:00Z")
            self.assertIsNone(second)

    def test_insert_with_existing_reply_marks_posted_owner(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(
                conn, "ext-2", "Bob", 4, "nice", "2026-01-01T00:00:00Z", existing_reply="Thanks!"
            )
            row = store.get_review(conn, rid)
            self.assertEqual(row["status"], "posted")
            self.assertEqual(row["reply_source"], "owner")
            self.assertEqual(row["posted_reply"], "Thanks!")

    def test_get_missing_review_returns_none(self):
        with temp_business():
            conn = store.connect()
            self.assertIsNone(store.get_review(conn, 999))


class UpdateAndListTests(unittest.TestCase):
    def test_update_review(self):
        with temp_business():
            conn = store.connect()
            rid = store.insert_review(conn, "ext-3", "C", 3, "ok", "2026-01-01T00:00:00Z")
            store.update_review(conn, rid, status="pending_review", draft_reply="hi")
            row = store.get_review(conn, rid)
            self.assertEqual(row["status"], "pending_review")
            self.assertEqual(row["draft_reply"], "hi")

    def test_list_reviews_filters_by_status(self):
        with temp_business():
            conn = store.connect()
            store.insert_review(conn, "a", "A", 5, "x", "2026-01-01T00:00:00Z")
            rid2 = store.insert_review(conn, "b", "B", 5, "y", "2026-01-02T00:00:00Z")
            store.update_review(conn, rid2, status="posted")
            new_only = store.list_reviews(conn, status="new")
            self.assertEqual([r["external_id"] for r in new_only], ["a"])

    def test_list_reviews_no_filter_returns_all(self):
        with temp_business():
            conn = store.connect()
            store.insert_review(conn, "a", "A", 5, "x", "2026-01-01T00:00:00Z")
            store.insert_review(conn, "b", "B", 5, "y", "2026-01-02T00:00:00Z")
            self.assertEqual(len(store.list_reviews(conn)), 2)


class MigrationTests(unittest.TestCase):
    def test_backfills_reply_source_from_pre_migration_schema(self):
        with temp_business() as business:
            # Simulate a DB created before the reply_source column existed.
            conn = sqlite3.connect(business.db_path)
            conn.execute(
                """
                CREATE TABLE reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_id TEXT UNIQUE NOT NULL,
                    author_name TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    create_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    category TEXT, sentiment TEXT, urgency TEXT, confidence REAL,
                    reasoning TEXT, draft_reply TEXT, posted_reply TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO reviews (external_id, author_name, rating, text, create_time, "
                "status, posted_reply, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("owner-1", "A", 5, "x", "2026-01-01T00:00:00Z", "posted", "Thanks", "ts", "ts"),
            )
            conn.execute(
                "INSERT INTO reviews (external_id, author_name, rating, text, create_time, "
                "status, posted_reply, reasoning, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("agent-1", "B", 5, "y", "2026-01-02T00:00:00Z", "posted", "Nice one", "why", "ts", "ts"),
            )
            conn.commit()
            conn.close()

            conn = store.connect()  # triggers _migrate
            owner_row = conn.execute("SELECT * FROM reviews WHERE external_id = 'owner-1'").fetchone()
            agent_row = conn.execute("SELECT * FROM reviews WHERE external_id = 'agent-1'").fetchone()
            self.assertEqual(owner_row["reply_source"], "owner")
            self.assertEqual(agent_row["reply_source"], "agent")


class RunLogTests(unittest.TestCase):
    def test_log_run_and_last_run(self):
        with temp_business():
            conn = store.connect()
            self.assertIsNone(store.last_run(conn))
            store.log_run(conn, fetched=10, already_replied=8, processed=2, posted=1, escalated=0, queued=1, notes="ok")
            run = store.last_run(conn)
            self.assertEqual(run["fetched"], 10)
            self.assertEqual(run["posted"], 1)
            self.assertEqual(run["notes"], "ok")

    def test_last_run_returns_most_recent(self):
        with temp_business():
            conn = store.connect()
            store.log_run(conn, fetched=1, already_replied=0, processed=1, posted=1, escalated=0, queued=0)
            store.log_run(conn, fetched=2, already_replied=0, processed=2, posted=0, escalated=1, queued=1)
            run = store.last_run(conn)
            self.assertEqual(run["fetched"], 2)


if __name__ == "__main__":
    unittest.main()
