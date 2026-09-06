# Turning this into a multi-client framework

This system already runs against real data for one business (Brows & Threading City) end-to-end: fetch → classify → draft → route → post/escalate/queue. This document is the plan for generalizing it so a second, third, and Nth client can be onboarded without touching the core code — Brows & Threading City becomes just the first use case the framework serves, not the thing the framework is built around.

## What's already generic (don't need to change)

- **The reasoning itself.** `.claude/agents/review-handler.md` has no business-specific logic in it — classification rubric, drafting rules, and the escalate/auto-post/queue routing policy all apply to any business. Per-business specifics are already externalized to `businesses/<slug>/profile.md`, which the agent reads at the start of every run.
- **The `businesses/<slug>/` convention.** `business.json` (structured facts) + `profile.md` (voice/context) + `seed_reviews.json` (mock data) is a clean per-business unit already. Adding a directory is enough for the agent and tools to pick up a new business's identity and mock data.
- **The tool scripts and `lib/` code.** Nothing in `tools/*.py` or `lib/*.py` has Brows & Threading City hardcoded — they all go through `lib/config.py`'s resolution of the active business.

## Gaps that block true multi-client use

These are the places where the current design still assumes "one business, configured globally" rather than "many businesses, selected per-run."

### 1. OAuth credentials are global, but they shouldn't be

`GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` live in the single top-level `.env`. That's fine for one client, but a second client's Google Business Profile listing will almost always be managed by a **different Google account** than the first client's — these aren't just different locations under one account, they're different owners entirely. A shared `.env` can only hold one set of credentials at a time.

**Fix**: move OAuth credentials into a per-business secrets file — `businesses/<slug>/.env` (gitignored, same `KEY=value` format `lib/config.py` already parses) or a `secrets.json` alongside `business.json`. `lib/config.py` should load the active business's secrets file in addition to (or instead of) the top-level `.env`. Each client goes through their own `tools/google_oauth_setup.py` run, authorizing as their own Google account, and their token lands in their own business directory.

### 2. One shared SQLite database

`review_management.db` is a single file at the repo root. Two businesses' reviews would currently land in the same table, distinguished only by `external_id` happening not to collide (which it won't, since Google's review IDs are globally unique, but the *design intent* of one DB for all clients is still fragile — one client's data is mixed into a file that has nothing to do with them, backups/deletes aren't per-client, and any future per-business analytics query needs an extra filter that's easy to forget).

**Fix**: `lib/store.py`'s `DB_PATH` should be `businesses/<slug>/reviews.db` instead of a repo-root file. Trivial change (one path expression), but do it before onboarding a second client.

### 3. Confidence threshold and Slack webhook are global too

Same shape of problem as #1: `CONFIDENCE_THRESHOLD` and `SLACK_WEBHOOK_URL` live in the shared `.env`. A newer, less-established client might reasonably want a higher confidence bar before auto-posting (less historical voice data to learn from); different clients may want alerts in different Slack workspaces/channels entirely.

**Fix**: make these overridable per-business in `business.json`, falling back to the `.env` value as a global default when a business doesn't specify its own. (This is a small, backward-compatible addition to `lib/config.py` — read the business.json value first, fall back to the env-derived one.)

### 4. Voice-learning is a manual, one-off analysis today

Onboarding Brows & Threading City's `profile.md` voice section involved a human (this session) reading a sample of ~330 past replies and hand-summarizing the pattern into prose. That doesn't scale to "onboard client #5 in ten minutes."

**Fix**: a `tools/learn_voice.py` script that, given a business with `GOOGLE_CLIENT_MODE=live` already fetched at least once, pulls a random sample of `posted` reviews where `posted_reply` came from `existing_reply` (i.e., genuinely pre-existing owner replies, not ones this system posted), and dumps them in a structured format (review text + reply, paired) to a file. The *judgment* of turning that into prose guidance still belongs in an agent-assisted step (read the sample, write `profile.md`'s voice section) — but the mechanical part (find, sample, format) shouldn't be a bespoke one-off script each time.

### 5. Tools implicitly operate on "the" active business

Every tool script resolves the business via `config.BUSINESS_SLUG`, which comes from `.env` (or the single existing directory, if there's only one). That's workable for "one client at a time, switch `.env` between runs," but breaks down the moment you want, say, a scheduled job that processes multiple clients' reviews in one pass, or you're just tired of editing `.env` to switch context.

**Fix**: add an optional `--business <slug>` flag to every tool script (`fetch_reviews.py`, `save_review.py`, `post_reply.py`, `notify.py`, `list_pending.py`, `approve.py`, `reject.py`), defaulting to `config.BUSINESS_SLUG` for backward compatibility when omitted. The agent definition gains a note: "if asked to handle a specific business, pass `--business <slug>` to every tool call this run." This is additive and doesn't require touching `lib/config.py`'s resolution logic — just threading one new CLI arg through.

### 6. Multi-location clients aren't modeled

`business.json` has a single `google_location_id`. A client that owns multiple physical locations under one Business Profile account (common for any small chain) doesn't fit today's one-location-per-business assumption.

**Fix**: defer until it's actually needed by a real client — don't build this speculatively. When it comes up, `business.json`'s `google_location_id` becomes `google_location_ids: [...]`, and `fetch_reviews.py`/`post_reply.py` loop over them, tagging each review with which location it came from (a new `location_id` column in the reviews table).

## Suggested sequencing

1. **Now**: per-business DB path (#2) and `--business` flag on tools (#5) — small, low-risk, unblock everything else.
2. **Before onboarding client #2**: per-business OAuth secrets (#1) — this is the one that actually blocks a second real client, since client #2's Google account is guaranteed to be different from client #1's.
3. **When it matters**: per-business confidence/Slack overrides (#3) and `tools/learn_voice.py` (#4) — quality-of-life and onboarding-speed improvements, not blockers.
4. **Only if a real client needs it**: multi-location support (#6).

## Onboarding checklist (target state, once #1–#5 are done)

For a new client `<slug>`:

1. `mkdir businesses/<slug>`
2. Write `businesses/<slug>/business.json` (name, category, maps_url; leave `google_account_id`/`google_location_id` blank for now).
3. Get that client's own Google Business Profile API access approved (their listing, their Google account) — see `docs/API_SETUP.md`; this is inherently per-client and can't be batched.
4. `python3 tools/google_oauth_setup.py --business <slug>` → writes that client's OAuth secrets into `businesses/<slug>/.env` (once #1 is done).
5. `python3 tools/google_list_locations.py --business <slug>` → fill in `business.json`.
6. `GOOGLE_CLIENT_MODE=live python3 tools/fetch_reviews.py --business <slug>` → pulls their real review history, including past replies.
7. `python3 tools/learn_voice.py --business <slug>` (once #4 is done) → produces a sample of past-reply pairs; a human (or an agent-assisted pass) turns that into `businesses/<slug>/profile.md`'s voice section.
8. Run the review-handler agent against `<slug>` and review the first batch's output before trusting it unattended.

No step here touches `.claude/agents/review-handler.md`, `lib/`, or any other client's directory — that's the actual definition of "framework," and is the bar this document's changes are aimed at clearing.
