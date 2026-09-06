#!/bin/bash
# Invoked by launchd (see scripts/com.review-management.brows-and-threading-city.plist)
# to run the review-handler agent unattended, once a day.
#
# Runs claude non-interactively (-p) with --permission-mode auto: the same
# safety posture used throughout this project's development - normal tool
# calls proceed, but bulk/high-risk actions still get the classifier's
# blocking rather than the assumption that nobody's watching means anything
# goes. The agent's own routing policy (escalate/queue anything risky) is
# the other half of that safety net.
set -uo pipefail

REPO_DIR="/Users/sansha/Documents/Projects/brows & threading/review-management"
LOG_DIR="$REPO_DIR/businesses/brows-and-threading-city/logs"
LOG_FILE="$LOG_DIR/launchd.log"
CLAUDE_BIN="/opt/homebrew/bin/claude"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR" || exit 1

{
  echo "===== Run started: $(date '+%Y-%m-%d %H:%M:%S') ====="
  "$CLAUDE_BIN" -p \
    "Run the review-handler agent for brows-and-threading-city. If tools/fetch_reviews.py reports batch_too_large, stop and report it - do not pass --allow-large-batch yourself." \
    --permission-mode auto
  status=$?
  echo "===== Run finished: $(date '+%Y-%m-%d %H:%M:%S') (exit $status) ====="
} >> "$LOG_FILE" 2>&1
