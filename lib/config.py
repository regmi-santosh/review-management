"""Loads .env (service credentials only — Slack webhook, Google OAuth — never
an LLM API key, since the agent runs as a model inside this VS Code / Claude
Code session, not via a separate API call) into os.environ, stdlib only.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


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


CONFIDENCE_THRESHOLD = float(_get("CONFIDENCE_THRESHOLD", "0.85"))
GOOGLE_CLIENT_MODE = _get("GOOGLE_CLIENT_MODE", "mock")
SLACK_WEBHOOK_URL = _get("SLACK_WEBHOOK_URL", "")
BUSINESS_NAME = _get("BUSINESS_NAME", "Brows & Threading City")

GOOGLE_OAUTH_CLIENT_ID = _get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = _get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REFRESH_TOKEN = _get("GOOGLE_OAUTH_REFRESH_TOKEN", "")
GOOGLE_BUSINESS_ACCOUNT_ID = _get("GOOGLE_BUSINESS_ACCOUNT_ID", "")
GOOGLE_BUSINESS_LOCATION_ID = _get("GOOGLE_BUSINESS_LOCATION_ID", "")
