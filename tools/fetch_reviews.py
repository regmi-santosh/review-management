#!/usr/bin/env python3
"""Pull reviews from Google (mock or live, per GOOGLE_CLIENT_MODE in .env)
and insert any not already in the local DB as status=new. Prints the newly
inserted reviews as a JSON array so the review-handler agent can process
them.

Usage: python3 tools/fetch_reviews.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.google_client import get_google_client


def main() -> None:
    conn = store.connect()
    client = get_google_client()
    fetched = client.fetch_reviews()

    inserted = []
    for raw in fetched:
        new_id = store.insert_review(
            conn, raw.external_id, raw.author_name, raw.rating, raw.text, raw.create_time
        )
        if new_id is not None:
            inserted.append(store.get_review(conn, new_id))

    print(json.dumps({"fetched": len(fetched), "new": inserted}, indent=2))


if __name__ == "__main__":
    main()
