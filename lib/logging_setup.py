"""Structured, persistent logging - stdlib logging module only, no new
dependency. Each business gets its own rotating log file under
businesses/<slug>/logs/app.log, consistent with this project's
per-business isolation (own DB, own secrets, own logs).

This exists because console output (print()) is lost the moment a
session ends or output isn't captured somewhere - the things that matter
(a reply was posted, an escalation notification succeeded or failed, how
many reviews a fetch found) need a durable record regardless of whether
the tool was run interactively, via the review-handler agent, or by the
launchd schedule (see docs/OPERATIONS.md).

Existing print() calls are left in place for immediate console feedback
during interactive use - get_logger() calls are additive, not a
replacement, so nothing about the interactive experience changes.
"""
import logging
from logging.handlers import RotatingFileHandler

from lib import config

_configured_businesses = set()


def get_logger(name: str) -> logging.Logger:
    """Logger for the currently active business (config.active()),
    resolved fresh on every call so it's always correct even if the active
    business changed since the last call (e.g. a test switching contexts)."""
    business = config.active()
    logger_name = f"review_management.{business.slug}.{name}"
    logger = logging.getLogger(logger_name)

    if business.slug not in _configured_businesses:
        log_dir = business.dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        business_root = logging.getLogger(f"review_management.{business.slug}")
        handler = RotatingFileHandler(log_dir / "app.log", maxBytes=5_000_000, backupCount=5)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        business_root.addHandler(handler)
        business_root.setLevel(logging.INFO)
        business_root.propagate = False
        _configured_businesses.add(business.slug)

    return logger
