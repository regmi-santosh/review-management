"""Milestone detection: total review-count thresholds (on by default), and
two opt-in types that stay a no-op until a business sets the relevant
business.json field - consecutive-5-star-review streaks
(rating_streak_milestones) and founding-date anniversaries (founded_date).
See docs/ARCHITECTURE.md "Milestone layer".

Every type is derived fresh from stored data each call (a chronological
scan of the reviews table, or founded_date vs today) rather than a
separately maintained counter that could drift out of sync - the same
"derive, don't track" approach the rest of this codebase uses for review
counts. A milestone is recorded (store.record_milestone) the first time
it's crossed and never reconsidered again; the UNIQUE(type, threshold)
constraint on the `milestones` table is what makes repeated calls safe and
idempotent, not any check-then-record logic here.
"""
import sqlite3
from datetime import date
from typing import Optional

from lib import config, store


def _check_review_count(conn: sqlite3.Connection, business: config.Business) -> list:
    thresholds = sorted(business.milestone_thresholds)
    if not thresholds:
        return []
    recorded = store.get_recorded_milestone_thresholds(conn, "review_count")
    crossed = []
    count = 0
    for review in store.list_reviews_chronological(conn):
        count += 1
        for threshold in thresholds:
            if threshold not in recorded and count == threshold:
                milestone_id = store.record_milestone(conn, "review_count", threshold, review["id"])
                recorded.add(threshold)
                crossed.append(
                    {
                        "milestone_id": milestone_id,
                        "type": "review_count",
                        "threshold": threshold,
                        "reached_review_id": review["id"],
                    }
                )
    return crossed


def _check_rating_streak(conn: sqlite3.Connection, business: config.Business) -> list:
    thresholds = sorted(business.rating_streak_milestones)
    if not thresholds:
        return []
    recorded = store.get_recorded_milestone_thresholds(conn, "rating_streak")
    crossed = []
    streak = 0
    streak_review_id: Optional[int] = None
    for review in store.list_reviews_chronological(conn):
        if review["rating"] == 5:
            streak += 1
            streak_review_id = review["id"]
        else:
            streak = 0
            streak_review_id = None
        for threshold in thresholds:
            if threshold not in recorded and streak == threshold:
                milestone_id = store.record_milestone(conn, "rating_streak", threshold, streak_review_id)
                recorded.add(threshold)
                crossed.append(
                    {
                        "milestone_id": milestone_id,
                        "type": "rating_streak",
                        "threshold": threshold,
                        "reached_review_id": streak_review_id,
                    }
                )
    return crossed


def _check_anniversary(conn: sqlite3.Connection, business: config.Business) -> list:
    if not business.founded_date:
        return []
    founded = date.fromisoformat(business.founded_date)
    years_elapsed = (date.today() - founded).days // 365
    if years_elapsed < 1:
        return []
    recorded = store.get_recorded_milestone_thresholds(conn, "anniversary")
    crossed = []
    for year in range(1, years_elapsed + 1):
        if year not in recorded:
            milestone_id = store.record_milestone(conn, "anniversary", year, None)
            crossed.append(
                {
                    "milestone_id": milestone_id,
                    "type": "anniversary",
                    "threshold": year,
                    "reached_review_id": None,
                }
            )
    return crossed


def check_milestones(conn: sqlite3.Connection, business: config.Business) -> list:
    """Run all three milestone checks and return every newly-crossed one
    (usually empty). Safe to call every run regardless of whether that
    run's fetch found any new reviews - see docs/ARCHITECTURE.md "Milestone
    layer" for why (an anniversary can land on a day with none)."""
    crossed = []
    crossed += _check_review_count(conn, business)
    crossed += _check_rating_streak(conn, business)
    crossed += _check_anniversary(conn, business)
    return crossed
