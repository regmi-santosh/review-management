import json
import urllib.request

from lib import config


def notify_escalation(review: dict, reason: str) -> None:
    message = (
        f":rotating_light: Escalated review for {config.BUSINESS_NAME}\n"
        f"Rating: {review['rating']}/5  Author: {review['author_name']}\n"
        f"Reason: {reason}\n"
        f"Review: {review['text']}\n"
        f"Draft reply (needs approval): {review.get('draft_reply') or '(none yet)'}"
    )

    if config.SLACK_WEBHOOK_URL:
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(config.SLACK_WEBHOOK_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=10)
            return
        except Exception as exc:
            print(f"[notify] failed to post to Slack ({exc}); falling back to console:")

    print(f"[notify] {message}")
