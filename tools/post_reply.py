#!/usr/bin/env python3
"""Post a review's draft_reply (or an override) through the Google client and
mark it posted. Used both for auto-post (agent calls this right after
save_review sets status=posted) and for human-approved queued reviews.

Usage:
  python tools/post_reply.py --review-id 3
  python tools/post_reply.py --review-id 3 --text "edited reply text"

Exits non-zero if posting fails, leaving the review's status untouched so the
caller can decide how to recover (e.g. fall back to pending_review).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.db import engine, init_db
from app.models import Review
from app.services import post_review_reply


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument(
        "--text", default=None, help="Override text to post instead of draft_reply."
    )
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        review = session.get(Review, args.review_id)
        if not review:
            print(f"error: no review with id {args.review_id}", file=sys.stderr)
            sys.exit(1)

        try:
            post_review_reply(session, review, text=args.text)
        except Exception as exc:
            print(f"error: failed to post reply: {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"posted reply for review {args.review_id}")


if __name__ == "__main__":
    main()
