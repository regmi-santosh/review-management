#!/usr/bin/env python3
"""List reviews awaiting a human decision (pending_review or escalated).

Usage: python3 tools/list_pending.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store


def main() -> None:
    conn = store.connect()
    reviews = store.list_reviews(conn)
    pending = [r for r in reviews if r["status"] in ("pending_review", "escalated")]
    pending.sort(key=lambda r: r["status"] != "escalated")

    if not pending:
        print("Nothing pending.")
        return

    for r in pending:
        print(f"--- [{r['status']}] review {r['id']} ({r['rating']}★ by {r['author_name']}) ---")
        print(f"  text: {r['text']}")
        print(
            f"  category={r['category']}, sentiment={r['sentiment']}, "
            f"urgency={r['urgency']}, confidence={r['confidence']}"
        )
        print(f"  draft_reply: {r['draft_reply']}")
        print()


if __name__ == "__main__":
    main()
