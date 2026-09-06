#!/usr/bin/env python3
"""After running google_oauth_setup.py, run this to list the Google Business
accounts and locations visible to that business's authorized account, so you
can fill google_account_id / google_location_id into businesses/<slug>/business.json.

Note: Google's Business Profile APIs have shifted across a few service
names over the years. If these endpoints 404 for you, check
https://developers.google.com/my-business/reference/rest for whichever
ones your approved API access actually covers.

Usage: python3 tools/google_list_locations.py [--business <slug>]
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config
from lib.cli import add_business_arg, apply_business_arg

ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL_TMPL = (
    "https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations"
    "?readMask=name,title"
)


def _access_token(business) -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": business.google_oauth_client_id,
            "client_secret": business.google_oauth_client_secret,
            "refresh_token": business.google_oauth_refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(
            f"error: GET {url} -> {exc.code} {exc.read().decode(errors='replace')}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    missing = [
        name
        for name, value in [
            ("GOOGLE_OAUTH_CLIENT_ID", business.google_oauth_client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", business.google_oauth_client_secret),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", business.google_oauth_refresh_token),
        ]
        if not value
    ]
    if missing:
        print(
            f"error: missing for business '{business.slug}': {', '.join(missing)} "
            f"(run tools/google_oauth_setup.py --business {business.slug} first)",
            file=sys.stderr,
        )
        sys.exit(1)

    token = _access_token(business)
    accounts = _get(ACCOUNTS_URL, token).get("accounts", [])
    if not accounts:
        print("No accounts visible to this Google login.")
        return

    for account in accounts:
        account_name = account["name"]  # e.g. "accounts/123456"
        print(f"Account: {account_name}  ({account.get('accountName', '')})")
        locations = _get(
            LOCATIONS_URL_TMPL.format(account_name=account_name), token
        ).get("locations", [])
        for loc in locations:
            print(f"  Location: {loc['name']}  ({loc.get('title', '')})")
        print()

    print(
        "Put the numeric IDs (the part after the last '/') into "
        f"businesses/{business.slug}/business.json as "
        '"google_account_id" and "google_location_id".'
    )


if __name__ == "__main__":
    main()
