"""Resolves the active business and its settings, stdlib only.

Two layers of config:
  - Top-level .env: cross-cutting defaults (which business is active, and
    fallback values any business can inherit). Never an LLM/model API key —
    the agent runs as the model already powering this Claude Code session,
    not via a separate API call.
  - businesses/<slug>/business.json + businesses/<slug>/.env: everything
    specific to one business — structured facts (name, Google location IDs),
    that business's own Google OAuth credentials (a second client's listing
    is normally owned by a completely different Google account, so these
    can't be shared globally), and optional per-business overrides
    (confidence_threshold, slack_webhook_url). Falls back to the top-level
    .env when a business doesn't set its own.

Call `active()` to get the current business's resolved settings; tools that
take a --business flag call `use_business(slug)` first to switch it.
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
BUSINESSES_DIR = ROOT / "businesses"


def _parse_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _write_env(path: Path, key: str, value: str) -> None:
    """Set or replace KEY=value in an env file, preserving everything else."""
    lines = path.read_text().splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) == key:
            lines[i] = f"{key}={value}"
            path.write_text("\n".join(lines) + "\n")
            return
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


_global_env = _parse_env(ENV_PATH)
for _k, _v in _global_env.items():
    os.environ.setdefault(_k, _v)


def _global_get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _default_business_slug() -> str:
    if BUSINESSES_DIR.is_dir():
        subdirs = sorted(p.name for p in BUSINESSES_DIR.iterdir() if p.is_dir())
        if len(subdirs) == 1:
            return subdirs[0]
    return "brows-and-threading-city"


class Business:
    """Resolved settings for one businesses/<slug>/ directory."""

    def __init__(self, slug: str):
        self.slug = slug
        self.dir = BUSINESSES_DIR / slug
        self.profile_path = self.dir / "profile.md"
        self.seed_reviews_path = self.dir / "seed_reviews.json"
        self.db_path = self.dir / "reviews.db"
        self.env_path = self.dir / ".env"

        business_json_path = self.dir / "business.json"
        self.facts = (
            json.loads(business_json_path.read_text()) if business_json_path.exists() else {}
        )
        self._secrets = _parse_env(self.env_path)

        self.name = self.facts.get("name", slug)
        self.maps_url = self.facts.get("maps_url", "")
        self.google_account_id = self.facts.get("google_account_id", "")
        self.google_location_id = self.facts.get("google_location_id", "")

    def _secret(self, key: str) -> str:
        # Business's own .env wins; falls back to the top-level .env / process env.
        return self._secrets.get(key) or _global_get(key, "")

    @property
    def google_oauth_client_id(self) -> str:
        return self._secret("GOOGLE_OAUTH_CLIENT_ID")

    @property
    def google_oauth_client_secret(self) -> str:
        return self._secret("GOOGLE_OAUTH_CLIENT_SECRET")

    @property
    def google_oauth_refresh_token(self) -> str:
        return self._secret("GOOGLE_OAUTH_REFRESH_TOKEN")

    @property
    def google_client_mode(self) -> str:
        return self.facts.get("google_client_mode") or _global_get("GOOGLE_CLIENT_MODE", "mock")

    @property
    def confidence_threshold(self) -> float:
        value = self.facts.get("confidence_threshold")
        return float(value) if value is not None else float(_global_get("CONFIDENCE_THRESHOLD", "0.85"))

    @property
    def slack_webhook_url(self) -> str:
        return self.facts.get("slack_webhook_url") or _global_get("SLACK_WEBHOOK_URL", "")

    def save_secret(self, key: str, value: str) -> None:
        """Set or replace KEY=value in this business's own .env file."""
        _write_env(self.env_path, key, value)
        self._secrets[key] = value


_active_slug = _global_get("BUSINESS_SLUG", _default_business_slug())
_active = Business(_active_slug)


def use_business(slug: str) -> None:
    """Switch the active business (e.g. from a tool's --business flag)."""
    global _active_slug, _active
    _active_slug = slug
    _active = Business(slug)


def active() -> Business:
    return _active
