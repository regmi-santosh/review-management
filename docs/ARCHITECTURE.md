# Architecture: layers, and what's actually swappable

This system is built in four layers. Three of them have no dependency on any particular AI vendor or product at all — they're plain, deterministic code. Exactly one integration point is genuinely vendor-specific, and it's isolated to a single small directory on purpose, so changing it never touches the other three.

```
1. Reasoning / instructions   .claude/agents/review-handler.md (body)
2. Harness adapter            scripts/harnesses/*.sh
3. Deterministic tool/action  tools/*.py, lib/*.py
4. Data                       reviews.db, business.json, .env
```

## 1. Reasoning / instructions

The classification rubric, voice-matching guidance, and routing policy in `.claude/agents/review-handler.md` are ordinary prose — read the review, decide category/sentiment/urgency/confidence, draft a reply, apply the routing rules, call the right tool script. Nothing in that body assumes Claude Code specifically; any sufficiently capable agentic system with shell access could execute the same instructions.

The YAML frontmatter at the top of that file (`name:`, `description:`, `tools:`, `model:`) *is* Claude-Code-specific — it's how Claude Code's own subagent discovery mechanism registers the file. That's registration metadata, not logic. A second harness would carry its own registration in whatever format it requires, pointing at conceptually the same instructions - it wouldn't need to touch this file's frontmatter or body.

## 2. Harness adapter — the one swappable seam

This is where "which AI product actually runs the agent" lives, and it's deliberately isolated to `scripts/harnesses/`:

- **`scripts/harnesses/claude-code.sh`** — the only file in the repo that knows about the `claude` CLI. Defines `run_agent "<prompt>"`, today just `claude -p "$prompt" --permission-mode auto`.
- **`scripts/run_review_handler.sh`** — reads `AGENT_HARNESS` from the top-level `.env` (defaults to `claude-code`), sources the matching `scripts/harnesses/<name>.sh`, and calls `run_agent`. It never invokes a CLI binary directly itself.

**To add a second harness later** (Copilot, a local-LLM agent framework, anything else with shell/tool access): write `scripts/harnesses/<name>.sh` implementing the same `run_agent()` function however that harness needs to be invoked, set `AGENT_HARNESS=<name>` in `.env`, done. Nothing in `review-handler.md`, `tools/`, or `lib/` changes. `tools/check_health.py`'s "Agent harness" check confirms the configured name actually has a matching adapter file, so a typo or half-finished switch gets caught before the next unattended run rather than silently doing nothing.

**What this doesn't cover**: the *interactive* path — asking Claude Code directly, "run the review-handler agent" — has no repo-level script to abstract, since Claude Code's own subagent discovery is what's doing the invoking. Using a different product interactively means using that product's own equivalent mechanism, pointed at the same instructions. This seam is specifically about the unattended/scripted path (`scripts/run_review_handler.sh`, driven by `launchd` — see `docs/OPERATIONS.md` "Scheduling").

**`scripts/run_telegram_listener.sh` / `tools/telegram_listen.py` need no harness at all** — approve/reject/edit dispatch and the on-demand summary are pure rule-based Python (`lib/telegram_bot.py`), zero LLM involvement. Proof that layer 3 already stands on its own without layer 1/2 for anything that doesn't actually need judgment.

## 3. Deterministic tool/action layer

`tools/*.py` (thin CLI scripts) and `lib/*.py` (shared logic: `store.py`, `actions.py`, `google_client.py`, `notifier.py`, `telegram_bot.py`, `summary.py`, `config.py`) — all plain Python, stdlib only, no LLM calls anywhere. This is what the reasoning layer (1) calls into via Bash, and it's completely unaffected by which harness (2) is doing the calling. See the main [README](../README.md) for the full file-by-file breakdown.

## 4. Data

Per-business SQLite DB (`businesses/<slug>/reviews.db`), structured facts (`business.json`), and secrets (`businesses/<slug>/.env`) — see `docs/OPERATIONS.md` and the README's "Configuration" section. Unaffected by any of the above.
