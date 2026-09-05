from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import Category, ReviewStatus, Sentiment, Urgency


class ReviewRead(BaseModel):
    id: int
    external_id: str
    author_name: str
    rating: int
    text: str
    create_time: datetime

    status: ReviewStatus
    category: Optional[Category]
    sentiment: Optional[Sentiment]
    urgency: Optional[Urgency]
    confidence: Optional[float]
    reasoning: Optional[str]

    draft_reply: Optional[str]
    posted_reply: Optional[str]

    class Config:
        from_attributes = True


class DraftUpdate(BaseModel):
    draft_reply: str


class SyncResult(BaseModel):
    fetched: int
    new: int
    auto_posted: int
    escalated: int
    pending_review: int


class ClassificationResult(BaseModel):
    category: Category
    sentiment: Sentiment
    urgency: Urgency
    confidence: float
    reasoning: str
    draft_reply: str
