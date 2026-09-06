#!/bin/bash
# Invoked by launchd (see
# scripts/com.review-management.brows-and-threading-city.telegram-listener.plist)
# to run tools/telegram_listen.py as a persistent daemon (KeepAlive, not a
# once-a-day StartCalendarInterval like scripts/run_review_handler.sh).
#
# Pure deterministic Python, not `claude -p` - approve/reject/edit and the
# on-demand summary reply need no LLM judgment, just lib/telegram_bot.py's
# dispatch logic. Routine output goes through the rotated
# businesses/<slug>/logs/app.log (lib/logging_setup.py) rather than this
# script's own stdout/stderr, which launchd never rotates - see
# docs/OPERATIONS.md "Interactive Telegram" for why.
set -uo pipefail

REPO_DIR="/Users/sansha/Documents/Projects/brows & threading/review-management"
PYTHON_BIN="/usr/bin/python3"

cd "$REPO_DIR" || exit 1
exec "$PYTHON_BIN" tools/telegram_listen.py --business brows-and-threading-city
