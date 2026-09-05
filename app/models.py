from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class ReviewStatus(str, Enum):
    new = "new"
    pending_review = "pending_review"
    escalated = "escalated"
    posted = "posted"
    rejected = "rejected"


class Sentiment(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class Urgency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class Category(str, Enum):
    compliment = "compliment"
    complaint = "complaint"
    question = "question"
    spam = "spam"
    other = "other"


class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str = Field(index=True, unique=True)
    author_name: str
    rating: int
    text: str
    create_time: datetime

    status: ReviewStatus = Field(default=ReviewStatus.new)
    category: Optional[Category] = None
    sentiment: Optional[Sentiment] = None
    urgency: Optional[Urgency] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None

    draft_reply: Optional[str] = None
    posted_reply: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
