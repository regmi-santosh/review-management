#!/usr/bin/env python3
"""Human-triggered: actually publish one review's already-drafted social
post to one platform (see docs/ARCHITECTURE.md "Social platform layer" -
Phase 2). Nothing auto-posts on its own - a person runs this explicitly
after reviewing the draft (see the image/caption save_social_draft.py
already sent to Telegram/Slack), mirroring tools/approve.py's
human-in-the-loop gate on posting Google replies.

Usage:
  python3 tools/post_social.py --review-id 358 --platform facebook
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, social_platforms, store
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--platform", required=True, choices=social_platforms.available_platforms())
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    posts = {p["platform"]: p for p in store.list_social_posts(conn, args.review_id)}
    post = posts.get(args.platform)
    if not post:
        print(
            f"error: no drafted social post for review {args.review_id} on {args.platform} - "
            "run tools/save_social_draft.py first",
            file=sys.stderr,
        )
        sys.exit(1)
    if post["status"] == "posted":
        print(
            f"error: review {args.review_id} was already posted to {args.platform} "
            f"(external id {post['external_post_id']})",
            file=sys.stderr,
        )
        sys.exit(1)

    business = config.active()
    platform = social_platforms.get_platform(args.platform)
    try:
        external_id = platform.post(business, post["image_path"], post["text"])
    except Exception as exc:
        print(f"error: failed to post to {args.platform}: {exc}", file=sys.stderr)
        sys.exit(1)

    store.mark_social_post_posted(conn, args.review_id, args.platform, external_id)
    print(f"Posted to {args.platform}: {external_id}")


if __name__ == "__main__":
    main()
