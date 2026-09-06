#!/bin/bash
# Invoked by launchd (see scripts/com.review-management.brows-and-threading-city.plist)
# to run the review-handler agent unattended, once a day.
#
# Which agentic harness actually runs review-handler.md's instructions is
# pluggable (see docs/ARCHITECTURE.md "Harness layer") - this script never
# invokes a CLI binary directly, it sources scripts/harnesses/<AGENT_HARNESS>.sh
# and calls the run_agent() that adapter defines. Defaults to claude-code,
# the only one implemented so far - --permission-mode auto there is the
# same safety posture used throughout this project's development: normal
# tool calls proceed, but bulk/high-risk actions still get the classifier's
# blocking rather than the assumption that nobody's watching means anything
# goes. The agent's own routing policy (escalate/queue anything risky) is
# the other half of that safety net.
set -uo pipefail

REPO_DIR="/Users/sansha/Documents/Projects/brows & threading/review-management"
LOG_DIR="$REPO_DIR/businesses/brows-and-threading-city/logs"
LOG_FILE="$LOG_DIR/launchd.log"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR" || exit 1

# Scoped read of just AGENT_HARNESS, not a full `source .env` - the
# top-level .env also holds Google OAuth secrets that have no reason to
# become shell env vars here.
AGENT_HARNESS="$(grep -E '^AGENT_HARNESS=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
AGENT_HARNESS="${AGENT_HARNESS:-claude-code}"

HARNESS_SCRIPT="scripts/harnesses/${AGENT_HARNESS}.sh"
if [ ! -f "$HARNESS_SCRIPT" ]; then
  echo "error: no harness adapter at $HARNESS_SCRIPT (AGENT_HARNESS=$AGENT_HARNESS)" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$HARNESS_SCRIPT"

PROMPT="Run the review-handler agent for brows-and-threading-city. If tools/fetch_reviews.py reports batch_too_large, stop and report it - do not pass --allow-large-batch yourself."

{
  echo "===== Run started: $(date '+%Y-%m-%d %H:%M:%S') (harness=$AGENT_HARNESS) ====="
  run_agent "$PROMPT"
  status=$?
  echo "===== Run finished: $(date '+%Y-%m-%d %H:%M:%S') (exit $status) ====="
} >> "$LOG_FILE" 2>&1
