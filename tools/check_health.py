#!/usr/bin/env python3
"""Health check for one business: verifies its Google OAuth credentials
still actually work (catches Testing-mode's 7-day refresh token expiry
before it silently breaks fetch/post), checks secrets-file permissions,
confirms an escalation channel (Telegram/Slack) is actually configured,
confirms the configured agentic harness (see docs/ARCHITECTURE.md) has a
matching adapter, reports which social platforms are enabled for social
drafts, reports which milestone types are configured, and reports the
review queue and last run.

Exit code: 0 if everything's OK, 1 if there are warnings, 2 if anything failed.

Usage: python3 tools/check_health.py [--business <slug>]
"""
import argparse
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from lib import config, social_image, social_platforms, store
from lib.cli import add_business_arg, apply_business_arg
from lib.health_checks import (
    FAIL,
    OK,
    WARN,
    check_escalation_channel,
    check_facebook_posting,
    check_oauth,
    check_queue,
    worst_level,
)


def check_secrets_permissions(business: config.Business) -> tuple:
    if not business.env_path.exists():
        return OK, "no businesses/<slug>/.env yet (mock mode, or using top-level .env)"
    mode = stat.S_IMODE(business.env_path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        business.env_path.chmod(0o600)
        return WARN, f"businesses/{business.slug}/.env had group/other-readable permissions - fixed to 600"
    return OK, "businesses/<slug>/.env permissions are 600"


def check_agent_harness() -> tuple:
    harness = config.agent_harness()
    adapter = REPO_DIR / "scripts" / "harnesses" / f"{harness}.sh"
    if not adapter.exists():
        return FAIL, (
            f"AGENT_HARNESS={harness} but no adapter at scripts/harnesses/{harness}.sh - "
            "the next unattended run (scripts/run_review_handler.sh) will fail before it even "
            "starts. See docs/ARCHITECTURE.md 'Harness layer'."
        )
    return OK, f"{harness} (scripts/harnesses/{harness}.sh)"


def check_social_platforms(business: config.Business) -> tuple:
    configured = business.social_platforms
    registered = social_platforms.available_platforms()
    enabled = configured if configured is not None else registered
    if not enabled:
        return OK, "none enabled (business.json social_platforms is an empty list)"
    unknown = [p for p in enabled if p not in registered]
    if unknown:
        return WARN, (
            f"business.json social_platforms has unknown name(s) {unknown} - "
            f"no adapter for them in lib/social_platforms.py, so they're skipped"
        )
    if not social_image.is_available():
        return WARN, (
            "Pillow not installed (pip install -r requirements.txt) - text captions still "
            "draft fine, but quote-card images (lib/social_image.py) won't generate"
        )
    return OK, f"enabled: {', '.join(enabled)} (draft-only - see docs/ARCHITECTURE.md)"


def check_milestones(business: config.Business) -> tuple:
    """Purely informational (always OK) - just surfaces what's configured
    so it's obvious at onboarding-verification time which milestone types
    are live for this business, per docs/ARCHITECTURE.md "Milestone
    layer": review-count is always on, streak/anniversary are opt-in and
    silently do nothing until their business.json key is set."""
    parts = [f"review-count thresholds {business.milestone_thresholds}"]
    parts.append(
        f"rating-streak {business.rating_streak_milestones}"
        if business.rating_streak_milestones
        else "rating-streak: not configured (opt-in)"
    )
    parts.append(
        f"anniversary: founded {business.founded_date}"
        if business.founded_date
        else "anniversary: founded_date not set (opt-in)"
    )
    return OK, "; ".join(parts)


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
        ("Agent harness", check_agent_harness()),
        ("Social platforms", check_social_platforms(business)),
        ("Facebook posting", check_facebook_posting(business)),
        ("Milestones", check_milestones(business)),
        ("Review queue", check_queue(conn)),
        ("Last run", check_last_run(conn)),
    ]

    for name, (level, message) in checks:
        print(f"[{level}] {name}: {message}")

    sys.exit({OK: 0, WARN: 1, FAIL: 2}[worst_level(level for _, (level, _) in checks)])


if __name__ == "__main__":
    main()
