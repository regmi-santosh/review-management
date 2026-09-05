#!/usr/bin/env python3
"""Human approval: post a pending/escalated review's draft (optionally
edited) to Google and mark it posted.

Usage:
  python tools/approve.py --review-id 3
  python tools/approve.py --review-id 3 --edit "new reply text"
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
    parser.add_argument("--edit", default=None, help="Replace the draft reply with this text before posting.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        review = session.get(Review, args.review_id)
        if not review:
            print(f"error: no review with id {args.review_id}", file=sys.stderr)
            sys.exit(1)

        try:
            post_review_reply(session, review, text=args.edit)
        except Exception as exc:
            print(f"error: failed to post reply: {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"posted reply for review {args.review_id}")


if __name__ == "__main__":
    main()
