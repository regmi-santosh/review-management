#!/usr/bin/env python3
"""Fire an escalation notification for a review (console log, or
Telegram/Slack if configured - see docs/API_SETUP.md). Called by the
review-handler agent immediately when it routes a review to 'escalated'.

If sent via Telegram, the message id is saved on the review
(telegram_message_id) so a later reply to that message (approve/reject/edit
- see lib/telegram_bot.py) can be matched back to it.

Usage: python3 tools/notify.py --review-id 3 --reason "Health/safety complaint"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.cli import add_business_arg, apply_business_arg
from lib.notifier import notify_escalation


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    review = store.get_review(conn, args.review_id)
    if not review:
        print(f"error: no review with id {args.review_id}", file=sys.stderr)
        sys.exit(1)

    telegram_message_id = notify_escalation(review, args.reason)
    if telegram_message_id:
        store.update_review(conn, args.review_id, telegram_message_id=telegram_message_id)


if __name__ == "__main__":
    main()
