#!/usr/bin/env python3
"""One-time-per-business helper to connect a Facebook Page (and its linked
Instagram Business account, if any) via Facebook Login for Business - see
docs/API_SETUP.md "Meta platforms (Facebook, Instagram)" and
docs/ARCHITECTURE.md "Social platform layer".

Mirrors tools/google_oauth_setup.py's shape: opens a browser for the
business's own Facebook admin to authorize, catches the redirect on a local
server, and writes credentials straight into that business's own
businesses/<slug>/.env. Unlike a plain personal-user OAuth token, the
resulting business-integration token is scoped to the authorizing admin's
business and, per Meta's docs, defaults to never expire for server-to-server
use - it doesn't degrade if the admin's personal login changes, and doesn't
require the business to have its own Meta Business Manager setup.

The Meta app + Facebook Login for Business configuration (config_id) are
platform-level, shared across every business - see docs/API_SETUP.md for
the one-time App Dashboard setup this depends on (META_APP_ID/
META_APP_SECRET/META_CONFIG_ID in the top-level .env).

Usage:
  python3 tools/meta_oauth_setup.py --business <slug>
  python3 tools/meta_oauth_setup.py --business <slug> --page-name "Some Page"
    (non-interactive selection when the authorizing admin manages several Pages)
"""
import argparse
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config
from lib.cli import add_business_arg, apply_business_arg

API_VERSION = "v25.0"
AUTH_URL = f"https://www.facebook.com/{API_VERSION}/dialog/oauth"
TOKEN_URL = f"https://graph.facebook.com/{API_VERSION}/oauth/access_token"
GRAPH_URL = f"https://graph.facebook.com/{API_VERSION}"
PORT = 8766
REDIRECT_URI = f"http://localhost:{PORT}/"

_received = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _received["code"] = params["code"][0]
            _received["state"] = params.get("state", [None])[0]
            body = b"<html><body>Authorized - you can close this tab and return to the terminal.</body></html>"
        else:
            _received["error"] = params.get("error_description", params.get("error", ["unknown_error"]))[0]
            body = b"<html><body>Authorization failed - see the terminal.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args) -> None:
        pass


def _get(url: str, params: dict) -> dict:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(full_url, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"error: HTTP {exc.code} from {url}: {detail}", file=sys.stderr)
        sys.exit(1)


def _select_page(pages: list, page_name: str, page_id: str):
    if page_id:
        match = next((p for p in pages if p["id"] == page_id), None)
        if not match:
            print(f"error: no page with id {page_id} in this authorization", file=sys.stderr)
            sys.exit(1)
        return match
    if page_name:
        match = next((p for p in pages if p["name"] == page_name), None)
        if not match:
            print(f"error: no page named {page_name!r} in this authorization", file=sys.stderr)
            sys.exit(1)
        return match
    if len(pages) == 1:
        return pages[0]
    print("Multiple pages authorized - pick one:")
    for i, p in enumerate(pages, 1):
        print(f"  {i}. {p['name']} (id {p['id']})")
    choice = input("Enter a number: ").strip()
    try:
        return pages[int(choice) - 1]
    except (ValueError, IndexError):
        print("error: invalid choice", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--page-name", default=None, help="Non-interactive page selection by name")
    parser.add_argument("--page-id", default=None, help="Non-interactive page selection by id")
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    app_id = business.meta_app_id
    app_secret = business.meta_app_secret
    config_id = business.meta_config_id
    if not (app_id and app_secret and config_id):
        print(
            "error: META_APP_ID / META_APP_SECRET / META_CONFIG_ID not set - these are "
            "platform-level, one-time setup in the top-level .env. See docs/API_SETUP.md "
            "'Meta platforms (Facebook, Instagram)'.",
            file=sys.stderr,
        )
        sys.exit(1)

    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id": app_id,
        "redirect_uri": REDIRECT_URI,
        "config_id": config_id,
        "state": state,
        "response_type": "code",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    print(f"Authorizing for business '{business.slug}'.")
    print(f"Opening your browser to authorize. If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", PORT), _Handler)
    print(f"Waiting for authorization on {REDIRECT_URI} ...")
    while "code" not in _received and "error" not in _received:
        server.handle_request()

    if "error" in _received:
        print(f"error: authorization failed: {_received['error']}", file=sys.stderr)
        sys.exit(1)
    if _received.get("state") != state:
        print("error: state mismatch on redirect - possible CSRF, aborting", file=sys.stderr)
        sys.exit(1)

    token_response = _get(
        TOKEN_URL,
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": REDIRECT_URI,
            "code": _received["code"],
        },
    )
    access_token = token_response.get("access_token")
    if not access_token:
        print(f"error: no access_token in response: {token_response}", file=sys.stderr)
        sys.exit(1)

    # Per Meta's docs this token is already scoped to the assets the admin
    # granted - /me/accounts is the same call used for a plain personal
    # token to list managed Pages, and should list this authorization's
    # Page(s) too. Confirm this assumption the first time this is run for
    # real; if it instead returns nothing, the token itself may already be
    # a single Page's token (see docs/API_SETUP.md's notes on this).
    accounts = _get(f"{GRAPH_URL}/me/accounts", {"access_token": access_token})
    pages = accounts.get("data", [])
    if not pages:
        print(
            "error: GET /me/accounts returned no pages for this token. If you know this "
            "authorization was for exactly one Page, the token itself may already be "
            "Page-scoped - see docs/API_SETUP.md for how to confirm this by hand.",
            file=sys.stderr,
        )
        sys.exit(1)

    page = _select_page(pages, args.page_name, args.page_id)
    page_token = page.get("access_token", access_token)

    business.save_secret("FACEBOOK_PAGE_ID", page["id"])
    business.save_secret("FACEBOOK_PAGE_ACCESS_TOKEN", page_token)
    print(f"Saved Facebook Page credentials for '{page['name']}' (id {page['id']}).")

    ig = _get(f"{GRAPH_URL}/{page['id']}", {"fields": "instagram_business_account", "access_token": page_token})
    ig_account = ig.get("instagram_business_account", {}).get("id")
    if ig_account:
        business.save_secret("INSTAGRAM_BUSINESS_ACCOUNT_ID", ig_account)
        print(f"Also saved linked Instagram Business Account id {ig_account} (not used by anything yet).")

    print(f"\nSuccess. Saved to businesses/{business.slug}/.env.")
    print(f"Next: python3 tools/check_health.py --business {business.slug}")


if __name__ == "__main__":
    main()
