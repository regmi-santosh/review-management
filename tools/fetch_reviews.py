#!/usr/bin/env python3
"""Pull reviews from Google (mock or live, per GOOGLE_CLIENT_MODE) and insert
any not already in the local DB as status=new. Prints the newly inserted
reviews as a JSON array so the review-handler agent can process them.

Usage: python tools/fetch_reviews.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import engine, init_db
from app.google_client import get_google_client
from app.models import Review


def main() -> None:
    init_db()
    client = get_google_client()
    fetched = client.fetch_reviews()

    inserted = []
    with Session(engine) as session:
        for raw in fetched:
            existing = session.exec(
                select(Review).where(Review.external_id == raw.external_id)
            ).first()
            if existing:
                continue
            review = Review(
                external_id=raw.external_id,
                author_name=raw.author_name,
                rating=raw.rating,
                text=raw.text,
                create_time=raw.create_time,
            )
            session.add(review)
            session.commit()
            session.refresh(review)
            inserted.append(review)

        result = [
            {
                "id": r.id,
                "external_id": r.external_id,
                "author_name": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "create_time": r.create_time.isoformat(),
            }
            for r in inserted
        ]

    print(json.dumps({"fetched": len(fetched), "new": result}, indent=2))


if __name__ == "__main__":
    main()
