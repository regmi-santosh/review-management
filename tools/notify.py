#!/usr/bin/env python3
"""Fire an escalation notification for a review (console log, or Slack if
SLACK_WEBHOOK_URL is set). Called by the review-handler agent immediately
when it routes a review to 'escalated'.

Usage: python tools/notify.py --review-id 3 --reason "Health/safety complaint"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.db import engine, init_db
from app.models import Review
from app.notifier import notify_escalation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        review = session.get(Review, args.review_id)
        if not review:
            print(f"error: no review with id {args.review_id}", file=sys.stderr)
            sys.exit(1)
        notify_escalation(review, args.reason)


if __name__ == "__main__":
    main()
