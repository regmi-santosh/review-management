"""Test utilities for consumers of this package, not just this repo's own
test suite - notification-mcp (still a facade over this package's data;
see its own ARCHITECTURE.md) needs to point lib.config at a temporary
business directory the same way review-management's own tests do, and a
git-installed (non-editable) dependency only ships what
[tool.hatch.build.targets.wheel] packages declares - "tests/" isn't part
of that, "lib/" is. Moved here (was tests/helpers.py) so it's a real,
shipped part of the package instead of something only reachable via a
local editable install's full source tree. tests/helpers.py re-exports
this unchanged for review-management's own test suite.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from lib import config


@contextmanager
def temp_businesses_root():
    """Points lib.config at an empty temp businesses/ dir. Caller creates
    business subdirectories (see make_business_dir) and switches to them
    with config.use_business(slug)."""
    tmp_root = Path(tempfile.mkdtemp())
    orig_dir = config.BUSINESSES_DIR
    orig_slug = config._active_slug
    orig_active = config._active
    try:
        config.BUSINESSES_DIR = tmp_root
        yield tmp_root
    finally:
        config.BUSINESSES_DIR = orig_dir
        config._active_slug = orig_slug
        config._active = orig_active
        shutil.rmtree(tmp_root, ignore_errors=True)


def make_business_dir(
    root: Path, slug: str, business_facts: dict | None = None, seed_reviews: list | None = None
) -> Path:
    biz_dir = root / slug
    biz_dir.mkdir(parents=True, exist_ok=True)
    if business_facts is not None:
        (biz_dir / "business.json").write_text(json.dumps(business_facts))
    if seed_reviews is not None:
        (biz_dir / "seed_reviews.json").write_text(json.dumps(seed_reviews))
    return biz_dir


@contextmanager
def temp_business(slug: str = "test-biz", business_facts: dict | None = None, seed_reviews: list | None = None):
    """Convenience wrapper for the common single-business case. Yields the
    active config.Business."""
    with temp_businesses_root() as root:
        make_business_dir(root, slug, business_facts, seed_reviews)
        config.use_business(slug)
        yield config.active()
