"""Escalation notifications via a plug-and-play connector interface.

Each channel (Telegram, Slack, ...) is a Notifier implementing send() -
the same interface-plus-swappable-implementations shape as
lib/google_client.py's GoogleBusinessProfileClient. To add a channel:
write a class implementing Notifier, and add it to _CONNECTORS below. To
remove one: delete its entry. Nothing else in this file, or in any tool
that triggers a notification, needs to know a given channel exists.

get_configured_notifiers() returns an instance for every channel a
business actually has credentials for - possibly several at once, possibly
none. notify_escalation() sends to all of them, falling back to console
only if none are configured or every send fails.
"""
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import List

from lib import config
from lib.logging_setup import get_logger


def _post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        ...


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> None:
        _post_json(self.webhook_url, {"text": message})


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        _post_json(url, {"chat_id": self.chat_id, "text": message})


# Each entry: (condition on the business's config, factory to build the Notifier).
# Add a new channel here - nothing else in this file needs to change.
_CONNECTORS = [
    (
        lambda b: bool(b.telegram_bot_token and b.telegram_chat_id),
        lambda b: TelegramNotifier(b.telegram_bot_token, b.telegram_chat_id),
    ),
    (
        lambda b: bool(b.slack_webhook_url),
        lambda b: SlackNotifier(b.slack_webhook_url),
    ),
]


def get_configured_notifiers(business: config.Business) -> List[Notifier]:
    return [make(business) for configured, make in _CONNECTORS if configured(business)]


def notify_escalation(review: dict, reason: str) -> None:
    business = config.active()
    logger = get_logger("notifier")
    message = (
        f"\U0001F6A8 Escalated review for {business.name}\n"
        f"Rating: {review['rating']}/5  Author: {review['author_name']}\n"
        f"Reason: {reason}\n"
        f"Review: {review['text']}\n"
        f"Draft reply (needs approval): {review.get('draft_reply') or '(none yet)'}"
    )
    logger.info(f"escalation triggered: rating={review['rating']} author={review['author_name']!r} reason={reason!r}")

    sent = False
    for channel in get_configured_notifiers(business):
        channel_name = type(channel).__name__.replace("Notifier", "")
        try:
            channel.send(message)
            logger.info(f"escalation sent via {channel_name}")
            sent = True
        except Exception as exc:
            logger.warning(f"failed to post escalation to {channel_name}: {exc}")
            print(f"[notify] failed to post to {channel_name} ({exc}); falling back to console:")

    if sent:
        return

    logger.warning("escalation NOT sent to any channel - printed to console only")
    print(f"[notify] {message}")
