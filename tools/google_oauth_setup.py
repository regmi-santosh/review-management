#!/usr/bin/env python3
"""One-time helper to obtain a Google OAuth refresh token for the Business
Profile API, once Google has approved API access for your Cloud project
(see docs/API_SETUP.md). Stdlib only — opens a browser for you to sign in
as the Google account that manages the business listing, then prints a
refresh token to put in .env.

Usage:
  python3 tools/google_oauth_setup.py --client-id XXX.apps.googleusercontent.com --client-secret YYY
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

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
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    auth_params = {
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
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
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read())

    if "refresh_token" not in tokens:
        print(
            "error: no refresh_token in the response — this Google account may "
            "have already granted consent before. Revoke it at "
            "https://myaccount.google.com/permissions and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nSuccess. Add this to your .env:\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID={args.client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={args.client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={tokens['refresh_token']}")


if __name__ == "__main__":
    main()
