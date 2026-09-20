#!/usr/bin/env python3
"""Pull reviews from Google (mock or live, per GOOGLE_CLIENT_MODE in .env)
and insert any not already in the local DB. Reviews that already had an
owner reply on Google are recorded as already posted and excluded from the
"new" list below. Prints every review still awaiting action (status=new) -
not just ones inserted by this particular call, so a review left over from
an interrupted or guardrail-blocked previous run always resurfaces.

Safety guardrail: if more than --max-batch reviews need action at once
(default 50), this refuses to hand them all to the agent and exits 2
instead - unusual batch sizes deserve a human's attention before an agent
processes them unattended. Pass --allow-large-batch to proceed anyway.
Nothing is lost either way; reviews stay safely stored as status=new.

Usage:
  python3 tools/fetch_reviews.py [--business <slug>]
  python3 tools/fetch_reviews.py --allow-large-batch
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.actions import fetch_and_store_new_reviews
from lib.cli import add_business_arg, apply_business_arg
from lib.google_client import get_google_client


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument(
        "--max-batch",
        type=int,
        default=50,
        help="Refuse (exit 2) instead of returning more than this many actionable reviews.",
    )
    parser.add_argument(
        "--allow-large-batch",
        action="store_true",
        help="Proceed even if more than --max-batch reviews need action.",
    )
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    client = get_google_client()
    result = fetch_and_store_new_reviews(
        conn, client, max_batch=args.max_batch, allow_large_batch=args.allow_large_batch
    )

    print(json.dumps(result, indent=2))
    if result.get("batch_too_large"):
        sys.exit(2)


if __name__ == "__main__":
    main()
