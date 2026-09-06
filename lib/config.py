"""Loads .env (service credentials only — Slack webhook, Google OAuth — never
an LLM API key, since the agent runs as a model inside this VS Code / Claude
Code session, not via a separate API call) into os.environ, stdlib only.

Also resolves the active business: BUSINESS_SLUG in .env picks a directory
under businesses/<slug>/ holding that business's business.json (structured
facts: name, Google location IDs) and profile.md (free-text voice/context
the agent reads directly). This is what makes the system reusable across
businesses instead of hardcoding one — see README "Adding another business".
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
BUSINESSES_DIR = ROOT / "businesses"


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _default_business_slug() -> str:
    if BUSINESSES_DIR.is_dir():
        subdirs = sorted(p.name for p in BUSINESSES_DIR.iterdir() if p.is_dir())
        if len(subdirs) == 1:
            return subdirs[0]
    return "brows-and-threading-city"


CONFIDENCE_THRESHOLD = float(_get("CONFIDENCE_THRESHOLD", "0.85"))
GOOGLE_CLIENT_MODE = _get("GOOGLE_CLIENT_MODE", "mock")
SLACK_WEBHOOK_URL = _get("SLACK_WEBHOOK_URL", "")

GOOGLE_OAUTH_CLIENT_ID = _get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = _get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REFRESH_TOKEN = _get("GOOGLE_OAUTH_REFRESH_TOKEN", "")

BUSINESS_SLUG = _get("BUSINESS_SLUG", _default_business_slug())
BUSINESS_DIR = BUSINESSES_DIR / BUSINESS_SLUG
BUSINESS_PROFILE_PATH = BUSINESS_DIR / "profile.md"
SEED_REVIEWS_PATH = BUSINESS_DIR / "seed_reviews.json"

_business_json_path = BUSINESS_DIR / "business.json"
BUSINESS = json.loads(_business_json_path.read_text()) if _business_json_path.exists() else {}

BUSINESS_NAME = BUSINESS.get("name", BUSINESS_SLUG)
BUSINESS_MAPS_URL = BUSINESS.get("maps_url", "")
GOOGLE_BUSINESS_ACCOUNT_ID = BUSINESS.get("google_account_id", "")
GOOGLE_BUSINESS_LOCATION_ID = BUSINESS.get("google_location_id", "")
