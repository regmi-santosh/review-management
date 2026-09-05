#!/usr/bin/env python3
"""List reviews awaiting a human decision (pending_review or escalated).

Usage: python tools/list_pending.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Review, ReviewStatus


def main() -> None:
    init_db()
    with Session(engine) as session:
        reviews = session.exec(
            select(Review)
            .where(Review.status.in_([ReviewStatus.pending_review, ReviewStatus.escalated]))
            .order_by(Review.status.desc(), Review.create_time.desc())
        ).all()

        if not reviews:
            print("Nothing pending.")
            return

        for r in reviews:
            print(f"--- [{r.status.value}] review {r.id} ({r.rating}★ by {r.author_name}) ---")
            print(f"  text: {r.text}")
            print(f"  category={r.category}, sentiment={r.sentiment}, urgency={r.urgency}, confidence={r.confidence}")
            print(f"  draft_reply: {r.draft_reply}")
            print()


if __name__ == "__main__":
    main()
