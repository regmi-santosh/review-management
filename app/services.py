from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.google_client import get_google_client
from app.models import Review, ReviewStatus


def post_review_reply(session: Session, review: Review, text: Optional[str] = None) -> None:
    """Post `text` (or review.draft_reply) to Google and mark the review posted.

    Raises on failure; caller decides how to recover the review's status.
    """
    reply_text = text or review.draft_reply
    if not reply_text:
        raise ValueError(f"review {review.id} has no draft_reply to post")

    client = get_google_client()
    client.post_reply(review.external_id, reply_text)

    review.posted_reply = reply_text
    review.status = ReviewStatus.posted
    review.updated_at = datetime.utcnow()
    session.add(review)
    session.commit()


def reject_review(session: Session, review: Review) -> None:
    review.status = ReviewStatus.rejected
    review.updated_at = datetime.utcnow()
    session.add(review)
    session.commit()
