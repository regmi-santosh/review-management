"""Google OAuth for the self-serve live demo (see docs/ARCHITECTURE.md "Demo
layer"). Deliberately separate from lib/google_client.py: that module
authenticates as an already-onboarded business using a long-lived refresh
token from businesses/<slug>/.env; this module runs the interactive
browser consent flow that *produces* a refresh token in the first place,
for a visitor authorizing their own Business Profile on the spot.

Uses a Web-application OAuth client (GOOGLE_WEB_OAUTH_CLIENT_ID/_SECRET in
the top-level .env) - a different client, and a different type, from the
Desktop-app client tools/google_oauth_setup.py uses. See .env.example.

Same two Business Profile endpoints tools/google_list_locations.py already
wraps for the CLI onboarding path; list_accounts_and_locations() here is
that same lookup refactored into a plain function so webapp/app.py's
location-picker route can call it directly instead of shelling out.
"""
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from lib.google_client import LiveGoogleBusinessProfileClient

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/business.manage"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL_TMPL = (
    "https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations"
    "?readMask=name,title"
)


class OAuthConfigError(RuntimeError):
    """Raised when the platform-level Web OAuth client isn't configured -
    distinct from a visitor-facing error, since this one means the demo
    server itself is misconfigured, not that anything the visitor did."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise OAuthConfigError(
            f"{name} is not set in the top-level .env - see .env.example "
            "\"Only needed to run webapp/\""
        )
    return value


def redirect_uri() -> str:
    base = _require_env("DEMO_PUBLIC_BASE_URL").rstrip("/")
    return f"{base}/demo/oauth/callback"


def new_state() -> str:
    """CSRF token for the OAuth round-trip - generated per demo session and
    checked back on the callback (see webapp/app.py)."""
    return secrets.token_urlsafe(24)


def build_authorization_url(state: str) -> str:
    params = {
        "client_id": _require_env("GOOGLE_WEB_OAUTH_CLIENT_ID"),
        "redirect_uri": redirect_uri(),
        "scope": SCOPE,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: Optional[str]


def exchange_code_for_tokens(code: str) -> TokenResponse:
    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": _require_env("GOOGLE_WEB_OAUTH_CLIENT_ID"),
            "client_secret": _require_env("GOOGLE_WEB_OAUTH_CLIENT_SECRET"),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(LiveGoogleBusinessProfileClient.TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Google token exchange failed: {exc.code} {detail}") from exc
    # refresh_token is only present the first time a given account
    # authorizes this client (or after prompt=consent forces re-issue,
    # which build_authorization_url() always requests) - absent on a
    # silent re-auth. We always pass prompt=consent above specifically so
    # this is never missing for a fresh demo session.
    return TokenResponse(access_token=body["access_token"], refresh_token=body.get("refresh_token"))


@dataclass
class BusinessLocation:
    account_id: str
    location_id: str
    title: str


def _get(url: str, access_token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"GET {url} failed: {exc.code} {detail}") from exc


def list_accounts_and_locations(access_token: str) -> List[BusinessLocation]:
    """Every Business Profile location visible to this access token, flattened
    across every account it can see. Bare numeric IDs (not the "accounts/123"
    / "locations/456" prefixed form the API returns) - business.json stores
    the bare form, matching what tools/google_list_locations.py's printed
    instructions already tell a human to paste in."""
    results: List[BusinessLocation] = []
    accounts = _get(ACCOUNTS_URL, access_token).get("accounts", [])
    for account in accounts:
        account_name = account["name"]  # "accounts/123456"
        account_id = account_name.split("/")[-1]
        locations = _get(LOCATIONS_URL_TMPL.format(account_name=account_name), access_token).get(
            "locations", []
        )
        for loc in locations:
            location_id = loc["name"].split("/")[-1]
            results.append(
                BusinessLocation(account_id=account_id, location_id=location_id, title=loc.get("title", ""))
            )
    return results
