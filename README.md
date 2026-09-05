# Review Management Agent

An agentic system for **Brows & Threading City** ([Google Maps listing](https://www.google.com/maps/place/Brows+%26+Threading+City/@41.2887591,-96.0845815,17z)) that reads Google reviews and handles them:

1. **Classify** each review (category, sentiment, urgency, confidence).
2. **Draft** a human-toned reply.
3. **Route** it:
   - **Highly negative** (`sentiment=negative` and `urgency` is `high`/`critical`) → **escalate immediately** to a human (Slack webhook, or console log by default). Reply is held for approval — never auto-posted.
   - **High confidence** (`confidence >= CONFIDENCE_THRESHOLD`, default `0.85`) and not highly negative → **auto-post** the reply.
   - **Otherwise** → queue the draft for **human approval**.

## How it's built: harness-native, not a bolted-on LLM service

The reasoning (classification + drafting + routing policy) lives in a Claude Code **subagent**, [.claude/agents/review-handler.md](.claude/agents/review-handler.md) — not in a separate Python call to a model API. That agent does the actual thinking; Python is only used for thin, deterministic **tool scripts** it invokes via Bash:

```
tools/
  fetch_reviews.py    pull new reviews from Google (mock or live) into the local DB
  save_review.py      persist the agent's classification + draft + routing decision
  post_reply.py       post a reply through the Google client, mark it posted
  notify.py           fire an escalation alert (console / Slack)
  list_pending.py     human helper: show everything awaiting a decision
  approve.py          human helper: post a queued/escalated draft (optionally edited)
  reject.py           human helper: dismiss a queued review with no reply
```

`app/` is the shared library these scripts (and the dashboard below) import: DB models, config, the Google client, notifier, and posting/rejecting logic (`app/services.py`) — no logic is duplicated between the CLI tools and the dashboard.

A small **FastAPI dashboard** (`app/main.py`, `app/routes.py`) sits on top of the same SQLite DB purely as a human-approval UI/API (list pending/escalated reviews, edit a draft, approve, reject) — it does not orchestrate or run the agent.

### Running the agent

There's no scheduler wired up yet (by design, while we're on mock data — see below). To process the current batch of new reviews, just ask Claude Code to run it, e.g.:

> run the review-handler agent

or invoke it directly as a subagent. It will run `tools/fetch_reviews.py`, classify/draft/route each new review, and call the appropriate tool script(s) itself. Once this is validated end-to-end, wiring it to a real schedule is a one-line addition (the `schedule` skill, cron, etc.) — no changes needed to the agent or tools.

## Status: Google Business Profile API access

Reading/replying to reviews on Google Maps is only officially possible through the **Google Business Profile API**, which requires Google to manually approve API access for your Cloud project against a verified, owned listing. That access has **not been requested/granted yet** for Brows & Threading City.

To unblock live mode:

1. Verify ownership of the "Brows & Threading City" listing in [Google Business Profile Manager](https://business.google.com/).
2. Create a Google Cloud project, enable the Business Profile API family (Account Management, Business Information, and the reviews endpoints under the My Business APIs).
3. Request access via the [Business Profile API access request form](https://developers.google.com/my-business/content/prereqs) — Google reviews requests manually; this can take days to weeks.
4. Once approved, set up OAuth2 credentials (client ID/secret + a refresh token for an account that manages this location) and fill in `.env` (see `.env.example`).
5. Set `GOOGLE_CLIENT_MODE=live` in `.env`. Everything else (agent, tools, dashboard) is unchanged — only `app/google_client.py`'s `LiveGoogleBusinessProfileClient` gets used instead of the mock.

**Until then**, everything runs against `app/google_client.py::MockGoogleBusinessProfileClient`, seeded from `data/seed_reviews.json` with realistic sample reviews for this business, so the full classify → draft → route pipeline can be exercised end-to-end today.

## Project layout

```
.claude/agents/review-handler.md   the agent: classification rubric, drafting style, routing policy
tools/                             thin Python scripts the agent calls via Bash (see above)
app/
  config.py       env-driven settings (confidence threshold, Google client mode, Slack webhook, ...)
  db.py           SQLite (SQLModel) engine/session
  models.py       Review ORM model + status/category/sentiment/urgency enums
  schemas.py      Pydantic schemas for the dashboard API
  google_client.py  GoogleBusinessProfileClient interface + Mock/Live implementations
  services.py     shared post/reject logic used by both tools/ and the dashboard
  notifier.py     escalation notifications (console / Slack webhook)
  routes.py       FastAPI routes for the human-approval dashboard
  main.py         FastAPI app entrypoint
data/seed_reviews.json   sample reviews used by the mock Google client
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run the agent (see "Running the agent" above), then inspect results directly:

```bash
python3 tools/list_pending.py
python3 tools/approve.py --review-id 3
python3 tools/reject.py --review-id 5
```

Or run the dashboard API:

```bash
uvicorn app.main:app --reload
curl http://localhost:8000/reviews
curl http://localhost:8000/reviews?status=pending_review
curl -X POST http://localhost:8000/reviews/3/approve
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `0.85` | Minimum confidence for the agent to auto-post a reply. |
| `GOOGLE_CLIENT_MODE` | `mock` | `mock` or `live`. |
| `SLACK_WEBHOOK_URL` | — | Optional. If set, escalations post here instead of just logging. |
| `BUSINESS_NAME` | `Brows & Threading City` | Used in prompts/notifications. |
| `DATABASE_URL` | `sqlite:///./review_management.db` | SQLite DB path. |
| `GOOGLE_OAUTH_*`, `GOOGLE_BUSINESS_*` | — | Only needed once `GOOGLE_CLIENT_MODE=live`. |

## Tests

```bash
pytest
```
