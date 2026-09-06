# Turning this into a multi-client framework

This system already runs against real data for one business (Brows & Threading City) end-to-end: fetch → classify → draft → route → post/escalate/queue. This document tracks what's needed to onboard a second, third, and Nth client without touching the core code — Brows & Threading City is just the first use case the framework serves, not the thing the framework is built around.

## What's already generic

- **The reasoning itself.** `.claude/agents/review-handler.md` has no business-specific logic in it — classification rubric, drafting rules, and the escalate/auto-post/queue routing policy all apply to any business. Per-business specifics are externalized to `businesses/<slug>/profile.md`, which the agent reads at the start of every run, and it knows to pass `--business <slug>` to every tool call when handling a specific one.
- **The `businesses/<slug>/` convention**, and — as of this round of work — **true per-business isolation**, not just per-business config files:
  - `business.json` — structured facts (name, Maps URL, Google account/location IDs) plus optional overrides (`confidence_threshold`, `slack_webhook_url`, `google_client_mode`) that fall back to the top-level `.env` when a business doesn't set its own.
  - `businesses/<slug>/.env` (gitignored) — that business's own Google OAuth credentials. **Never shared globally** — a second client's listing is normally owned by a completely different Google account, so this was the gap that would have actually blocked onboarding a real second client.
  - `businesses/<slug>/reviews.db` (gitignored) — that business's own SQLite DB. No shared file, no cross-business table.
  - `profile.md`, `seed_reviews.json` — voice/context and mock data, as before.
  - `lib/config.py`'s `Business` class resolves all of this into one object (`config.active()`); `use_business(slug)` switches it. Every module that used to read frozen top-level constants (`lib/store.py`, `lib/google_client.py`, `lib/notifier.py`) now calls `config.active()` at the point of use, so switching business mid-process works correctly.
- **Every `tools/*.py` script accepts `--business <slug>`** (`lib/cli.py`'s `add_business_arg`/`apply_business_arg`), defaulting to `BUSINESS_SLUG`/the sole business directory when omitted. Verified with a throwaway second business: isolated DB file, isolated mock data, a `google_client_mode` override working independently of the global (`live`) default — and the first business's 362-review DB was untouched throughout.

## Remaining gaps

### Voice-learning is still a manual, one-off analysis

Onboarding Brows & Threading City's `profile.md` voice section involved a human (this session) reading a sample of ~330 past replies and hand-summarizing the pattern into prose. That doesn't scale to "onboard client #5 in ten minutes."

**Fix**: a `tools/learn_voice.py` script that, given a business already fetched at least once in live mode, pulls a random sample of `posted` reviews where `posted_reply` came from `existing_reply` (i.e., genuinely pre-existing owner replies, not ones this system posted), and dumps them in a structured format (review text + reply, paired) to a file. The *judgment* of turning that into prose guidance still belongs in an agent-assisted step (read the sample, write `profile.md`'s voice section) — but the mechanical part (find, sample, format) shouldn't be a bespoke one-off each time.

### Multi-location clients aren't modeled

`business.json` has a single `google_location_id`. A client that owns multiple physical locations under one Business Profile account (common for any small chain) doesn't fit today's one-location-per-business assumption.

**Fix**: defer until it's actually needed by a real client — don't build this speculatively. When it comes up, `business.json`'s `google_location_id` becomes `google_location_ids: [...]`, and `fetch_reviews.py`/`post_reply.py` loop over them, tagging each review with which location it came from (a new `location_id` column in the reviews table).

## Onboarding checklist (current, working state)

For a new client `<slug>`:

1. `mkdir businesses/<slug>`
2. Write `businesses/<slug>/business.json` (name, category, maps_url; leave `google_account_id`/`google_location_id` blank for now).
3. Get that client's own Google Business Profile API access approved (their listing, their Google account) — see `docs/API_SETUP.md`; this is inherently per-client and can't be batched.
4. `python3 tools/google_oauth_setup.py --business <slug> --client-id ... --client-secret ...` → writes that client's OAuth secrets into `businesses/<slug>/.env`, isolated from every other business.
5. `python3 tools/google_list_locations.py --business <slug>` → fill in `business.json`.
6. Set `"google_client_mode": "live"` in that business's `business.json`, then `python3 tools/fetch_reviews.py --business <slug>` → pulls their real review history into `businesses/<slug>/reviews.db`, including past replies (auto-protected from being overwritten).
7. `python3 tools/learn_voice.py --business <slug>` (once built) → produces a sample of past-reply pairs; a human (or an agent-assisted pass) turns that into `businesses/<slug>/profile.md`'s voice section.
8. Run the review-handler agent against `<slug>` and review the first batch's output before trusting it unattended.

No step here touches `.claude/agents/review-handler.md`, `lib/`, or any other client's directory — that's the actual definition of "framework," and this round of work is what made that true rather than aspirational.
