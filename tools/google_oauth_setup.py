#!/usr/bin/env python3
"""One-time helper to obtain a Google OAuth refresh token for the Business
Profile API, once Google has approved API access for your Cloud project
(see docs/API_SETUP.md). Stdlib only — opens a browser for you to sign in
as the Google account that manages the business listing, then writes the
refresh token straight into that business's own businesses/<slug>/.env
(each business's listing is normally owned by a different Google account,
so credentials are never shared across businesses).

Usage:
  python3 tools/google_oauth_setup.py [--business <slug>]
    (reads GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET from that
    business's .env, or the top-level .env as a fallback)

  python3 tools/google_oauth_setup.py --client-id XXX --client-secret YYY
    (overrides/provides them directly; still saved into the business's .env)
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config
from lib.cli import add_business_arg, apply_business_arg

SCOPE = "https://www.googleapis.com/auth/business.manage"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}"

_received = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _received["code"] = params["code"][0]
            body = b"<html><body>Authorized - you can close this tab and return to the terminal.</body></html>"
        else:
            _received["error"] = params.get("error", ["unknown_error"])[0]
            body = b"<html><body>Authorization failed - see the terminal.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--client-secret", default=None)
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    client_id = args.client_id or business.google_oauth_client_id
    client_secret = args.client_secret or business.google_oauth_client_secret

    if not client_id or not client_secret:
        print(
            f"error: no client id/secret given and none found for business "
            f"'{business.slug}' (businesses/{business.slug}/.env or top-level .env: "
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET). "
            "Pass --client-id/--client-secret or set them first.",
            file=sys.stderr,
        )
        sys.exit(1)

    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
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

    data = urllib.parse.urlencode(
        {
            "code": _received["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read())

    if "refresh_token" not in tokens:
        print(
            "error: no refresh_token in the response - this Google account may "
            "have already granted consent before. Revoke it at "
            "https://myaccount.google.com/permissions and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    business.save_secret("GOOGLE_OAUTH_CLIENT_ID", client_id)
    business.save_secret("GOOGLE_OAUTH_CLIENT_SECRET", client_secret)
    business.save_secret("GOOGLE_OAUTH_REFRESH_TOKEN", tokens["refresh_token"])
    print(f"\nSuccess. Saved OAuth credentials to businesses/{business.slug}/.env.")
    print(f"Next: python3 tools/google_list_locations.py --business {business.slug}")


if __name__ == "__main__":
    main()
