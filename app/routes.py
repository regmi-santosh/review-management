from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Review, ReviewStatus
from app.schemas import DraftUpdate, ReviewRead
from app.services import post_review_reply, reject_review

router = APIRouter()


@router.get("/reviews", response_model=List[ReviewRead])
def list_reviews(status: Optional[ReviewStatus] = None, session: Session = Depends(get_session)):
    query = select(Review).order_by(Review.create_time.desc())
    if status:
        query = query.where(Review.status == status)
    return session.exec(query).all()


@router.get("/reviews/{review_id}", response_model=ReviewRead)
def get_review(review_id: int, session: Session = Depends(get_session)):
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    return review


@router.patch("/reviews/{review_id}/draft", response_model=ReviewRead)
def update_draft(review_id: int, body: DraftUpdate, session: Session = Depends(get_session)):
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    review.draft_reply = body.draft_reply
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


@router.post("/reviews/{review_id}/approve", response_model=ReviewRead)
def approve_review(review_id: int, session: Session = Depends(get_session)):
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        post_review_reply(session, review)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to post reply: {exc}")
    session.refresh(review)
    return review


@router.post("/reviews/{review_id}/reject", response_model=ReviewRead)
def reject_review_route(review_id: int, session: Session = Depends(get_session)):
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    reject_review(session, review)
    session.refresh(review)
    return review
