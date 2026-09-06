# Operations & hardening

Reference for running this system with less hand-holding — health checks, safety guardrails, and what happens when things go wrong.

## Health checks

```bash
python3 tools/check_health.py [--business <slug>]
```

Checks, in order:
1. **Secrets file permissions** — `businesses/<slug>/.env` should be owner-only (600). If it's found looser, this fixes it automatically and reports that it did.
2. **Google OAuth** — actually attempts a token refresh (only when `google_client_mode` is `live`). This is what catches the Testing-mode 7-day refresh token expiry (see `docs/API_SETUP.md`) *before* it silently breaks `fetch_reviews.py`/`post_reply.py` — the error message tells you exactly which command to re-run.
3. **Escalation channel** — warns if no Telegram or Slack connector is configured (see "Notification connectors" below), since escalations printing to a console nobody's watching defeats the point once this runs unattended.
4. **Review queue** — how many reviews are sitting in `pending_review`/`escalated`, and how long the oldest one has been waiting. Flags as a warning if anything's escalated or something's been queued over a day.
5. **Last run** — when the review-handler agent last ran and what it did (see "Run history" below).

Exit code: `0` all OK, `1` warnings present, `2` something failed — usable as a monitoring check if this ever runs on a schedule.

Run this periodically (daily is reasonable) even before any scheduler exists — catching an expired OAuth token or a stale escalation via a health check beats discovering it the next time you happen to run the agent.

## Run history

Every review-handler run logs a summary row (fetched/already-replied/processed/posted/escalated/queued counts, plus notes) via `tools/log_run.py`, stored in the business's own `reviews.db` (a `runs` table, separate from the `reviews` table). This is what `check_health.py`'s "Last run" check reads. It exists so run history survives beyond whatever chat session it happened in — useful for noticing "it's been 3 days since this last ran" or "posting volume dropped off" without digging through transcripts.

## Notification connectors

`lib/notifier.py` sends escalation alerts through a small plug-and-play connector interface — the same interface-plus-swappable-implementations shape as `lib/google_client.py`'s Mock/Live clients. Each channel is a class implementing `Notifier.send(message)`:

- `TelegramNotifier` — set up via `python3 tools/telegram_setup.py --business <slug> --bot-token <token>` (see `docs/API_SETUP.md` for the non-technical setup steps). Recommended default: no business/developer account needed, just the Telegram app.
- `SlackNotifier` — set up via a `SLACK_WEBHOOK_URL` (see `docs/API_SETUP.md`).

`get_configured_notifiers()` returns an instance for every channel a business actually has credentials for; `notify_escalation()` sends to all of them (not just the first), and only falls back to printing to console if none are configured or every send fails. **Adding a new channel** (email, Discord, SMS, ...) means writing one class and adding it to `_CONNECTORS` in `lib/notifier.py` — nothing else in the codebase (tools, the agent, tests for other channels) needs to change. **Removing a channel** is deleting its `_CONNECTORS` entry.

## Batch-size guardrail

`tools/fetch_reviews.py` refuses (exit code 2) to hand back more than **50** actionable reviews at once unless you pass `--allow-large-batch`. This exists as a safety net against an agent unattended-processing (and potentially auto-posting replies to) an unexpectedly huge batch — e.g. a bug, an API anomaly, or a genuine large backlog that a human should sanity-check before an agent works through it. Nothing is lost while blocked: reviews stay stored as `status=new` and reappear on every subsequent fetch until processed. The review-handler agent is instructed to stop and report this to a human rather than self-authorizing `--allow-large-batch`.

Adjust the threshold with `--max-batch <N>` if 50 is the wrong number for a given business's normal volume.

## Google API reliability

`lib/google_client.py` retries transient failures (HTTP 429/500/502/503/504, and network-level errors like timeouts) up to 3 times with exponential backoff (1s, 2s, 4s) before giving up — both for the reviews API calls and the OAuth token refresh. Non-transient errors (401/403/404/etc.) fail immediately since retrying won't fix them; the goal is to ride out rate limiting and momentary Google-side or network hiccups without a full run failing, which matters more once this runs unattended/scheduled than it does under a human's eye.

## Automated tests

```bash
python3 -m unittest discover -s tests -t .
```

stdlib `unittest` only — no new dependency, consistent with the rest of this project. Covers `lib/store.py` (including the schema migration/backfill logic), `lib/actions.py`, `lib/config.py`'s per-business resolution and secrets handling, `lib/cli.py`'s `--business` flag, and `lib/google_client.py`'s mock client and retry behavior. Tests are fully isolated from real `businesses/` data (see `tests/helpers.py` — everything runs against a temp directory).

Run this after any change to `lib/` before trusting it against real data. Two real bugs (missing pagination, reply-overwrite risk — see `docs/API_SETUP.md`) were only found by manually testing against real data before this suite existed; it exists so the next regression gets caught here instead.

## Scheduling (unattended runs)

Runs locally via `launchd` on this Mac — **not** a cloud routine. A cloud routine clones a fresh checkout from GitHub on every run, which can't see `businesses/<slug>/.env` (Google OAuth credentials, Slack webhook URL) or `businesses/<slug>/reviews.db` (which reviews are already handled) — both are deliberately gitignored, so a cloud routine would either have no credentials at all, or require embedding real secrets into the routine definition stored in Anthropic's cloud. `launchd` runs on this exact machine, this exact working copy, so it just sees the same filesystem an interactive session would.

- `scripts/run_review_handler.sh` — invokes `claude -p "Run the review-handler agent for brows-and-threading-city..." --permission-mode auto` and appends output to `businesses/brows-and-threading-city/logs/launchd.log`. `--permission-mode auto` is the same safety posture used throughout this project's development: normal tool calls proceed without a prompt, but the classifier still blocks bulk/high-risk actions rather than assuming nobody's watching means anything goes.
- `scripts/com.review-management.brows-and-threading-city.plist` — the `launchd` job definition. Runs once daily at 7:00 AM local time by default; edit the `Hour`/`Minute` values and re-run the bootstrap command below to change it.

**Install** (copies the plist into place and starts the schedule):

```bash
cp "scripts/com.review-management.brows-and-threading-city.plist" ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.review-management.brows-and-threading-city.plist
```

**Check it's loaded**: `launchctl print gui/$(id -u)/com.review-management.brows-and-threading-city`

**Run it immediately** (without waiting for the schedule, e.g. to test): `launchctl kickstart gui/$(id -u)/com.review-management.brows-and-threading-city`

**Uninstall**:

```bash
launchctl bootout gui/$(id -u)/com.review-management.brows-and-threading-city
rm ~/Library/LaunchAgents/com.review-management.brows-and-threading-city.plist
```

**Known limitation**: only runs while this Mac is on, awake, and logged in at the scheduled time — `launchd` doesn't run LaunchAgents when the user is logged out, and a sleeping Mac won't wake for it. Fine for a single-owner local setup; revisit if this needs to run independent of any one machine.

`businesses/<slug>/logs/launchd.log` holds each scheduled run's full agent output (appended); `launchd_stdout.log`/`launchd_stderr.log` alongside it should normally stay empty — anything there means the script itself failed to start, before it could even write to its own log. See "Structured logging" below for the separate, rotated application log.

## Structured logging

Console output (`print()`) is lost the moment a session ends or nobody's watching stdout — the interactive experience still prints as before, but the things that matter durably now also go through `lib/logging_setup.py` into a rotating file per business: `businesses/<slug>/logs/app.log` (5MB per file, 5 backups kept, stdlib `logging.handlers.RotatingFileHandler` — no new dependency).

What's logged there today:
- `lib/actions.py` — every successful post (`posted reply for review N`) and every rejection, plus the full exception (not just a message) if posting fails.
- `lib/notifier.py` — every escalation trigger, whether it reached Slack, and — at `WARNING` level, since this is the case that matters most — when an escalation reached **no channel at all** and only got printed to a console nobody may be watching.
- `lib/google_client.py` — how many reviews a live fetch pulled, every live post, and mock-mode "would post" events.
- `tools/fetch_reviews.py` — a one-line summary of every fetch (fetched/already-replied/actionable counts), and a `WARNING` when the batch-size guardrail trips.

This is additive, not a replacement for the CLI tools' existing stdout contracts (`fetch_reviews.py`'s JSON output, confirmation messages, etc.) — the review-handler agent still parses those exactly as before.

## Secrets hygiene

`businesses/<slug>/.env` is written with owner-only (600) permissions every time `Business.save_secret()` writes to it (i.e., whenever `tools/google_oauth_setup.py` runs), and `check_health.py` audits/fixes permissions on every run regardless of how the file got there. These files are also gitignored (see `.gitignore`) — they should never end up in a commit.
