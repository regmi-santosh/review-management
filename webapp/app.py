#!/usr/bin/env python3
"""Self-serve live demo web app - see docs/ARCHITECTURE.md "Demo layer"
and the plan this was built from. A visitor authorizes their own Google
Business Profile, we pull a handful of their real reviews through the
exact same review-handler reasoning the product already uses, and show
them their own reviews answered. Nothing is ever posted anywhere; see
webapp/demo.py's docstring and prompt for the safety guardrails.

Local-machine + HTTPS tunnel deployment for now (see .env.example
DEMO_PUBLIC_BASE_URL) - not production hosting.

Usage:
  python3 webapp/app.py
"""
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, redirect, render_template, request, session

from lib import config  # noqa: E402  (triggers top-level .env -> os.environ, see lib/config.py)
from webapp import demo, google_oauth
from webapp.google_oauth import OAuthConfigError

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

LEADS_PATH = REPO_ROOT / "leads.jsonl"

# In-memory only, never a cookie - these hold a real Google credential for
# the few seconds between the OAuth callback and a multi-location visitor
# picking which location is theirs. Keyed by a random id handed to the
# browser in a hidden form field, not the credential itself. Entries are
# popped on use; _PENDING_TTL_SECONDS is a backstop for one that's never
# claimed (visitor closes the tab on the picker page).
_pending_auth: dict = {}
_pending_lock = threading.Lock()
_PENDING_TTL_SECONDS = 10 * 60


def _stash_pending_auth(refresh_token: str, locations) -> str:
    pending_id = secrets.token_urlsafe(24)
    with _pending_lock:
        _pending_auth[pending_id] = {
            "refresh_token": refresh_token,
            "locations": locations,
            "created": time.time(),
        }
        _prune_pending_locked()
    return pending_id


def _pop_pending_auth(pending_id: str):
    with _pending_lock:
        return _pending_auth.pop(pending_id, None)


def _prune_pending_locked() -> None:
    now = time.time()
    expired = [k for k, v in _pending_auth.items() if now - v["created"] > _PENDING_TTL_SECONDS]
    for k in expired:
        _pending_auth.pop(k, None)


@app.route("/demo/start")
def demo_start():
    try:
        state = google_oauth.new_state()
        session["oauth_state"] = state
        return redirect(google_oauth.build_authorization_url(state))
    except OAuthConfigError as exc:
        app.logger.error(f"demo misconfigured: {exc}")
        return render_template("demo_error.html", message="The live demo isn't available right now."), 503


@app.route("/demo/oauth/callback")
def demo_oauth_callback():
    if request.args.get("error"):
        return render_template(
            "demo_error.html",
            message="It looks like you didn't finish connecting your Google Business Profile. You can try again anytime.",
        )

    expected_state = session.pop("oauth_state", None)
    returned_state = request.args.get("state")
    if not expected_state or not returned_state or not secrets.compare_digest(expected_state, returned_state):
        return render_template("demo_error.html", message="Your session expired - please start the demo again."), 400

    code = request.args.get("code")
    if not code:
        return render_template("demo_error.html", message="Something went wrong connecting to Google."), 400

    try:
        tokens = google_oauth.exchange_code_for_tokens(code)
        if not tokens.refresh_token:
            return render_template(
                "demo_error.html",
                message="Google didn't grant us access - please try again and make sure to approve the request.",
            ), 400

        locations = google_oauth.list_accounts_and_locations(tokens.access_token)
    except OAuthConfigError as exc:
        app.logger.error(f"demo misconfigured: {exc}")
        return render_template("demo_error.html", message="The live demo isn't available right now."), 503
    except Exception as exc:
        app.logger.exception("OAuth callback failed")
        return render_template("demo_error.html", message="We couldn't connect to Google - please try again."), 502

    if not locations:
        return render_template(
            "demo_error.html",
            message="We couldn't find a Business Profile on that Google account - make sure you're signed in as the account that manages your listing.",
        )

    if len(locations) == 1:
        return _run_and_render(locations[0], tokens.refresh_token)

    pending_id = _stash_pending_auth(tokens.refresh_token, locations)
    return render_template("demo_picker.html", pending_id=pending_id, locations=locations)


@app.route("/demo/locations", methods=["POST"])
def demo_locations():
    pending_id = request.form.get("pending_id", "")
    location_key = request.form.get("location_key", "")
    entry = _pop_pending_auth(pending_id)
    if not entry:
        return render_template("demo_error.html", message="Your session expired - please start the demo again."), 400

    chosen = next(
        (loc for loc in entry["locations"] if f"{loc.account_id}:{loc.location_id}" == location_key), None
    )
    if not chosen:
        return render_template("demo_error.html", message="Please pick one of the listed locations."), 400

    return _run_and_render(chosen, entry["refresh_token"])


def _run_and_render(location, refresh_token: str):
    try:
        result = demo.run_demo(location, refresh_token)
    except subprocess.TimeoutExpired:
        return render_template(
            "demo_error.html", message="That took longer than expected - please try again in a moment."
        ), 504
    except demo.DemoRunError as exc:
        app.logger.error(f"demo run failed: {exc}")
        return render_template("demo_error.html", message="Something went wrong generating your preview."), 500

    if not result["reviews"]:
        return render_template("demo_error.html", message="We didn't find any new reviews to preview on that listing yet.")

    return render_template("demo_results.html", business_name=result["business_name"], reviews=result["reviews"])


@app.route("/demo/lead", methods=["POST"])
def demo_lead():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    if not email:
        return render_template("demo_error.html", message="Please include an email address."), 400
    with open(LEADS_PATH, "a") as f:
        f.write(json.dumps({"name": name, "email": email, "at": time.time()}) + "\n")
    return render_template("demo_thanks.html", name=name)


if __name__ == "__main__":
    removed = demo.sweep_stale_demo_dirs()
    if removed:
        app.logger.info(f"swept {removed} stale demo director{'y' if removed == 1 else 'ies'} on startup")
    # threaded=False is deliberate - see webapp/demo.py's module docstring
    # on why concurrent demo runs aren't safe yet with lib/config.py's
    # process-global active-business state.
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=False)
