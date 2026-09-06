# Review Management Agent

An agentic system that reads Google reviews for a business and handles them:

1. **Classify** each review (category, sentiment, urgency, confidence).
2. **Draft** a human-toned reply, in that business's voice.
3. **Route** it:
   - **Highly negative** (`sentiment=negative` and `urgency` is `high`/`critical`) → **escalate immediately** to a human (Slack webhook, or console log by default). Reply is held for approval — never auto-posted.
   - **High confidence** (`confidence >= CONFIDENCE_THRESHOLD`, default `0.85`) and not highly negative → **auto-post** the reply.
   - **Otherwise** → queue the draft for **human approval**.

The system itself is generic — it isn't written for any one business. The classification/drafting/routing logic in [.claude/agents/review-handler.md](.claude/agents/review-handler.md) is business-agnostic; a specific business is just a config directory under `businesses/`. The first one set up is [businesses/brows-and-threading-city](businesses/brows-and-threading-city) ([Google Maps listing](https://www.google.com/maps/place/Brows+%26+Threading+City/@41.2887591,-96.0845815,17z)), used here as a concrete example/demo — see "Adding another business" below to point this at a different one.

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
  google_list_locations.py   one-time: discover your Google account/location IDs

lib/                  shared code the tools above import (no ORM, no web framework)
  config.py           loads .env + the active business's business.json — service credentials
                       only (Slack webhook, Google OAuth). No LLM key: nothing here calls a model API.
  store.py             plain sqlite3 (stdlib) persistence — no ORM
  google_client.py    GoogleBusinessProfileClient interface + Mock/Live implementations (stdlib
                       urllib for HTTP — no third-party HTTP client)
  notifier.py          escalation notifications (console / Slack, via urllib)
  actions.py           shared post/reject logic used by the CLI tools

businesses/<slug>/     one directory per business (see "Adding another business")
  business.json        structured facts: name, Maps URL, Google account/location IDs
  profile.md           free-text voice/context the agent reads directly (Step 0 of the agent)
  seed_reviews.json    mock review data used while GOOGLE_CLIENT_MODE=mock
```

**Dependencies: none.** Everything is Python 3 standard library (`sqlite3`, `urllib`, `argparse`, `json`, `dataclasses`, `http.server`, `webbrowser`). There's no `requirements.txt`, no virtualenv to set up, no `pip install` step — just `python3 tools/<script>.py`.

### Running the agent

There's no scheduler wired up yet, by design, while we're on mock data. To process the current batch of new reviews, just ask Claude Code to run it, e.g.:

> run the review-handler agent

It will read the active business's profile, run `tools/fetch_reviews.py`, classify/draft/route each new review itself, and call the appropriate tool script(s) directly. Once this is validated end-to-end, wiring it to a real schedule is a later addition (e.g. the `schedule` skill) — no changes needed to the agent or tools.

## Adding another business

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
3. Add `profile.md` — reply voice, signature, any business-specific escalation notes (see the example in `businesses/brows-and-threading-city/profile.md`).
4. For demo/dev purposes, add a `seed_reviews.json` with a few sample reviews in the same shape as the existing one.
5. Set `BUSINESS_SLUG=<new-slug>` in `.env` (or just don't set it if this is the only business directory — it's picked automatically).

Nothing else changes: the same agent definition, tools, and DB schema work for any business.

## Status: Google Business Profile API access

Reading/replying to reviews on Google Maps is only officially possible through the **Google Business Profile API**, which requires Google to manually approve API access for your Cloud project against a verified, owned listing. That access has **not been requested/granted yet**.

**Until it is**, everything runs against `lib/google_client.py::MockGoogleBusinessProfileClient`, seeded from each business's `seed_reviews.json`, so the full classify → draft → route pipeline can be exercised end-to-end today.

**For the full walkthrough of getting live API access and generating the OAuth keys, see [docs/API_SETUP.md](docs/API_SETUP.md)** (also covers the optional Slack webhook for escalation alerts). Short version: verify the listing → create a Google Cloud OAuth client → request Business Profile API access (manual review, days-to-weeks) → run `tools/google_oauth_setup.py` for a refresh token → run `tools/google_list_locations.py` to find your IDs → set `GOOGLE_CLIENT_MODE=live`.

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

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BUSINESS_SLUG` | the only dir under `businesses/`, if there's exactly one | Which `businesses/<slug>/` to use. |
| `CONFIDENCE_THRESHOLD` | `0.85` | Minimum confidence for the agent to auto-post a reply. |
| `GOOGLE_CLIENT_MODE` | `mock` | `mock` or `live`. |
| `SLACK_WEBHOOK_URL` | — | Optional. If set, escalations post here instead of just logging. |
| `GOOGLE_OAUTH_*` | — | Only needed once `GOOGLE_CLIENT_MODE=live`. See docs/API_SETUP.md. |

Business name, Maps URL, and Google account/location IDs live in `businesses/<slug>/business.json`, not `.env` — see "Adding another business".

The local DB is a single file, `review_management.db` (sqlite3, created automatically on first run, gitignored).
