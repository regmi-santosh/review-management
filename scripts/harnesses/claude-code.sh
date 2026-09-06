#!/bin/bash
# Claude Code harness adapter - see docs/ARCHITECTURE.md "Harness layer".
#
# This is the only file in the repo that knows about the `claude` CLI
# specifically. scripts/run_review_handler.sh sources whichever
# scripts/harnesses/<AGENT_HARNESS>.sh is configured (this one by default)
# and calls run_agent() - it never invokes a CLI binary directly itself.
#
# To add a second harness later (Copilot, a local-LLM agent framework,
# ...): write a sibling scripts/harnesses/<name>.sh defining the same
# run_agent() function however that harness needs to be invoked, then set
# AGENT_HARNESS=<name> in .env. Nothing in review-handler.md, tools/, or
# lib/ needs to change - the instructions those files carry are already
# harness-neutral prose.
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"

run_agent() {
  local prompt="$1"
  "$CLAUDE_BIN" -p "$prompt" --permission-mode auto
}
