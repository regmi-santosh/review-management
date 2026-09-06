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
    message = (
        f"\U0001F6A8 Escalated review for {business.name}\n"
        f"Rating: {review['rating']}/5  Author: {review['author_name']}\n"
        f"Reason: {reason}\n"
        f"Review: {review['text']}\n"
        f"Draft reply (needs approval): {review.get('draft_reply') or '(none yet)'}"
    )

    sent = False
    for notifier in get_configured_notifiers(business):
        try:
            notifier.send(message)
            sent = True
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"[notify] failed to send via {type(notifier).__name__} ({exc})")

    if not sent:
        print(f"[notify] {message}")
