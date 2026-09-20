"""Health-check logic shared between review-management's own
tools/check_health.py and the independent MCP services (review-mcp,
social-mcp, notification-mcp) that took over the actions these checks
protect. Extracted rather than duplicated, per platform-dev-agent's
extract-before-duplicate rule - review-management's CLI keeps using these
exact functions so there's still only one implementation of "is the
Google OAuth token still valid," not two that can quietly drift apart.

Each check takes a `config.Business` (or `conn`, for the ones that read
the review queue) and returns (level, message), where level is one of
OK/WARN/FAIL.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from lib import notifier, social_platforms, store

OK, WARN, FAIL = "OK", "WARN", "FAIL"
LEVEL_RANK = {OK: 0, WARN: 1, FAIL: 2}


def worst_level(levels) -> str:
    worst = OK
    for level in levels:
        if LEVEL_RANK[level] > LEVEL_RANK[worst]:
            worst = level
    return worst


def check_oauth(business) -> tuple:
    if business.google_client_mode != "live":
        return OK, "google_client_mode is not 'live' - skipping OAuth check"
    if not (business.google_oauth_client_id and business.google_oauth_client_secret and business.google_oauth_refresh_token):
        return FAIL, "google_client_mode is 'live' but OAuth credentials are missing"

    data = urllib.parse.urlencode(
        {
            "client_id": business.google_oauth_client_id,
            "client_secret": business.google_oauth_client_secret,
            "refresh_token": business.google_oauth_refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            json.loads(resp.read())
        return OK, "OAuth refresh token is valid"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        if exc.code == 400 and "invalid_grant" in detail:
            return FAIL, (
                "refresh token is invalid/expired (common cause: the OAuth consent screen is "
                "still in Testing status, where tokens expire after 7 days). Fix: "
                f"python3 tools/google_oauth_setup.py --business {business.slug}"
            )
        return FAIL, f"OAuth check failed: {exc.code} {detail}"
    except urllib.error.URLError as exc:
        return WARN, f"could not reach Google to verify (network issue?): {exc}"


def check_escalation_channel(business) -> tuple:
    configured = notifier.get_configured_notifiers(business)
    if not configured:
        return WARN, (
            "no notification channel configured - escalations only print to console, which "
            "nobody sees in an unattended/scheduled run. See docs/API_SETUP.md 'Escalation alerts'."
        )
    channels = ", ".join(type(n).__name__.replace("Notifier", "") for n in configured)
    return OK, f"configured: {channels}"


def check_facebook_posting(business) -> tuple:
    """Facebook is the one platform with real posting wired up. Round-
    trips the token (not just presence) the same way check_oauth() does
    for Google - a token from tools/meta_oauth_setup.py's Facebook Login
    for Business flow "defaults to never expire", but that's a default,
    not a guarantee, so this is still worth catching proactively rather
    than failing mid-post."""
    configured = business.social_platforms
    enabled = configured if configured is not None else social_platforms.available_platforms()
    if "facebook" not in enabled:
        return OK, "facebook not enabled for this business (business.json social_platforms)"
    if not (business.facebook_page_id and business.facebook_page_access_token):
        return WARN, "FACEBOOK_PAGE_ID/FACEBOOK_PAGE_ACCESS_TOKEN not set - Facebook posting will fail"

    url = f"https://graph.facebook.com/v25.0/me?fields=id,name&access_token={business.facebook_page_access_token}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            json.loads(resp.read())
        return OK, f"credentials valid for page {business.facebook_page_id}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return FAIL, (
            f"Facebook token invalid/expired ({exc.code} {detail}) - re-run: "
            f"python3 tools/meta_oauth_setup.py --business {business.slug}"
        )
    except urllib.error.URLError as exc:
        return WARN, f"could not reach Facebook to verify (network issue?): {exc}"


def check_queue(conn) -> tuple:
    rows = store.list_reviews(conn)
    pending = [r for r in rows if r["status"] in ("pending_review", "escalated")]
    escalated = [r for r in rows if r["status"] == "escalated"]
    if not pending:
        return OK, "queue is empty"
    oldest = min(pending, key=lambda r: r["created_at"])
    age = datetime.now(timezone.utc) - datetime.fromisoformat(oldest["created_at"])
    level = WARN if escalated or age.days >= 1 else OK
    return level, (
        f"{len(pending)} awaiting a human decision ({len(escalated)} escalated), "
        f"oldest queued {age.days}d {age.seconds // 3600}h ago (review id {oldest['id']})"
    )
