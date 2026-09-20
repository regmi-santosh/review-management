#!/usr/bin/env python3
"""Save a drafted social-media caption for a review, render a per-platform
quote-card image (lib/social_image.py) for each enabled platform (see
lib/social_platforms.py), and push each one through every configured
notification channel (Telegram/Slack - see docs/API_SETUP.md) as a photo
where an image rendered, plain text otherwise. Called by the
review-handler agent for every 5-star review it processes (Step 5) -
draft-only, nothing gets auto-posted to any social platform, this repo has
no such integration.

Usage:
  python3 tools/save_social_draft.py --review-id 3 --caption "One of our regulars stopped by for a fresh brow shape and left glowing - exactly the kind of visit we love. 🌸"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.actions import draft_social_post_for_review
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--caption", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    try:
        result = draft_social_post_for_review(conn, args.review_id, args.caption)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if result["warning"]:
        print(f"warning: {result['warning']}", file=sys.stderr)
    print("Social draft saved.")


if __name__ == "__main__":
    main()
