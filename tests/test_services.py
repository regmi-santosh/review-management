from datetime import datetime

import pytest
from sqlmodel import Session

from app import services
from app.db import engine, init_db
from app.models import Review, ReviewStatus


@pytest.fixture(autouse=True)
def _init_db():
    init_db()


def test_post_review_reply_posts_and_marks_status(monkeypatch):
    posted = {}

    class FakeClient:
        def post_reply(self, external_id, text):
            posted["external_id"] = external_id
            posted["text"] = text

    monkeypatch.setattr(services, "get_google_client", lambda: FakeClient())

    with Session(engine) as session:
        review = Review(
            external_id="t1",
            author_name="A",
            rating=5,
            text="great",
            create_time=datetime.utcnow(),
            draft_reply="Thanks so much!",
        )
        session.add(review)
        session.commit()
        session.refresh(review)

        services.post_review_reply(session, review)

        assert review.status == ReviewStatus.posted
        assert review.posted_reply == "Thanks so much!"

    assert posted == {"external_id": "t1", "text": "Thanks so much!"}


def test_post_review_reply_requires_text():
    with Session(engine) as session:
        review = Review(
            external_id="t2", author_name="B", rating=3, text="meh",
            create_time=datetime.utcnow(),
        )
        session.add(review)
        session.commit()
        session.refresh(review)

        with pytest.raises(ValueError):
            services.post_review_reply(session, review)


def test_reject_review():
    with Session(engine) as session:
        review = Review(
            external_id="t3", author_name="C", rating=1, text="bad",
            create_time=datetime.utcnow(),
        )
        session.add(review)
        session.commit()
        session.refresh(review)

        services.reject_review(session, review)

        assert review.status == ReviewStatus.rejected
