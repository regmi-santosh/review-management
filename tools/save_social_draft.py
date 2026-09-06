#!/usr/bin/env python3
"""Save a drafted social-media caption for a review and push it through
every configured notification channel (Telegram/Slack - see
docs/API_SETUP.md). Called by the review-handler agent for every 5-star
review it processes (Step 5) - draft-only, nothing gets auto-posted to any
social platform, this repo has no such integration.

Usage:
  python3 tools/save_social_draft.py --review-id 3 --caption "One of our regulars stopped by for a fresh brow shape and left glowing - exactly the kind of visit we love. 🌸"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.cli import add_business_arg, apply_business_arg
from lib.notifier import notify_social_draft


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--caption", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    review = store.get_review(conn, args.review_id)
    if not review:
        print(f"error: no review with id {args.review_id}", file=sys.stderr)
        sys.exit(1)

    store.update_review(conn, args.review_id, draft_social_post=args.caption)
    notify_social_draft(
        f"\U0001F4F1 Social post idea (review {args.review_id}, {review['rating']}★):\n{args.caption}"
    )
    print("Social draft saved.")


if __name__ == "__main__":
    main()
