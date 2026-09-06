#!/usr/bin/env python3
"""Pull reviews from Google (mock or live, per GOOGLE_CLIENT_MODE in .env)
and insert any not already in the local DB. Reviews that already had an
owner reply on Google are recorded as already posted and excluded from the
"new" list below. Prints the reviews that actually need the review-handler
agent's attention as a JSON array.

Usage: python3 tools/fetch_reviews.py [--business <slug>]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.cli import add_business_arg, apply_business_arg
from lib.google_client import get_google_client


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    client = get_google_client()
    fetched = client.fetch_reviews()

    actionable = []
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
        )
        if new_id is None:
            continue
        row = store.get_review(conn, new_id)
        if row["status"] == "new":
            actionable.append(row)
        else:
            already_replied += 1

    print(
        json.dumps(
            {"fetched": len(fetched), "already_replied": already_replied, "new": actionable},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
