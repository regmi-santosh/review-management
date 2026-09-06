#!/usr/bin/env python3
"""Long-polls Telegram for replies and acts on them - the interactive side
of escalations (reply "approve"/"reject"/anything-else to a Telegram
escalation message) plus on-demand summaries (any other message).

This is a persistent daemon, not a one-shot script - intended to run under
launchd with KeepAlive (see scripts/com.review-management.<slug>.telegram-listener.plist
and docs/OPERATIONS.md), not the once-daily StartCalendarInterval pattern
used by scripts/run_review_handler.sh. All the actual decision logic lives
in lib/telegram_bot.py (unit tested); this script is a thin, untested loop
around it, matching this repo's convention that only lib/ gets tests.

Usage: python3 tools/telegram_listen.py [--business <slug>]
"""
import argparse
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store, telegram_bot
from lib.cli import add_business_arg, apply_business_arg
from lib.logging_setup import get_logger

_OFFSET_KEY = "telegram_update_offset"
_POLL_TIMEOUT = 30
_RETRY_SLEEP_SECONDS = 5


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    if not (business.telegram_bot_token and business.telegram_chat_id):
        print(
            f"error: Telegram isn't configured for {business.slug} - "
            "run tools/telegram_setup.py first (see docs/API_SETUP.md).",
            file=sys.stderr,
        )
        sys.exit(1)

    logger = get_logger("telegram_listen")
    conn = store.connect()
    offset = store.get_meta(conn, _OFFSET_KEY)
    offset = int(offset) if offset else None

    logger.info(f"listening for {business.slug} (offset={offset})")

    while True:
        try:
            updates = telegram_bot.get_updates(business.telegram_bot_token, offset, timeout=_POLL_TIMEOUT)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning(f"getUpdates failed, retrying: {exc}")
            time.sleep(_RETRY_SLEEP_SECONDS)
            continue

        for update in updates:
            try:
                reply_text = telegram_bot.handle_update(conn, business, update)
                if reply_text:
                    message = update["message"]
                    telegram_bot.send_message(
                        business.telegram_bot_token,
                        business.telegram_chat_id,
                        reply_text,
                        reply_to_message_id=message["message_id"],
                    )
            except Exception:
                logger.exception(f"failed to handle update {update.get('update_id')}")

            offset = update["update_id"] + 1
            store.set_meta(conn, _OFFSET_KEY, str(offset))


if __name__ == "__main__":
    main()
