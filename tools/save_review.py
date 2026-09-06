#!/usr/bin/env python3
"""Persist the review-handler agent's classification, draft reply, and
routing decision for one review.

Usage:
  python3 tools/save_review.py --review-id 3 \
    --category complaint --sentiment negative --urgency high \
    --confidence 0.4 --reasoning "..." \
    --draft-reply "..." --status pending_review
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--category", choices=sorted(store.VALID_CATEGORIES), required=True)
    parser.add_argument("--sentiment", choices=sorted(store.VALID_SENTIMENTS), required=True)
    parser.add_argument("--urgency", choices=sorted(store.VALID_URGENCIES), required=True)
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--reasoning", required=True)
    parser.add_argument("--draft-reply", required=True)
    parser.add_argument(
        "--status",
        choices=sorted(store.VALID_STATUSES),
        required=True,
        help="Routing decision: posted (will be auto-posted next by post_reply.py), "
        "escalated, or pending_review.",
    )
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    review = store.get_review(conn, args.review_id)
    if not review:
        print(f"error: no review with id {args.review_id}", file=sys.stderr)
        sys.exit(1)

    store.update_review(
        conn,
        args.review_id,
        category=args.category,
        sentiment=args.sentiment,
        urgency=args.urgency,
        confidence=args.confidence,
        reasoning=args.reasoning,
        draft_reply=args.draft_reply,
        status=args.status,
    )

    print(f"saved review {args.review_id} as status={args.status}")


if __name__ == "__main__":
    main()
