"""Plain sqlite3 (stdlib, no ORM) storage for reviews. Tools call these
functions directly; rows are plain dicts.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from lib import config

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
    reply_source TEXT,
    location_id TEXT,
    telegram_message_id TEXT,
    profile_photo_url TEXT,
    is_anonymous INTEGER,
    draft_social_post TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at TEXT NOT NULL,
    fetched INTEGER NOT NULL,
    already_replied INTEGER NOT NULL,
    processed INTEGER NOT NULL,
    posted INTEGER NOT NULL,
    escalated INTEGER NOT NULL,
    queued INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL REFERENCES reviews(id),
    platform TEXT NOT NULL,
    text TEXT NOT NULL,
    image_path TEXT,
    status TEXT NOT NULL DEFAULT 'drafted',
    external_post_id TEXT,
    posted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(review_id, platform)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """One-time, idempotent schema migrations for DBs created before a
    column existed. Safe to run on every connect()."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(reviews)")}
    if "reply_source" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN reply_source TEXT")
        # Backfill from data shape: the agent always sets `reasoning` via
        # save_review.py before posting, so a posted review with no
        # reasoning must have gotten its reply from a pre-existing Google
        # reply captured at fetch time (see insert_review), not from us.
        conn.execute(
            "UPDATE reviews SET reply_source = 'agent' "
            "WHERE reply_source IS NULL AND reasoning IS NOT NULL"
        )
        conn.execute(
            "UPDATE reviews SET reply_source = 'owner' "
            "WHERE reply_source IS NULL AND status = 'posted' AND posted_reply IS NOT NULL"
        )
        conn.commit()

    if "location_id" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN location_id TEXT")
        # Backfill: any row predating multi-location support was necessarily
        # fetched from a single-location setup. Only safe to infer when the
        # business has exactly one location configured now - if it already
        # has several, there's no way to know which one old rows came from,
        # so they're left NULL (post_reply.py will raise a clear error if
        # one of those is ever posted to, rather than silently guessing).
        location_ids = config.active().google_location_ids
        if len(location_ids) == 1:
            conn.execute(
                "UPDATE reviews SET location_id = ? WHERE location_id IS NULL", (location_ids[0],)
            )
        conn.commit()

    if "telegram_message_id" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN telegram_message_id TEXT")
        conn.commit()

    if "profile_photo_url" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN profile_photo_url TEXT")
        conn.execute("ALTER TABLE reviews ADD COLUMN is_anonymous INTEGER")
        conn.execute("ALTER TABLE reviews ADD COLUMN draft_social_post TEXT")
        conn.commit()

    social_posts_columns = {row["name"] for row in conn.execute("PRAGMA table_info(social_posts)")}
    if "image_path" not in social_posts_columns:
        conn.execute("ALTER TABLE social_posts ADD COLUMN image_path TEXT")
        conn.commit()


def connect() -> sqlite3.Connection:
    """Connect to the active business's own DB (config.active().db_path),
    resolved fresh on every call so a tool's --business flag (applied before
    this is called) takes effect."""
    conn = sqlite3.connect(config.active().db_path)
    # Default busy_timeout is 0 (no wait/retry on lock contention). Once the
    # Telegram listener (lib/telegram_bot.py) can write to this same DB at any
    # moment while a review-handler run is also mid-flight, a brief wait here
    # is needed instead of an immediate "database is locked" error.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
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
    existing_reply: Optional[str] = None,
    location_id: Optional[str] = None,
    profile_photo_url: Optional[str] = None,
    is_anonymous: bool = False,
) -> Optional[int]:
    """Insert a new review if external_id isn't already known.

    If `existing_reply` is set (Google already has an owner reply on this
    review — e.g. posted manually, before this system existed), it's
    recorded as already `posted` so the agent never processes it and never
    overwrites that existing reply via the API.

    `location_id` identifies which of the business's locations this review
    came from (see lib.config.Business.google_location_ids) - required to
    post a reply to a multi-location business's review later.

    `profile_photo_url`/`is_anonymous` are the only other reviewer detail
    Google's API exposes (no email, no profile link) - captured for
    possible future use, not read by anything today.

    Returns the new row id, or None if it already existed.
    """
    existing = conn.execute(
        "SELECT id FROM reviews WHERE external_id = ?", (external_id,)
    ).fetchone()
    if existing:
        return None

    ts = _now()
    status = "posted" if existing_reply else "new"
    reply_source = "owner" if existing_reply else None
    cur = conn.execute(
        "INSERT INTO reviews "
        "(external_id, author_name, rating, text, create_time, status, posted_reply, reply_source, location_id, "
        "profile_photo_url, is_anonymous, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            external_id, author_name, rating, text, create_time, status, existing_reply, reply_source, location_id,
            profile_photo_url, int(is_anonymous), ts, ts,
        ),
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


def log_run(
    conn: sqlite3.Connection,
    fetched: int,
    already_replied: int,
    processed: int,
    posted: int,
    escalated: int,
    queued: int,
    notes: str = "",
) -> int:
    """Record a summary of one review-handler run, so run history survives
    beyond the chat transcript it happened in."""
    cur = conn.execute(
        "INSERT INTO runs "
        "(finished_at, fetched, already_replied, processed, posted, escalated, queued, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(), fetched, already_replied, processed, posted, escalated, queued, notes),
    )
    conn.commit()
    return cur.lastrowid


def last_run(conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def get_meta(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_review_by_telegram_message_id(conn: sqlite3.Connection, message_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM reviews WHERE telegram_message_id = ?", (message_id,)
    ).fetchone()
    return dict(row) if row else None


def save_social_posts(
    conn: sqlite3.Connection, review_id: int, rendered: dict, images: Optional[dict] = None
) -> None:
    """Upsert one row per platform in `rendered` (platform -> text) for this
    review, optionally attaching `images` (platform -> image_path, omitted
    or missing entries leave image_path unset). Idempotent — re-drafting the
    same review's social post just overwrites its per-platform row rather
    than duplicating it. A platform missing from `images` on a re-draft
    (e.g. image rendering failed this time) keeps whatever image_path that
    row already had, via COALESCE, rather than wiping out a previously
    successful render."""
    ts = _now()
    images = images or {}
    for platform, text in rendered.items():
        conn.execute(
            "INSERT INTO social_posts (review_id, platform, text, image_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(review_id, platform) DO UPDATE SET "
            "text = excluded.text, "
            "image_path = COALESCE(excluded.image_path, social_posts.image_path), "
            "updated_at = excluded.updated_at",
            (review_id, platform, text, images.get(platform), ts, ts),
        )
    conn.commit()


def list_social_posts(conn: sqlite3.Connection, review_id: int) -> list:
    rows = conn.execute(
        "SELECT * FROM social_posts WHERE review_id = ? ORDER BY platform", (review_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def mark_social_post_posted(
    conn: sqlite3.Connection, review_id: int, platform: str, external_post_id: str
) -> None:
    ts = _now()
    conn.execute(
        "UPDATE social_posts SET status = 'posted', external_post_id = ?, posted_at = ?, updated_at = ? "
        "WHERE review_id = ? AND platform = ?",
        (external_post_id, ts, ts, review_id, platform),
    )
    conn.commit()
