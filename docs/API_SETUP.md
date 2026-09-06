# API & key setup guide

Everything here is optional until you want either (a) live Google data instead of the mock, or (b) Slack alerts instead of console-logged escalations. There is **no LLM/model API key anywhere in this system** — the review-handler agent runs as the model already powering your Claude Code / VS Code session, not via a separate API call.

## 1. Google Business Profile API (for live mode)

This is what lets `GOOGLE_CLIENT_MODE=live` actually read and reply to real reviews. It requires **manual approval from Google** per Cloud project — budget days to weeks for step 3, and don't block other work on it.

### Step 1 — Verify the listing

You (or whoever owns the listing) must have the business claimed and verified in [Google Business Profile Manager](https://business.google.com/). This is separate from and a prerequisite to API access.

### Step 2 — Create a Google Cloud project + OAuth client

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or reuse one).
2. **APIs & Services → OAuth consent screen**: configure it (External or Internal depending on your Google Workspace setup), add the scope `https://www.googleapis.com/auth/business.manage`.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**. Choose **Desktop app** as the application type (simplest for the local-redirect flow below). Note the **Client ID** and **Client Secret**.

### Step 3 — Request Business Profile API access

Google gates actual API traffic behind a manual review, separate from creating the OAuth client above. Submit the [Business Profile API access request form](https://developers.google.com/my-business/content/prereqs) with your Cloud project's number and a description of this use case (reading and replying to reviews for your own verified listing). You'll get an email when it's approved.

### Step 4 — Get a refresh token

Once approved, run the included helper (stdlib only, no install needed) from the repo root:

```bash
python3 tools/google_oauth_setup.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

This opens your browser, has you sign in as the Google account that manages the listing, and prints:

```
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REFRESH_TOKEN=...
```

Copy all three into `.env`.

### Step 5 — Find your account ID and location ID

```bash
python3 tools/google_list_locations.py
```

This lists every account and location visible to that Google login. Take the numeric ID after the last `/` in each `name` field and put them into `businesses/<slug>/business.json`:

```json
{
  "google_account_id": "123456789",
  "google_location_id": "987654321"
}
```

### Step 6 — Go live

Set `GOOGLE_CLIENT_MODE=live` in `.env`. `tools/fetch_reviews.py` and `tools/post_reply.py` now hit the real API instead of the mock — no other code changes needed.

**Note on API stability**: Google has reorganized these APIs (Account Management, Business Information, and the older v4 "My Business API" that reviews still live under) more than once. If `fetch_reviews.py`/`post_reply.py` 404 once you're live, check [the current reference docs](https://developers.google.com/my-business/reference/rest) — the reviews endpoints in `lib/google_client.py`'s `LiveGoogleBusinessProfileClient` may need updating to whatever Google calls them by then.

## 2. Slack webhook (optional, for escalation alerts)

Without this, escalations just print to the console. To get a real alert instead:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Pick your workspace, then under **Incoming Webhooks**, toggle it on and **Add New Webhook to Workspace**, choosing the channel to post to.
3. Copy the webhook URL (looks like `https://hooks.slack.com/services/T000/B000/XXXX`) into `.env`:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

That's it — `lib/notifier.py` posts there instead of logging to console the next time a review is escalated.
