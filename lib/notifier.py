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
import mimetypes
import uuid
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from lib import config
from lib.logging_setup import get_logger


def _urlopen(req: urllib.request.Request, timeout: int) -> bytes:
    """urlopen, but surfaces the response body on an HTTP error instead of
    swallowing it - APIs like Telegram's and Facebook's Graph API put the
    actual reason (invalid token, missing permission, etc.) in a JSON body
    even on 4xx, which a bare HTTPError discards."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {req.full_url}: {body}") from None


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    raw = _urlopen(req, timeout=10)
    return json.loads(raw) if raw else {}


def post_multipart(url: str, fields: dict, file_field: str, file_path: str) -> dict:
    """POST `fields` plus one file (`file_field` -> `file_path`) as
    multipart/form-data. stdlib has no multipart encoder built in, so this
    builds the body by hand — only needed for Telegram's sendPhoto today."""
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    filename = Path(file_path).name
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    raw = _urlopen(req, timeout=30)
    return json.loads(raw) if raw else {}


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> Optional[str]:
        """Send `message` through this channel. May return a channel-specific
        identifier for the sent message (e.g. Telegram's message_id, used to
        correlate a later reply back to what it was sent about) - None if the
        channel has no such concept."""
        ...

    def send_photo(self, path: str, caption: str) -> Optional[str]:
        """Send the image at `path` with `caption`. Default falls back to a
        plain text message noting an image was drafted - most channels
        (e.g. Slack incoming webhooks) can't upload files at all. Override
        this only where the channel genuinely supports it (see
        TelegramNotifier)."""
        return self.send(f"{caption}\n[image drafted: {path}]")


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

    def send_photo(self, path: str, caption: str) -> Optional[str]:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        result = post_multipart(
            url, {"chat_id": self.chat_id, "caption": caption}, "photo", path
        )
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


def _broadcast(
    business: config.Business, message: str, logger, context: str, image_path: Optional[str] = None
) -> tuple:
    """Send `message` (as a photo caption if `image_path` is set, else a
    plain text message) through every channel this business has configured.
    Returns (sent_to_at_least_one, telegram_message_id_if_any) - the latter
    lets a caller correlate a later Telegram reply back to this message."""
    sent = False
    telegram_message_id = None
    for channel in get_configured_notifiers(business):
        channel_name = type(channel).__name__.replace("Notifier", "")
        try:
            result = channel.send_photo(image_path, message) if image_path else channel.send(message)
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


def notify_social_draft(text: str, image_path: Optional[str] = None) -> None:
    """Broadcast one platform's drafted caption, as a photo caption when
    `image_path` is given (see lib/social_image.py) or plain text when not
    (e.g. image generation failed or Pillow isn't installed)."""
    business = config.active()
    logger = get_logger("notifier")
    logger.info("social draft triggered")
    _broadcast(business, text, logger, context="social draft", image_path=image_path)
