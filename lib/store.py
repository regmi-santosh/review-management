"""Plain sqlite3 (stdlib, no ORM) storage for reviews. Tools call these
functions directly; rows are plain dicts.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "review_management.db"

VALID_STATUSES = {"new", "pending_review", "escalated", "posted", "rejected"}
VALID_CATEGORIES = {"compliment", "complaint", "question", "spam", "other"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
VALID_URGENCIES = {"low", "normal", "high", "critical"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,
    author_name TEXT NOT NULL,
    rating INTEGER NOT NULL,
    text TEXT NOT NULL,
    create_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    sentiment TEXT,
    urgency TEXT,
    confidence REAL,
    reasoning TEXT,
    draft_reply TEXT,
    posted_reply TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_review(
    conn: sqlite3.Connection,
    external_id: str,
    author_name: str,
    rating: int,
    text: str,
    create_time: str,
) -> Optional[int]:
    """Insert a new review if external_id isn't already known.

    Returns the new row id, or None if it already existed.
    """
    existing = conn.execute(
        "SELECT id FROM reviews WHERE external_id = ?", (external_id,)
    ).fetchone()
    if existing:
        return None

    ts = _now()
    cur = conn.execute(
        "INSERT INTO reviews "
        "(external_id, author_name, rating, text, create_time, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'new', ?, ?)",
        (external_id, author_name, rating, text, create_time, ts, ts),
    )
    conn.commit()
    return cur.lastrowid


def get_review(conn: sqlite3.Connection, review_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    return dict(row) if row else None


def list_reviews(conn: sqlite3.Connection, status: Optional[str] = None) -> list:
    if status:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE status = ? ORDER BY create_time DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM reviews ORDER BY create_time DESC").fetchall()
    return [dict(r) for r in rows]


def update_review(conn: sqlite3.Connection, review_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [review_id]
    conn.execute(f"UPDATE reviews SET {columns} WHERE id = ?", values)
    conn.commit()
