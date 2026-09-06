"""Builds the text for a status summary - tallies from the last logged run
plus the current pending/escalated queue, with an optional highlights line.

Shared by the once-a-day scheduled push (tools/send_daily_summary.py) and
the on-demand reply the Telegram listener sends when someone messages the
bot without replying to a specific escalation (lib/telegram_bot.py) - one
function so the two can't drift into inconsistent formats.
"""
from typing import Optional

from lib import config, store


def build_summary_text(conn, business: config.Business, highlights: Optional[str] = None) -> str:
    run = store.last_run(conn)
    pending = store.list_reviews(conn, status="pending_review")
    escalated = store.list_reviews(conn, status="escalated")

    lines = [f"Summary for {business.name}"]
    if run:
        lines.append(
            f"Last run: {run['posted']} posted, {run['escalated']} escalated, "
            f"{run['queued']} queued (finished {run['finished_at']})"
        )
    else:
        lines.append("No runs logged yet.")
    lines.append(f"Currently open: {len(pending)} pending review, {len(escalated)} escalated")
    if highlights:
        lines.append(f"Highlights: {highlights}")
    return "\n".join(lines)
