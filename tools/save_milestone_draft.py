#!/usr/bin/env python3
"""Save a drafted social-media caption for a milestone (see
tools/check_milestones.py), render a per-platform milestone-card image for
each enabled platform, and push each one through every configured
notification channel - the milestone equivalent of save_social_draft.py.
Draft-only: nothing gets auto-posted to any social platform, same posture
as the review path (tools/post_social.py --milestone-id is still the
explicit, human-triggered publish step).

The image's headline/subline text is derived from the milestone's type and
threshold (see _headline_for below) - the caption itself is still
hand-drafted by whoever calls this (normally the review-handler agent,
following the same brand-voice rules as a review caption), since only that
part needs judgment.

Usage:
  python3 tools/save_milestone_draft.py --milestone-id 1 --caption "500 reviews in and counting - thank you, Omaha! 🌸"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.actions import draft_social_post_for_milestone
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--milestone-id", type=int, required=True)
    parser.add_argument("--caption", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    try:
        result = draft_social_post_for_milestone(conn, args.milestone_id, args.caption)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if result["warning"]:
        print(f"warning: {result['warning']}", file=sys.stderr)
    print("Milestone draft saved.")


if __name__ == "__main__":
    main()
