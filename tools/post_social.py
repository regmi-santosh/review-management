#!/usr/bin/env python3
"""Human-triggered: actually publish one review's (or one milestone's)
already-drafted social post to one platform (see docs/ARCHITECTURE.md
"Social platform layer" - Phase 2). Nothing auto-posts on its own - a
person runs this explicitly after reviewing the draft (see the
image/caption save_social_draft.py / save_milestone_draft.py already sent
to Telegram/Slack), mirroring tools/approve.py's human-in-the-loop gate on
posting Google replies.

Usage:
  python3 tools/post_social.py --review-id 358 --platform facebook
  python3 tools/post_social.py --milestone-id 1 --platform facebook
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import social_platforms, store
from lib.actions import publish_social_post
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--review-id", type=int)
    target.add_argument("--milestone-id", type=int)
    parser.add_argument("--platform", required=True, choices=social_platforms.available_platforms())
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    try:
        external_id = publish_social_post(
            conn, args.platform, review_id=args.review_id, milestone_id=args.milestone_id
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Posted to {args.platform}: {external_id}")


if __name__ == "__main__":
    main()
