# Google Business Profile API setup — as actually performed

This is the real, battle-tested sequence we followed to go from "API access approved" to "362 reviews fetched, 31 replied to live" for Brows & Threading City, including every gotcha we actually hit and how we fixed it. Follow this over any generic Google doc — the theory in Google's own guides is right, but the Console UI and gating behavior have specifics that aren't obvious until you hit them.

There is **no LLM/model API key anywhere in this system**. The review-handler agent runs as the model already powering your Claude Code / VS Code session — everything below is Google service credentials only.

## Prerequisites (before touching Cloud Console)

1. The business listing must be claimed and verified in [Google Business Profile Manager](https://business.google.com/) by whoever owns it.
2. You must separately request Business Profile API access via the [access request form](https://developers.google.com/my-business/content/prereqs), describing the use case (reading/replying to reviews on your own verified listing). **This is a manual review — budget days to weeks and don't block other work on it.** Everything below assumes this step is already approved.

## Step 1 — Enable the right APIs in the Cloud project

Go to **APIs & Services → Library** in the project tied to your approved access, and enable:

- **Google My Business API** — this is the one that actually backs the reviews endpoints (list + reply) used by this system. It's normally hidden/blocked for new projects; your approved access request is what unlocks it here.
- **My Business Business Information API**
- **My Business Account Management API** (needed to discover account/location IDs in Step 5)

If "Google My Business API" isn't enable-able yet, that's a sign the approval hasn't fully propagated to this specific project — double check against the project number Google actually approved.

## Step 2 — OAuth consent screen ("Google Auth Platform")

Google has reorganized this into tabs (Overview / **Branding** / **Audience** / **Clients** / **Data Access**) rather than one wizard. Since this is an internal tool with no public users, most branding fields are just noise:

| Branding tab field | What to put |
|---|---|
| App name | Anything identifying — only test users ever see it. |
| User support email | Any email you control. |
| App logo | **Leave empty** — uploading one triggers a verification requirement you don't need. |
| Homepage / privacy policy / terms of service links | **Leave empty.** |
| Authorized domains | **Leave completely empty.** There's no domain involved at all — our OAuth client is a Desktop app type using `http://localhost:8765` as the redirect, so there's nothing valid to register here. (If you type something like a public email provider's domain, Google will reject it with "must be a top private domain" — that's expected; just leave the field blank.) |
| Developer contact email | Required — any email you control. |

**Data Access tab** — this is what used to be called "Scopes," and it's a separate tab from Branding:
1. Click **Add or remove scopes**.
2. `https://www.googleapis.com/auth/business.manage` **will not show up in the searchable/curated list** — it's a restricted scope tied to an API most projects don't have. Scroll to the manual-entry box at the bottom of the dialog and paste it there directly instead.
3. Save.

**Audience tab** — while publishing status is "Testing" (the default, and fine for this use case), Google blocks every Google account except explicitly added ones:
1. Add the Google account you'll actually sign in with (the one that manages the business listing) under **Test users**.
2. Skip this and you'll get `Error 403: access_denied — Review Management System has not completed the Google verification process` when you try to authorize.

**Known limitation to plan around**: while in Testing status, refresh tokens for sensitive scopes like `business.manage` **expire after 7 days**. Moving to "In production" requires Google's OAuth app verification (a separate review, similar in spirit to the API access approval). For now we're staying in Testing and just re-running Step 4 periodically; revisit this if the system needs to run unattended for longer stretches. Run `python3 tools/check_health.py --business <slug>` periodically — it actually attempts a token refresh and tells you exactly when this has expired (rather than finding out the next time `fetch_reviews.py` mysteriously fails), and exactly which command to re-run.

## Step 3 — Create the OAuth client

**APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app.**

Desktop app, not Web application — this matters. `tools/google_oauth_setup.py` runs entirely on your machine: it opens your browser and catches the redirect on `http://localhost:<port>` via a throwaway local HTTP server. There's no domain, no backend, and no way to keep the client secret confidential from whoever runs the script — that's exactly the "installed app" pattern ([RFC 8252](https://developers.google.com/identity/protocols/oauth2/native-app)) Desktop app credentials exist for. Google allows any loopback port for this client type without pre-registering it; a Web application client would instead force you to pre-register an exact redirect URI and fight assumptions (domain verification, stricter consent requirements) that don't fit a local script. The client type only affects this authorization step — it has no bearing on the actual API calls made afterward.

Note the Client ID and Client Secret — you'll pass them to the script in the next step (or put them directly in `businesses/<slug>/.env` first, same `KEY=value` format as the top-level `.env`).

**Important for more than one business**: these credentials are scoped to whichever `--business <slug>` you run the next two steps with. A second business's listing is normally owned by a completely different Google account, so its credentials go in *its own* `businesses/<other-slug>/.env`, never the shared top-level one.

## Step 4 — Get a refresh token

```bash
python3 tools/google_oauth_setup.py --business <slug> --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

(`--business` defaults to `BUSINESS_SLUG`/the only business directory if omitted; `--client-id`/`--client-secret` default to whatever's already in that business's `.env` if omitted.)

This opens your browser, has you sign in as the test-user account from Step 2, and **writes the credentials straight into `businesses/<slug>/.env`** — nothing to copy-paste.

If you get `Error 403: access_denied`, you missed the Audience → Test users step above.

## Step 5 — Find your account ID and location ID

```bash
python3 tools/google_list_locations.py --business <slug>
```

Lists every account and location visible to that Google login, e.g.:

```
Account: accounts/112566968304890997185  (Brows And Threading City)
  Location: locations/6553677151317499236  (Brows & Threading City)
```

Put the numeric IDs into `businesses/<slug>/business.json`:

```json
{
  "google_account_id": "112566968304890997185",
  "google_location_id": "6553677151317499236"
}
```

If the tool lists more than one location for this account (a business with several physical locations), use `"google_location_ids": ["...", "..."]` instead of the singular field — every review gets tagged with which location it came from, and replies route back to the matching one.

## Step 6 — Go live

Set `"google_client_mode": "live"` in `businesses/<slug>/business.json` (or `GOOGLE_CLIENT_MODE=live` in the top-level `.env` if this is the only/default business). `tools/fetch_reviews.py` and `tools/post_reply.py` now hit the real API for that business — no other code changes needed.

**What we learned doing this for real, encoded as safety features in `lib/google_client.py` and `lib/store.py` — don't remove these if you're touching that code:**

- **Pagination.** The reviews endpoint pages results (`nextPageToken`). Our first live fetch without pagination silently returned only 50 of 362 actual reviews. `LiveGoogleBusinessProfileClient.fetch_reviews()` now loops until `nextPageToken` is absent.
- **Existing-reply protection.** Of those 362 reviews, 331 already had an owner reply posted manually on Google, before this system ever ran. The reviews endpoint reports this via a `reviewReply` field on each review. If a review with an existing reply is treated as brand-new, the agent could confidently draft and auto-post a *replacement* reply — silently overwriting the real one via the API's `PUT .../reply` (which replaces, not appends). `insert_review()` now checks for `existing_reply` and immediately records that review as already `posted`, with the real reply preserved in `posted_reply`, so it's never surfaced to the agent as actionable.

**Note on API stability**: Google has reorganized these APIs more than once (the old monolithic v4 "My Business API" was split into separate Account Management / Business Information / etc. APIs in 2022). As of this writing (September 2026) the reviews list/reply endpoints still live under `mybusiness.googleapis.com/v4`, confirmed against Google's own current docs and by actually calling them. If `fetch_reviews.py`/`post_reply.py` start 404ing, check [the current reference docs](https://developers.google.com/my-business/reference/rest) — the endpoints in `LiveGoogleBusinessProfileClient` may need updating to whatever Google calls them by then.

## Slack webhook (optional, for escalation alerts)

Without this, escalations just print to the console. To get a real alert instead:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Pick your workspace, then under **Incoming Webhooks**, toggle it on and **Add New Webhook to Workspace**, choosing the channel to post to.
3. Copy the webhook URL into `.env` (`SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`) for a global default, or into a specific business's `business.json` as `"slack_webhook_url": "..."` if that business's escalations should go to a different Slack workspace/channel than the default.

`lib/notifier.py` posts there instead of logging to console the next time a review is escalated.
