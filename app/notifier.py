import httpx

from app.config import settings
from app.models import Review


def notify_escalation(review: Review, reason: str) -> None:
    message = (
        f":rotating_light: Escalated review for {settings.business_name}\n"
        f"Rating: {review.rating}/5  Author: {review.author_name}\n"
        f"Reason: {reason}\n"
        f"Review: {review.text}\n"
        f"Draft reply (needs approval): {review.draft_reply or '(none yet)'}"
    )

    if settings.slack_webhook_url:
        httpx.post(settings.slack_webhook_url, json={"text": message}, timeout=10)
    else:
        print(f"[notify] {message}")
