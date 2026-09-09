# Client onboarding: bringing a new business/franchise onto the platform

This is the ordered checklist for taking a new business from zero to fully running — start to finish, in the order you'd actually do it. It's a **thin index over the detailed docs**, not a replacement for them: each step links to where the real how-to and gotchas live ([README.md](../README.md), [API_SETUP.md](API_SETUP.md), [ARCHITECTURE.md](ARCHITECTURE.md), [OPERATIONS.md](OPERATIONS.md)) rather than duplicating their content, so this doc doesn't go stale independently of them.

This system is multi-tenant by design — every step below is scoped to one business (`--business <slug>`) and never touches another business's data or credentials.

## 0. Prerequisites — what the business needs to already have

Confirm these exist before starting; nothing below can substitute for them:

- A **Google Business Profile listing**, claimed and verified by the business (or someone with admin access to do so) in [Google Business Profile Manager](https://business.google.com/).
- A **Facebook Page** (not a personal profile) — only if this business wants social post drafting/publishing. Optional.
- A **Telegram** account (recommended) or **Slack workspace** — only if this business wants escalation alerts and daily summaries. Strongly recommended before scheduling anything unattended; without one, escalations just print to a console nobody's watching.

## 1. Create the business directory

Everything specific to this business lives under `businesses/<slug>/`, fully isolated from every other business.

→ **[README.md "Adding another business"](../README.md#adding-another-business)** for the exact `business.json`/`profile.md` fields, including the optional per-business overrides (`confidence_threshold`, `google_client_mode`, social-draft settings, brand colors/logo).

Do this first — every later step (`--business <slug>`) assumes the directory already exists.

## 2. Google Business Profile — API access and OAuth

This is the long pole: Google's API access approval is a manual review that can take days to weeks. Start it as early as possible, even before the rest of onboarding is done.

→ **[API_SETUP.md, Steps 1–6](API_SETUP.md)**: enable the right Cloud APIs → OAuth consent screen → create the OAuth client → `tools/google_oauth_setup.py` for a refresh token → `tools/google_list_locations.py` to find account/location IDs → set `google_client_mode` to `live`.

**Multi-location businesses**: if this one has several physical locations under one Google account, use `google_location_ids` (plural) instead of the singular field — see the README section above for the exact shape.

## 3. Escalation channel — Telegram or Slack

Without this, a highly-negative review just prints to a console; with it, a human gets pinged immediately and (for Telegram) can approve/reject/edit right from their phone.

→ **[API_SETUP.md "Escalation alerts: Telegram or Slack"](API_SETUP.md#escalation-alerts-telegram-or-slack-optional-but-strongly-recommended-before-scheduling)**. Telegram is recommended for a non-technical business owner — no developer account needed on their end, just the Telegram app and `tools/telegram_setup.py`.

## 4. Social posting (optional) — Facebook (+ Instagram credential)

Only relevant if the business wants the drafted quote-card images actually published, not just sent to Telegram/Slack for a human to post manually.

→ **[API_SETUP.md "Meta platforms (Facebook, Instagram)"](API_SETUP.md)**: assumes the one-time platform-level Meta app setup already exists (done once, ever, not per business — check with whoever set up the platform if you're not sure); then it's one command, `tools/meta_oauth_setup.py --business <slug>`, for this business's own Facebook admin to authorize.

**Brand look**: optional `business.json` keys (`brand_color`, `brand_text_color`, `brand_font_path`) and a `businesses/<slug>/logo.png` file control the quote-card image's appearance — see [README.md's business.json field list](../README.md#adding-another-business). Falls back to sensible generic defaults and the business name as text if skipped.

**Not yet available**: Instagram posting itself (credential gets captured automatically alongside Facebook's, but publishing isn't implemented yet — see [ARCHITECTURE.md "Social platform layer"](ARCHITECTURE.md) for why), X/Twitter, TikTok, WhatsApp.

## 5. Voice calibration (recommended if the listing has history)

If this business already has owner replies on Google from before this system existed, don't guess at their voice — sample it.

→ Run `python3 tools/learn_voice.py --business <slug>` (after Step 2 is live and has fetched at least once) — samples existing replies into `voice_sample.md` so `profile.md`'s voice section can be grounded in how this business actually already writes, not invented.

## 6. Verify — `tools/check_health.py`

```bash
python3 tools/check_health.py --business <slug>
```

This is the single gate — walk down every line before considering onboarding done:

| Check | OK means | If not OK |
|---|---|---|
| Secrets file permissions | `businesses/<slug>/.env` is `600` | Auto-fixed if it wasn't |
| Google OAuth | refresh token round-trips against Google | Re-run Step 2's `google_oauth_setup.py` |
| Escalation channel | Telegram and/or Slack configured | Revisit Step 3, or accept console-only (not recommended for scheduling) |
| Agent harness | the configured `AGENT_HARNESS` has a matching adapter | Platform-level config issue, not per-business — see ARCHITECTURE.md "Harness layer" |
| Social platforms | Pillow installed, enabled platforms list is valid | `pip install -r requirements.txt`, or fix a `social_platforms` typo in `business.json` |
| Facebook posting | token round-trips against the Graph API (or Facebook just isn't enabled for this business, which is also OK) | Re-run Step 4's `meta_oauth_setup.py` |
| Review queue | reports current pending/escalated count | Informational |
| Last run | reports the most recent run's tallies | Informational (no run yet is fine for a brand-new business) |

Exit code 0 = everything's OK, 1 = warnings, 2 = something failed. Don't schedule anything unattended (Step 8) until this is exit-0 or the warnings are ones you've deliberately accepted.

## 7. First manual run

Before scheduling anything, run it once by hand and watch it work:

> run the review-handler agent for `<slug>`

This fetches, classifies, drafts, and routes every new review, and drafts social content for any 5-star ones. Confirm the replies read right and the routing (auto-post / escalate / queue) matches expectations before trusting it unattended.

## 8. Go live and schedule

→ **[OPERATIONS.md "Scheduling"](OPERATIONS.md#scheduling-unattended-runs)** — installing the `launchd` job for the daily review-handler run, and (if Step 3 used Telegram) the persistent Telegram listener for interactive approve/reject/edit.

This runs locally via `launchd` on the machine holding this business's credentials/data — not a cloud routine, which can't see the gitignored `.env`/`reviews.db` it would need.

## 9. Ongoing operation

Nothing further to "set up" — day to day:

- **Interactive Telegram** (if configured): reply to an escalation to approve/reject/edit it, or send any other message for an on-demand summary. See [OPERATIONS.md "Interactive Telegram"](OPERATIONS.md#interactive-telegram-approverejectedit--daily--on-demand-summaries).
- **Daily summaries**: pushed automatically at the end of each scheduled run.
- **Social backlog** (if Facebook posting is enabled): new 5-star reviews draft and notify automatically as part of each run; posting them is still a deliberate human action (`tools/post_social.py`). For a backlog of *existing* reviews from before this business was onboarded, don't dump them all at once — pace it out (e.g. a handful per day) so the Page's feed doesn't look like a content dump.
- **Health checks**: re-run `tools/check_health.py --business <slug>` periodically, or whenever something seems off — it's the fastest way to find out which credential broke and exactly which command fixes it.
