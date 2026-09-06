# Review Management Agent

An agentic system for **Brows & Threading City** ([Google Maps listing](https://www.google.com/maps/place/Brows+%26+Threading+City/@41.2887591,-96.0845815,17z)) that reads Google reviews and handles them:

1. **Classify** each review (category, sentiment, urgency, confidence).
2. **Draft** a human-toned reply.
3. **Route** it:
   - **Highly negative** (`sentiment=negative` and `urgency` is `high`/`critical`) → **escalate immediately** to a human (Slack webhook, or console log by default). Reply is held for approval — never auto-posted.
   - **High confidence** (`confidence >= CONFIDENCE_THRESHOLD`, default `0.85`) and not highly negative → **auto-post** the reply.
   - **Otherwise** → queue the draft for **human approval**.

## Architecture: harness-native, not a Python service

There is no separate LLM API call anywhere in this repo, and no API key for a model. The reasoning — classification, drafting, and the routing policy — is entirely the job of a Claude Code **subagent**, [.claude/agents/review-handler.md](.claude/agents/review-handler.md), which runs as the model already powering your VS Code / Claude Code session. Python only exists for thin, deterministic **tool scripts** that the agent invokes via Bash:

```
tools/
  fetch_reviews.py    pull new reviews from Google (mock or live) into the local DB
  save_review.py      persist the agent's classification + draft + routing decision
  post_reply.py       post a reply through the Google client, mark it posted
  notify.py           fire an escalation alert (console / Slack)
  list_pending.py     human helper: show everything awaiting a decision
  approve.py          human helper: post a queued/escalated draft (optionally edited)
  reject.py           human helper: dismiss a queued review with no reply

lib/                  shared code the tools above import (no ORM, no web framework)
  config.py           loads .env into os.environ — service credentials only (Slack webhook,
                       Google OAuth client/secret/refresh token). No LLM key: nothing here calls
                       a model API.
  store.py            plain sqlite3 (stdlib) persistence — no ORM
  google_client.py    GoogleBusinessProfileClient interface + Mock/Live implementations (stdlib
                       urllib for HTTP — no third-party HTTP client)
  notifier.py         escalation notifications (console / Slack, via urllib)
  actions.py          shared post/reject logic used by the CLI tools
```

**Dependencies: none.** Everything is Python 3 standard library (`sqlite3`, `urllib`, `argparse`, `json`, `dataclasses`). There's no `requirements.txt`, no virtualenv to set up, no `pip install` step — just `python3 tools/<script>.py`.

### Running the agent

There's no scheduler wired up yet, by design, while we're on mock data. To process the current batch of new reviews, just ask Claude Code to run it, e.g.:

> run the review-handler agent

It will run `tools/fetch_reviews.py`, classify/draft/route each new review itself, and call the appropriate tool script(s) directly. Once this is validated end-to-end, wiring it to a real schedule is a later addition (e.g. the `schedule` skill) — no changes needed to the agent or tools.

## Status: Google Business Profile API access

Reading/replying to reviews on Google Maps is only officially possible through the **Google Business Profile API**, which requires Google to manually approve API access for your Cloud project against a verified, owned listing. That access has **not been requested/granted yet** for Brows & Threading City.

To unblock live mode:

1. Verify ownership of the "Brows & Threading City" listing in [Google Business Profile Manager](https://business.google.com/).
2. Create a Google Cloud project, enable the Business Profile API family (Account Management, Business Information, and the reviews endpoints under the My Business APIs).
3. Request access via the [Business Profile API access request form](https://developers.google.com/my-business/content/prereqs) — Google reviews requests manually; this can take days to weeks.
4. Once approved, set up OAuth2 credentials (client ID/secret + a refresh token for an account that manages this location) and fill them into `.env` (see `.env.example`).
5. Set `GOOGLE_CLIENT_MODE=live` in `.env`. Everything else (agent, tools) is unchanged — only `lib/google_client.py`'s `LiveGoogleBusinessProfileClient` gets used instead of the mock.

**Until then**, everything runs against `lib/google_client.py::MockGoogleBusinessProfileClient`, seeded from `data/seed_reviews.json` with realistic sample reviews for this business, so the full classify → draft → route pipeline can be exercised end-to-end today.

## Setup

Nothing to install. Just:

```bash
cp .env.example .env
```

`.env` holds service credentials the tool scripts use (Slack webhook URL, Google OAuth details once live) — never a model/LLM API key.

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
| `CONFIDENCE_THRESHOLD` | `0.85` | Minimum confidence for the agent to auto-post a reply. |
| `GOOGLE_CLIENT_MODE` | `mock` | `mock` or `live`. |
| `SLACK_WEBHOOK_URL` | — | Optional. If set, escalations post here instead of just logging. |
| `BUSINESS_NAME` | `Brows & Threading City` | Used in prompts/notifications. |
| `GOOGLE_OAUTH_*`, `GOOGLE_BUSINESS_*` | — | Only needed once `GOOGLE_CLIENT_MODE=live`. |

The local DB is a single file, `review_management.db` (sqlite3, created automatically on first run, gitignored).
