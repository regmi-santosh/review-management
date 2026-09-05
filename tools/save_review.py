#!/usr/bin/env python3
"""Persist the review-handler agent's classification, draft reply, and
routing decision for one review.

Usage:
  python tools/save_review.py --review-id 3 \
    --category complaint --sentiment negative --urgency high \
    --confidence 0.4 --reasoning "..." \
    --draft-reply "..." --status pending_review
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.db import engine, init_db
from app.models import Category, Review, ReviewStatus, Sentiment, Urgency


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--category", choices=[c.value for c in Category], required=True)
    parser.add_argument("--sentiment", choices=[s.value for s in Sentiment], required=True)
    parser.add_argument("--urgency", choices=[u.value for u in Urgency], required=True)
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--reasoning", required=True)
    parser.add_argument("--draft-reply", required=True)
    parser.add_argument(
        "--status",
        choices=[s.value for s in ReviewStatus],
        required=True,
        help="Routing decision: posted (will be auto-posted next by post_reply.py), "
        "escalated, or pending_review.",
    )
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        review = session.get(Review, args.review_id)
        if not review:
            print(f"error: no review with id {args.review_id}", file=sys.stderr)
            sys.exit(1)

        review.category = Category(args.category)
        review.sentiment = Sentiment(args.sentiment)
        review.urgency = Urgency(args.urgency)
        review.confidence = args.confidence
        review.reasoning = args.reasoning
        review.draft_reply = args.draft_reply
        review.status = ReviewStatus(args.status)
        review.updated_at = datetime.utcnow()

        session.add(review)
        session.commit()

    print(f"saved review {args.review_id} as status={args.status}")


if __name__ == "__main__":
    main()
