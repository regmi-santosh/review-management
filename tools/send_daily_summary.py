#!/usr/bin/env python3
"""Send today's summary (tallies from the last logged run + current
pending/escalated queue, plus optional highlights) through every configured
notification channel (Telegram/Slack - see docs/API_SETUP.md).

Called by the review-handler agent at the end of Step 6, right after
log_run.py, with a short highlights sentence composed from its own run
context (a background script has no LLM judgment to do that itself - see
lib/telegram_bot.py's on-demand reply for the highlights-less equivalent).

Usage:
  python3 tools/send_daily_summary.py --highlights "one escalation: skin reaction complaint"
  python3 tools/send_daily_summary.py    # no highlights, tallies only
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store
from lib.cli import add_business_arg, apply_business_arg
from lib.notifier import notify_daily_summary
from lib.summary import build_summary_text


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--highlights", default=None)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    text = build_summary_text(conn, config.active(), highlights=args.highlights)
    notify_daily_summary(text)
    print("Daily summary sent.")


if __name__ == "__main__":
    main()
