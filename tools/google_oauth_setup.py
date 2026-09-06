#!/usr/bin/env python3
"""One-time helper to obtain a Google OAuth refresh token for the Business
Profile API, once Google has approved API access for your Cloud project
(see docs/API_SETUP.md). Stdlib only — opens a browser for you to sign in
as the Google account that manages the business listing, then writes the
refresh token straight into .env.

Usage:
  python3 tools/google_oauth_setup.py
    (reads GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET from .env)

  python3 tools/google_oauth_setup.py --client-id XXX --client-secret YYY
    (overrides/provides them directly; also saved into .env)
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config

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


def _save_to_env(values: dict) -> None:
    """Set or replace KEY=value lines in .env, preserving everything else."""
    lines = config.ENV_PATH.read_text().splitlines() if config.ENV_PATH.exists() else []
    remaining = dict(values)
    for i, line in enumerate(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            lines[i] = f"{key}={remaining.pop(key)}"
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
    config.ENV_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", default=config.GOOGLE_OAUTH_CLIENT_ID)
    parser.add_argument("--client-secret", default=config.GOOGLE_OAUTH_CLIENT_SECRET)
    args = parser.parse_args()

    if not args.client_id or not args.client_secret:
        print(
            "error: no client id/secret given and none found in .env "
            "(GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET). "
            "Pass --client-id/--client-secret or set them in .env first.",
            file=sys.stderr,
        )
        sys.exit(1)

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
            "error: no refresh_token in the response - this Google account may "
            "have already granted consent before. Revoke it at "
            "https://myaccount.google.com/permissions and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    _save_to_env(
        {
            "GOOGLE_OAUTH_CLIENT_ID": args.client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": args.client_secret,
            "GOOGLE_OAUTH_REFRESH_TOKEN": tokens["refresh_token"],
        }
    )
    print("\nSuccess. Saved GOOGLE_OAUTH_REFRESH_TOKEN (and client id/secret) to .env.")
    print("Next: python3 tools/google_list_locations.py")


if __name__ == "__main__":
    main()
