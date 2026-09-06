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
from lib.cli import add_business_arg, apply_business_arg
from lib.google_client import get_google_client
from lib.logging_setup import get_logger


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
    fetched = client.fetch_reviews()

    already_replied = 0
    for raw in fetched:
        new_id = store.insert_review(
            conn,
            raw.external_id,
            raw.author_name,
            raw.rating,
            raw.text,
            raw.create_time,
            existing_reply=raw.existing_reply,
            location_id=raw.location_id,
        )
        if new_id is None:
            continue
        row = store.get_review(conn, new_id)
        if row["status"] != "new":
            already_replied += 1

    actionable = store.list_reviews(conn, status="new")
    get_logger("fetch_reviews").info(
        f"fetched={len(fetched)} already_replied={already_replied} actionable={len(actionable)}"
    )

    if len(actionable) > args.max_batch and not args.allow_large_batch:
        get_logger("fetch_reviews").warning(
            f"batch_too_large: {len(actionable)} actionable reviews exceeds max_batch={args.max_batch}"
        )
        print(
            json.dumps(
                {
                    "fetched": len(fetched),
                    "already_replied": already_replied,
                    "batch_too_large": True,
                    "actionable_count": len(actionable),
                    "max_batch": args.max_batch,
                    "message": (
                        f"{len(actionable)} reviews need action, exceeding --max-batch="
                        f"{args.max_batch}. This is unusual - stop and confirm with a human this "
                        "is expected (e.g. a large backlog on a first-ever fetch) before "
                        "processing. Nothing is lost: all reviews are safely stored as status=new. "
                        "Re-run with --allow-large-batch once confirmed."
                    ),
                    "new": [],
                },
                indent=2,
            )
        )
        sys.exit(2)

    print(
        json.dumps(
            {"fetched": len(fetched), "already_replied": already_replied, "new": actionable},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
