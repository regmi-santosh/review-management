#!/usr/bin/env python3
"""Human rejection: mark a pending/escalated review as rejected without
posting any reply.

Usage: python tools/reject.py --review-id 3
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.db import engine, init_db
from app.models import Review
from app.services import reject_review


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-id", type=int, required=True)
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        review = session.get(Review, args.review_id)
        if not review:
            print(f"error: no review with id {args.review_id}", file=sys.stderr)
            sys.exit(1)
        reject_review(session, review)

    print(f"rejected review {args.review_id}")


if __name__ == "__main__":
    main()
