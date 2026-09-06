"""Interactive (inbound) side of the Telegram integration - reading and
acting on replies. lib/notifier.py is outbound-only and DB-agnostic by
design; this module is the opposite: it needs lib.store/lib.actions to
correlate a reply to a review and act on it, so it's kept separate.

get_updates()/send_message() are the raw Telegram Bot API calls (long-poll
GET getUpdates, POST sendMessage - the latter via lib.notifier.post_json,
the same helper Slack/Telegram outbound sends already use).

classify_reply() and handle_update() are pure(ish) - no network calls, so
they're the part that's actually unit tested (see tests/test_telegram_bot.py
and the repo-wide convention that only lib/ gets tests; tools/telegram_listen.py
is a thin, untested loop around handle_update()).
"""
import json
import urllib.parse
import urllib.request
from typing import Optional

from lib import actions, store
from lib.logging_setup import get_logger
from lib.notifier import post_json
from lib.summary import build_summary_text

_ACTIONABLE_STATUSES = ("escalated", "pending_review")


def get_updates(bot_token: str, offset: Optional[int], timeout: int = 30) -> list:
    """GET getUpdates, long-polling. `offset` must already be
    last_update_id + 1 (Telegram's required semantics) - pass the stored
    value straight through unmodified."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?{urllib.parse.urlencode(params)}"
    # The local socket timeout must exceed Telegram's own long-poll `timeout`
    # query param above - they're unrelated values that happen to share a
    # name, and urlopen would otherwise time out locally before Telegram's
    # window even closes.
    with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
        result = json.loads(resp.read())
    return result.get("result", []) if result.get("ok") else []


def send_message(bot_token: str, chat_id, text: str, reply_to_message_id: Optional[int] = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    return post_json(url, payload)


def classify_reply(text: str) -> str:
    """Returns "approve" | "reject" | "edit" - anything that isn't clearly
    an approve/reject keyword is treated as the actual reply text to post."""
    normalized = text.strip().lower()
    if normalized in {"approve", "yes", "ok"}:
        return "approve"
    if normalized in {"reject", "no", "skip"}:
        return "reject"
    return "edit"


def handle_update(conn, business, update: dict) -> Optional[str]:
    """Dispatch one Telegram update. Returns the text to send back as a
    reply, or None if nothing should be sent (wrong chat, no text)."""
    logger = get_logger("telegram_bot")
    message = update.get("message")
    if not message:
        return None

    if int(message["chat"]["id"]) != int(business.telegram_chat_id):
        logger.warning(f"ignoring message from unrecognized chat {message['chat']['id']}")
        return None

    text = message.get("text")
    if not text:
        return None

    reply_to = message.get("reply_to_message")
    if not reply_to:
        return build_summary_text(conn, business)

    review = store.get_review_by_telegram_message_id(conn, str(reply_to["message_id"]))
    if not review:
        return (
            "Couldn't match this to an open escalation - it may already be resolved "
            "or too old to act on. Send any other message (not a reply) for today's summary."
        )
    if review["status"] not in _ACTIONABLE_STATUSES:
        return f"Review {review['id']} was already handled (status: {review['status']})."

    action = classify_reply(text)
    try:
        if action == "approve":
            actions.post_review_reply(conn, review["id"])
            return f"Posted the draft reply for review {review['id']}."
        if action == "reject":
            actions.reject_review(conn, review["id"])
            return f"Dismissed review {review['id']} - no reply posted."
        actions.post_review_reply(conn, review["id"], text=text)
        return f"Posted your reply for review {review['id']}."
    except (ValueError, RuntimeError) as exc:
        logger.exception(f"failed to act on review {review['id']} from Telegram reply")
        return f"Couldn't act on review {review['id']}: {exc}"
