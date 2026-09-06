"""Escalation notifications via a plug-and-play connector interface.

Each channel (Telegram, Slack, ...) is a Notifier implementing send() -
the same interface-plus-swappable-implementations shape as
lib/google_client.py's GoogleBusinessProfileClient. To add a channel:
write a class implementing Notifier, and add it to _CONNECTORS below. To
remove one: delete its entry. Nothing else in this file, or in any tool
that triggers a notification, needs to know a given channel exists.

get_configured_notifiers() returns an instance for every channel a
business actually has credentials for - possibly several at once, possibly
none. notify_escalation() and notify_daily_summary() both send to all of
them (via the shared _broadcast() helper), falling back to console only if
none are configured or every send fails.

This module is outbound-only and has no database coupling - see
lib/telegram_bot.py for the interactive (inbound) side, which correlates a
Telegram reply back to a review and acts on it.
"""
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import List, Optional

from lib import config
from lib.logging_setup import get_logger


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> Optional[str]:
        """Send `message` through this channel. May return a channel-specific
        identifier for the sent message (e.g. Telegram's message_id, used to
        correlate a later reply back to what it was sent about) - None if the
        channel has no such concept."""
        ...


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> Optional[str]:
        post_json(self.webhook_url, {"text": message})
        return None


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> Optional[str]:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        result = post_json(url, {"chat_id": self.chat_id, "text": message})
        message_id = result.get("result", {}).get("message_id")
        return str(message_id) if message_id is not None else None


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


def _broadcast(business: config.Business, message: str, logger, context: str) -> tuple:
    """Send `message` through every channel this business has configured.
    Returns (sent_to_at_least_one, telegram_message_id_if_any) - the latter
    lets a caller correlate a later Telegram reply back to this message."""
    sent = False
    telegram_message_id = None
    for channel in get_configured_notifiers(business):
        channel_name = type(channel).__name__.replace("Notifier", "")
        try:
            result = channel.send(message)
            logger.info(f"{context} sent via {channel_name}")
            sent = True
            if isinstance(channel, TelegramNotifier) and result:
                telegram_message_id = result
        except Exception as exc:
            logger.warning(f"failed to post {context} to {channel_name}: {exc}")
            print(f"[notify] failed to post to {channel_name} ({exc}); falling back to console:")

    if not sent:
        logger.warning(f"{context} NOT sent to any channel - printed to console only")
        print(f"[notify] {message}")

    return sent, telegram_message_id


def notify_escalation(review: dict, reason: str) -> Optional[str]:
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

    _, telegram_message_id = _broadcast(business, message, logger, context="escalation")
    return telegram_message_id


def notify_daily_summary(text: str) -> None:
    business = config.active()
    logger = get_logger("notifier")
    logger.info("daily summary triggered")
    _broadcast(business, text, logger, context="daily summary")


def notify_social_draft(text: str) -> None:
    business = config.active()
    logger = get_logger("notifier")
    logger.info("social draft triggered")
    _broadcast(business, text, logger, context="social draft")
