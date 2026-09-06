#!/usr/bin/env python3
"""Human rejection: mark a pending/escalated review as rejected without
posting any reply.

Usage: python3 tools/reject.py --review-id 3
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.actions import reject_review
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    try:
        reject_review(conn, args.review_id)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"rejected review {args.review_id}")


if __name__ == "__main__":
    main()
