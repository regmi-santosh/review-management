# Operations & hardening

Reference for running this system with less hand-holding — health checks, safety guardrails, and what happens when things go wrong.

## Health checks

```bash
python3 tools/check_health.py [--business <slug>]
```

Checks, in order:
1. **Secrets file permissions** — `businesses/<slug>/.env` should be owner-only (600). If it's found looser, this fixes it automatically and reports that it did.
2. **Google OAuth** — actually attempts a token refresh (only when `google_client_mode` is `live`). This is what catches the Testing-mode 7-day refresh token expiry (see `docs/API_SETUP.md`) *before* it silently breaks `fetch_reviews.py`/`post_reply.py` — the error message tells you exactly which command to re-run.
3. **Review queue** — how many reviews are sitting in `pending_review`/`escalated`, and how long the oldest one has been waiting. Flags as a warning if anything's escalated or something's been queued over a day.
4. **Last run** — when the review-handler agent last ran and what it did (see "Run history" below).

Exit code: `0` all OK, `1` warnings present, `2` something failed — usable as a monitoring check if this ever runs on a schedule.

Run this periodically (daily is reasonable) even before any scheduler exists — catching an expired OAuth token or a stale escalation via a health check beats discovering it the next time you happen to run the agent.

## Run history

Every review-handler run logs a summary row (fetched/already-replied/processed/posted/escalated/queued counts, plus notes) via `tools/log_run.py`, stored in the business's own `reviews.db` (a `runs` table, separate from the `reviews` table). This is what `check_health.py`'s "Last run" check reads. It exists so run history survives beyond whatever chat session it happened in — useful for noticing "it's been 3 days since this last ran" or "posting volume dropped off" without digging through transcripts.

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

## Secrets hygiene

`businesses/<slug>/.env` is written with owner-only (600) permissions every time `Business.save_secret()` writes to it (i.e., whenever `tools/google_oauth_setup.py` runs), and `check_health.py` audits/fixes permissions on every run regardless of how the file got there. These files are also gitignored (see `.gitignore`) — they should never end up in a commit.
