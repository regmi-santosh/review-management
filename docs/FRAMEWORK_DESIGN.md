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
- **Voice-learning is now a repeatable tool, not a one-off manual analysis.** `tools/learn_voice.py` samples a business's own pre-existing owner replies (tagged `reply_source='owner'` at fetch time — see below) and writes them, paired with their review, to `businesses/<slug>/voice_sample.md` (gitignored: it contains real customer review text). Verified against Brows & Threading City's real data: reproduces the same voice pattern (thank-you opener, 🌸/💖, no formal sign-off) that was originally identified by hand. The judgment of turning that sample into `profile.md`'s prose voice section is still a separate, human-or-agent-assisted step — this tool only automates the mechanical sampling.
  - This required distinguishing genuine historic owner replies from ones this system posts itself, so the sampler never learns from — and reinforces — its own drafts. `reviews.reply_source` is `'owner'` (set on fetch, from Google's `reviewReply` field, before this system existed) or `'agent'` (set by `lib/actions.py::post_review_reply`, whenever this system posts — auto or human-approved). Existing DBs migrate automatically on connect (`lib/store.py::_migrate`), backfilled from the fact that the agent always sets `reasoning` before posting.
- **Multi-location clients are modeled.** A client with several physical locations under one Business Profile account uses `"google_location_ids": [...]` in `business.json` instead of the singular `"google_location_id"` (still supported for the single-location case — `Business.google_location_ids` always returns a uniform list either way). `LiveGoogleBusinessProfileClient.fetch_reviews()` pulls from every configured location and tags each review with a `location_id` column (needed because posting a reply requires knowing which location's endpoint to hit); `post_reply()` takes an explicit `location_id` argument and raises clearly if one isn't recorded rather than guessing. Existing single-location DBs migrate automatically, backfilling `location_id` from the business's one configured location; a DB with ambiguous (multiple) locations configured is left alone rather than guessed at. Verified end-to-end with a throwaway two-location mock business: reviews correctly tagged per location, replies correctly routed to the matching location's endpoint.

## Remaining gaps

None from the original list — multi-location was the last deferred item. Future gaps will show up here as real clients surface them (per the "don't build speculatively" principle this document has followed throughout).

## Onboarding checklist (current, working state)

For a new client `<slug>`:

1. `mkdir businesses/<slug>`
2. Write `businesses/<slug>/business.json` (name, category, maps_url; leave `google_account_id`/`google_location_id` blank for now).
3. Get that client's own Google Business Profile API access approved (their listing, their Google account) — see `docs/API_SETUP.md`; this is inherently per-client and can't be batched.
4. `python3 tools/google_oauth_setup.py --business <slug> --client-id ... --client-secret ...` → writes that client's OAuth secrets into `businesses/<slug>/.env`, isolated from every other business.
5. `python3 tools/google_list_locations.py --business <slug>` → fill in `business.json` (`google_location_id` for one location, `google_location_ids: [...]` for several).
6. Set `"google_client_mode": "live"` in that business's `business.json`, then `python3 tools/fetch_reviews.py --business <slug>` → pulls their real review history into `businesses/<slug>/reviews.db`, including past replies (auto-protected from being overwritten).
7. `python3 tools/learn_voice.py --business <slug>` → writes `businesses/<slug>/voice_sample.md`; a human (or an agent-assisted pass) reads it and writes `businesses/<slug>/profile.md`'s voice section. Skip this if the listing has no pre-existing owner replies yet (nothing to learn from) — write voice guidance from scratch instead.
8. Run the review-handler agent against `<slug>` and review the first batch's output before trusting it unattended.

No step here touches `.claude/agents/review-handler.md`, `lib/`, or any other client's directory — that's the actual definition of "framework," and this round of work is what made that true rather than aspirational.
