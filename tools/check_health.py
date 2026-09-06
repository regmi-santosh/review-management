#!/usr/bin/env python3
"""Health check for one business: verifies its Google OAuth credentials
still actually work (catches Testing-mode's 7-day refresh token expiry
before it silently breaks fetch/post), checks secrets-file permissions,
confirms an escalation channel (Telegram/Slack) is actually configured,
and reports the review queue and last run.

Exit code: 0 if everything's OK, 1 if there are warnings, 2 if anything failed.

Usage: python3 tools/check_health.py [--business <slug>]
"""
import argparse
import json
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, notifier, store
from lib.cli import add_business_arg, apply_business_arg

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_LEVEL_RANK = {OK: 0, WARN: 1, FAIL: 2}


def check_secrets_permissions(business: config.Business) -> tuple:
    if not business.env_path.exists():
        return OK, "no businesses/<slug>/.env yet (mock mode, or using top-level .env)"
    mode = stat.S_IMODE(business.env_path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        business.env_path.chmod(0o600)
        return WARN, f"businesses/{business.slug}/.env had group/other-readable permissions - fixed to 600"
    return OK, "businesses/<slug>/.env permissions are 600"


def check_oauth(business: config.Business) -> tuple:
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


def check_escalation_channel(business: config.Business) -> tuple:
    configured = notifier.get_configured_notifiers(business)
    if not configured:
        return WARN, (
            "no notification channel configured - escalations only print to console, which "
            "nobody sees in an unattended/scheduled run. See docs/API_SETUP.md 'Escalation alerts'."
        )
    channels = ", ".join(type(n).__name__.replace("Notifier", "") for n in configured)
    return OK, f"configured: {channels}"


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


def check_last_run(conn) -> tuple:
    run = store.last_run(conn)
    if not run:
        return OK, "no runs logged yet"
    finished = datetime.fromisoformat(run["finished_at"])
    age = datetime.now(timezone.utc) - finished
    return OK, (
        f"{age.days}d {age.seconds // 3600}h ago - fetched {run['fetched']}, "
        f"processed {run['processed']} ({run['posted']} posted, {run['escalated']} escalated, "
        f"{run['queued']} queued)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    conn = store.connect()
    print(f"Health check: {business.name} ({business.slug})\n")

    checks = [
        ("Secrets file permissions", check_secrets_permissions(business)),
        ("Google OAuth", check_oauth(business)),
        ("Escalation channel", check_escalation_channel(business)),
        ("Review queue", check_queue(conn)),
        ("Last run", check_last_run(conn)),
    ]

    worst = OK
    for name, (level, message) in checks:
        print(f"[{level}] {name}: {message}")
        if _LEVEL_RANK[level] > _LEVEL_RANK[worst]:
            worst = level

    sys.exit({OK: 0, WARN: 1, FAIL: 2}[worst])


if __name__ == "__main__":
    main()
