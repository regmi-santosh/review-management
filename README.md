# Review Management Agent

An agentic system that reads Google reviews for a business and handles them:

1. **Classify** each review (category, sentiment, urgency, confidence).
2. **Draft** a human-toned reply, in that business's voice.
3. **Route** it:
   - **Highly negative** (`sentiment=negative` and `urgency` is `high`/`critical`) → **escalate immediately** to a human (Slack webhook, or console log by default). Reply is held for approval — never auto-posted.
   - **High confidence** (`confidence >= CONFIDENCE_THRESHOLD`, default `0.85`) and not highly negative → **auto-post** the reply.
   - **Otherwise** → queue the draft for **human approval**.

The system itself is generic — it isn't written for any one business. The classification/drafting/routing logic in [.claude/agents/review-handler.md](.claude/agents/review-handler.md) is business-agnostic; a specific business is just a config directory under `businesses/`, with its own data, DB, and Google credentials — completely isolated from any other business the same install manages. The first one set up is [businesses/brows-and-threading-city](businesses/brows-and-threading-city) ([Google Maps listing](https://www.google.com/maps/place/Brows+%26+Threading+City/@41.2887591,-96.0845815,17z)), used here as a concrete example/demo — see "Adding another business" below to point this at a different one, or to run several at once via `--business`.

## Architecture: harness-native, not a Python service

There is no separate LLM API call anywhere in this repo, and no API key for a model. The reasoning — classification, drafting, and the routing policy — is entirely the job of a Claude Code **subagent**, [.claude/agents/review-handler.md](.claude/agents/review-handler.md), which runs as the model already powering your VS Code / Claude Code session. Python only exists for thin, deterministic **tool scripts** that the agent invokes via Bash:

```
tools/
  fetch_reviews.py           pull new reviews from Google (mock or live) into the local DB
  save_review.py             persist the agent's classification + draft + routing decision
  post_reply.py              post a reply through the Google client, mark it posted
  notify.py                  fire an escalation alert (console / Slack)
  list_pending.py            human helper: show everything awaiting a decision
  approve.py                 human helper: post a queued/escalated draft (optionally edited)
  reject.py                  human helper: dismiss a queued review with no reply
  google_oauth_setup.py      one-time: obtain a Google OAuth refresh token (see docs/API_SETUP.md)
  telegram_setup.py          one-time: connect a Telegram bot for escalation alerts (see docs/API_SETUP.md)
  google_list_locations.py   one-time: discover your Google account/location IDs
  learn_voice.py             onboarding: sample a business's pre-existing owner replies into
                              voice_sample.md, to turn into profile.md's voice section
  log_run.py                 append a run summary (see docs/OPERATIONS.md "Run history")
  check_health.py            OAuth/secrets/queue/last-run health check (see docs/OPERATIONS.md)

lib/                  shared code the tools above import (no ORM, no web framework)
  config.py           resolves the active business into a Business object (lib/config.py's
                       Business class) — see "Adding another business" below. No LLM key
                       anywhere: nothing here calls a model API.
  cli.py               shared --business flag handling for tool scripts
  store.py             plain sqlite3 (stdlib) persistence — no ORM
  google_client.py    GoogleBusinessProfileClient interface + Mock/Live implementations (stdlib
                       urllib for HTTP — no third-party HTTP client)
  notifier.py          escalation notifications (console / Slack, via urllib)
  actions.py           shared post/reject logic used by the CLI tools

businesses/<slug>/     one directory per business — fully isolated data (see "Adding another business")
  business.json        structured facts: name, Maps URL, Google account/location IDs, and
                       optional per-business overrides (confidence_threshold, slack_webhook_url,
                       google_client_mode)
  .env                 (gitignored) this business's own Google OAuth credentials — never shared
                       across businesses, since each listing is normally owned by a different
                       Google account
  profile.md           free-text voice/context the agent reads directly (Step 0 of the agent)
  seed_reviews.json    mock review data used while in mock mode
  reviews.db           (gitignored) this business's own SQLite DB — created automatically,
                       includes a `runs` table logging every review-handler run

tests/                 stdlib unittest suite, fully isolated from real businesses/ data
```

**Dependencies: none.** Everything is Python 3 standard library (`sqlite3`, `urllib`, `argparse`, `json`, `dataclasses`, `http.server`, `webbrowser`). There's no `requirements.txt`, no virtualenv to set up, no `pip install` step — just `python3 tools/<script>.py`.

### Running the agent

To process the current batch of new reviews on demand, just ask Claude Code to run it, e.g.:

> run the review-handler agent

It will read the active business's profile, run `tools/fetch_reviews.py`, classify/draft/route each new review itself, and call the appropriate tool script(s) directly.

For unattended/scheduled runs, see `docs/OPERATIONS.md` "Scheduling" — this runs via local `launchd` on the machine hosting the business's credentials and data, not a cloud routine (a cloud routine clones a fresh checkout from GitHub each run and can't see the gitignored `businesses/<slug>/.env` or `reviews.db` it would need).

To run it for a specific business (when more than one is configured):

> run the review-handler agent for &lt;slug&gt;

which has it pass `--business <slug>` to every `tools/*.py` call for that run instead of relying on `BUSINESS_SLUG` in `.env`.

## Adding another business

Each business is fully isolated — its own DB (`reviews.db`), its own Google OAuth credentials (`.env`), its own mock data. Nothing here requires touching an existing business's files.

1. Create `businesses/<new-slug>/`.
2. Add `business.json`:
   ```json
   {
     "name": "Some Other Business",
     "category": "...",
     "maps_url": "https://www.google.com/maps/place/...",
     "google_account_id": "",
     "google_location_id": ""
   }
   ```
   For a business with multiple physical locations under one account, use `"google_location_ids": ["...", "..."]` instead of the singular `google_location_id` — every review gets tagged with which location it came from, and replies get posted back to the matching one.

   Optional per-business overrides (fall back to the top-level `.env` / defaults when omitted): `"confidence_threshold": 0.9`, `"slack_webhook_url": "..."`, `"google_client_mode": "mock"`.
3. Add `profile.md` — reply voice, signature, any business-specific escalation notes (see the example in `businesses/brows-and-threading-city/profile.md`).
4. For demo/dev purposes, add a `seed_reviews.json` with a few sample reviews in the same shape as the existing one.
5. Once you have Google API access for this business, run `python3 tools/google_oauth_setup.py --business <new-slug>` and `python3 tools/google_list_locations.py --business <new-slug>` — this writes credentials into `businesses/<new-slug>/.env`, never the shared top-level one (see docs/API_SETUP.md).
6. Once live and fetched at least once, run `python3 tools/learn_voice.py --business <new-slug>` if the listing already has owner replies on Google — it samples them into `voice_sample.md` so you can write a grounded voice section in `profile.md` instead of guessing.
7. Either set `BUSINESS_SLUG=<new-slug>` in the top-level `.env` to make it the default, or just pass `--business <new-slug>` to every `tools/*.py` call (and tell the agent which business you mean when invoking it) to run it alongside other businesses without changing any defaults.

Nothing else changes: the same agent definition, tools, and DB schema work for any business.

## Status: Google Business Profile API access

Reading/replying to reviews on Google Maps is only officially possible through the **Google Business Profile API**, which requires Google to manually approve API access for your Cloud project against a verified, owned listing. That access has **not been requested/granted yet**.

**Until it is**, everything runs against `lib/google_client.py::MockGoogleBusinessProfileClient`, seeded from each business's `seed_reviews.json`, so the full classify → draft → route pipeline can be exercised end-to-end today.

**For the full walkthrough of getting live API access and generating the OAuth keys, see [docs/API_SETUP.md](docs/API_SETUP.md)** (also covers escalation alerts via Telegram or Slack). Short version: verify the listing → create a Google Cloud OAuth client → request Business Profile API access (manual review, days-to-weeks) → run `tools/google_oauth_setup.py` for a refresh token → run `tools/google_list_locations.py` to find your IDs → set `GOOGLE_CLIENT_MODE=live`.

## Setup

Nothing to install. Just:

```bash
cp .env.example .env
```

`.env` holds service credentials the tool scripts use (Slack webhook URL, Google OAuth once live) and `BUSINESS_SLUG` — never a model/LLM API key.

Run the agent (see "Running the agent" above), then inspect/act on results directly:

```bash
python3 tools/list_pending.py
python3 tools/approve.py --review-id 3
python3 tools/approve.py --review-id 3 --edit "edited reply text"
python3 tools/reject.py --review-id 5
```

## Configuration

Top-level `.env` holds cross-cutting defaults, overridable per business:

| Variable | Default | Meaning |
|---|---|---|
| `BUSINESS_SLUG` | the only dir under `businesses/`, if there's exactly one | Which `businesses/<slug>/` is active when a tool isn't given `--business`. |
| `CONFIDENCE_THRESHOLD` | `0.85` | Minimum confidence to auto-post — unless a business sets its own `confidence_threshold` in `business.json`. |
| `GOOGLE_CLIENT_MODE` | `mock` | `mock` or `live` — unless a business sets its own `google_client_mode` in `business.json`. |
| `SLACK_WEBHOOK_URL` | — | Escalation alerts destination — unless a business sets its own `slack_webhook_url` in `business.json`. |

Everything specific to one business lives under `businesses/<slug>/`, never the top-level `.env`:
- `business.json` — name, Maps URL, Google account/location IDs, and any of the overrides above.
- `.env` (gitignored) — that business's own `GOOGLE_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_REFRESH_TOKEN`, and `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` if using Telegram for escalation alerts. See docs/API_SETUP.md.
- `reviews.db` (gitignored) — that business's own SQLite DB, created automatically on first run.

Escalation alerts (`lib/notifier.py`) use a plug-and-play connector interface — each channel (`TelegramNotifier`, `SlackNotifier`) implements the same `send(message)` interface, mirroring `lib/google_client.py`'s Mock/Live pattern. Every channel a business has credentials for gets used, not just the first found; adding a new channel (email, Discord, SMS, ...) means writing one class and registering it, nothing else in the codebase needs to change.

Every `tools/*.py` script accepts `--business <slug>` to operate on a specific business regardless of `BUSINESS_SLUG`.

## Hardening & operations

- **`python3 tools/check_health.py [--business <slug>]`** — OAuth token validity, secrets file permissions, review queue backlog, and last-run summary in one report. Worth running periodically even without a scheduler.
- **`python3 tools/fetch_reviews.py`** refuses to hand back more than 50 actionable reviews at once (`--allow-large-batch` to override) — a safety net against an agent unattended-processing an unexpectedly huge batch.
- Google API calls retry transient failures (429/5xx, network errors) with backoff before giving up.
- `python3 -m unittest discover -s tests -t .` — stdlib-only test suite (no new dependency) covering the core library code.

Full detail on all of the above: [docs/OPERATIONS.md](docs/OPERATIONS.md).
