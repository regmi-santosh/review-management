"""Test helpers: isolate lib.config's business resolution to a temp
directory so tests never touch real businesses/ data. stdlib only.
"""
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


def make_business_dir(root: Path, slug: str, business_facts: dict = None, seed_reviews: list = None) -> Path:
    biz_dir = root / slug
    biz_dir.mkdir(parents=True, exist_ok=True)
    if business_facts is not None:
        (biz_dir / "business.json").write_text(json.dumps(business_facts))
    if seed_reviews is not None:
        (biz_dir / "seed_reviews.json").write_text(json.dumps(seed_reviews))
    return biz_dir


@contextmanager
def temp_business(slug: str = "test-biz", business_facts: dict = None, seed_reviews: list = None):
    """Convenience wrapper for the common single-business case. Yields the
    active config.Business."""
    with temp_businesses_root() as root:
        make_business_dir(root, slug, business_facts, seed_reviews)
        config.use_business(slug)
        yield config.active()
