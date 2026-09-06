import sqlite3
from typing import Optional

from lib import store
from lib.google_client import get_google_client
from lib.logging_setup import get_logger


def post_review_reply(conn: sqlite3.Connection, review_id: int, text: Optional[str] = None) -> dict:
    """Post `text` (or the review's draft_reply) to Google and mark it posted.

    Raises on failure; caller decides how to recover the review's status.
    """
    logger = get_logger("actions")
    review = store.get_review(conn, review_id)
    if not review:
        raise ValueError(f"no review with id {review_id}")

    reply_text = text or review.get("draft_reply")
    if not reply_text:
        raise ValueError(f"review {review_id} has no draft_reply to post")

    client = get_google_client()
    try:
        client.post_reply(review["external_id"], review.get("location_id"), reply_text)
    except Exception:
        logger.exception(f"failed to post reply for review {review_id} (external_id={review['external_id']})")
        raise

    store.update_review(conn, review_id, posted_reply=reply_text, status="posted", reply_source="agent")
    logger.info(f"posted reply for review {review_id} (external_id={review['external_id']})")
    return store.get_review(conn, review_id)


def reject_review(conn: sqlite3.Connection, review_id: int) -> dict:
    review = store.get_review(conn, review_id)
    if not review:
        raise ValueError(f"no review with id {review_id}")
    store.update_review(conn, review_id, status="rejected")
    get_logger("actions").info(f"rejected review {review_id} (external_id={review['external_id']})")
    return store.get_review(conn, review_id)
