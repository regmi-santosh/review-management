import json
import urllib.request

from lib import config
from lib.logging_setup import get_logger


def notify_escalation(review: dict, reason: str) -> None:
    business = config.active()
    logger = get_logger("notifier")
    message = (
        f":rotating_light: Escalated review for {business.name}\n"
        f"Rating: {review['rating']}/5  Author: {review['author_name']}\n"
        f"Reason: {reason}\n"
        f"Review: {review['text']}\n"
        f"Draft reply (needs approval): {review.get('draft_reply') or '(none yet)'}"
    )
    logger.info(f"escalation triggered: rating={review['rating']} author={review['author_name']!r} reason={reason!r}")

    if business.slack_webhook_url:
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(business.slack_webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=10)
            logger.info("escalation sent via Slack")
            return
        except Exception as exc:
            logger.warning(f"failed to post escalation to Slack: {exc}")
            print(f"[notify] failed to post to Slack ({exc}); falling back to console:")

    logger.warning("escalation NOT sent to any channel - printed to console only")
    print(f"[notify] {message}")
