"""Orchestrates one demo run: create an ephemeral businesses/_demo_<id>/
directory from a visitor's freshly-authorized Google credentials, run the
existing review-handler agent against it exactly as an onboarded business
would, read the results back, and delete the directory - see
docs/ARCHITECTURE.md "Demo layer" and the plan this was built from.

Deliberately reuses everything in lib/ and tools/ unmodified: the whole
point of the ephemeral-directory approach is that LiveGoogleBusinessProfileClient,
lib/store.py, and review-handler.md don't need to know this is a demo at
all - they just see one more --business <slug>.

Concurrency note: lib/config.py's active-business selection is a single
process-wide global (config.use_business()), which is fine for the CLI
tools this repo was built around (one process, one business, one run) but
NOT safe for two demo requests running at once in this same process - they
would stomp each other's active business mid-run. _DEMO_LOCK below
serializes demo runs to sidestep that entirely rather than trying to make
config.py thread-safe. Fine for "local machine + tunnel" scale; revisit if
this ever needs to serve concurrent visitors for real.
"""
import base64
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from lib import config, store
from webapp.google_oauth import BusinessLocation

REPO_ROOT = Path(__file__).resolve().parent.parent
BUSINESSES_DIR = REPO_ROOT / "businesses"
DEMO_PREFIX = "_demo_"
STALE_SECONDS = 15 * 60
DEMO_MAX_REVIEWS = 5
AGENT_TIMEOUT_SECONDS = 300

_DEMO_LOCK = threading.Lock()


class DemoRunError(RuntimeError):
    pass


def _demo_slug() -> str:
    return f"{DEMO_PREFIX}{uuid.uuid4().hex[:12]}"


def _create_ephemeral_business(location: BusinessLocation, refresh_token: str) -> str:
    slug = _demo_slug()
    biz_dir = BUSINESSES_DIR / slug
    biz_dir.mkdir(parents=True, exist_ok=False)

    business_json = {
        "name": location.title or "Your Business",
        "category": "Local service business",
        "google_account_id": location.account_id,
        "google_location_id": location.location_id,
        "google_client_mode": "live",
    }
    (biz_dir / "business.json").write_text(json.dumps(business_json, indent=2))

    # Same secrets-file-permissions posture as every other business
    # directory (see lib/config.py's _write_env / tools/check_health.py's
    # check_secrets_permissions) - this one happens to hold a stranger's
    # live credential for only as long as this one demo run takes.
    env_path = biz_dir / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"GOOGLE_OAUTH_CLIENT_ID={os.environ.get('GOOGLE_WEB_OAUTH_CLIENT_ID', '')}",
                f"GOOGLE_OAUTH_CLIENT_SECRET={os.environ.get('GOOGLE_WEB_OAUTH_CLIENT_SECRET', '')}",
                f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}",
                "",
            ]
        )
    )
    env_path.chmod(0o600)

    (biz_dir / "profile.md").write_text(
        f"# Business profile: {business_json['name']}\n\n"
        "Demo run - no business-specific voice calibration yet (see "
        "docs/ONBOARDING.md's Voice calibration step, which a real "
        "onboarded business would go through). Use a warm, professional, "
        "generic small-business tone.\n"
    )
    return slug


def _cleanup_ephemeral_business(slug: str) -> None:
    shutil.rmtree(BUSINESSES_DIR / slug, ignore_errors=True)


def sweep_stale_demo_dirs() -> int:
    """Deletes any _demo_* directory older than STALE_SECONDS - a backstop
    for a crash that skipped _cleanup_ephemeral_business()'s `finally`.
    Call once on webapp startup. Returns how many it removed."""
    if not BUSINESSES_DIR.is_dir():
        return 0
    removed = 0
    now = time.time()
    for entry in BUSINESSES_DIR.iterdir():
        if entry.is_dir() and entry.name.startswith(DEMO_PREFIX):
            if now - entry.stat().st_mtime > STALE_SECONDS:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
    return removed


def _build_demo_prompt(slug: str) -> str:
    return (
        f'Run the review-handler agent for business "{slug}". This is a DEMO/PREVIEW run for a '
        "prospective customer trying the product against their own real Google Business Profile "
        "reviews - not a live production run. Follow review-handler.md's Step 0 through Step 4 and "
        "the save_review.py part of Step 5 exactly as written (fetch, classify, draft, route, "
        f"persist), but limit yourself to at most the first {DEMO_MAX_REVIEWS} actionable reviews "
        "from fetch_reviews.py's `new` list - ignore any beyond that for this run.\n\n"
        "Under NO circumstances run tools/post_reply.py, tools/notify.py, or "
        "tools/send_daily_summary.py, regardless of what status a review routes to - status=posted "
        "means \"would auto-post\" for display purposes only, not an instruction to actually call "
        "post_reply.py. This visitor has only agreed to preview the product, not to anything being "
        "sent to their real Google listing. tools/save_social_draft.py is fine to run normally for "
        "any 5-star review - it only ever drafts, never posts, by its own design. Skip "
        "tools/log_run.py and tools/check_milestones.py entirely - this ephemeral business has no "
        "meaningful run history or milestones to track.\n\n"
        "When finished, briefly confirm how many reviews you processed - the actual results will be "
        "read directly from the database, not from your reply."
    )


def _run_agent_headless(prompt: str) -> subprocess.CompletedProcess:
    harness = config.agent_harness()
    harness_script = REPO_ROOT / "scripts" / "harnesses" / f"{harness}.sh"
    if not harness_script.exists():
        raise DemoRunError(f"no harness adapter at {harness_script} (AGENT_HARNESS={harness})")

    env = {**os.environ, "DEMO_PROMPT": prompt}
    return subprocess.run(
        ["bash", "-c", f'source "{harness_script}" && run_agent "$DEMO_PROMPT"'],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=AGENT_TIMEOUT_SECONDS,
    )


def _inline_image(path: Optional[str]) -> Optional[str]:
    if not path or not Path(path).exists():
        return None
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


_STATUS_LABELS = {
    "posted": "Would auto-post",
    "escalated": "Would escalate to you immediately",
    "pending_review": "Would need your review first",
}


def run_demo(location: BusinessLocation, refresh_token: str) -> dict:
    """The full ephemeral-business lifecycle for one demo request: create,
    run, read results, always clean up. Serialized by _DEMO_LOCK - see
    module docstring."""
    with _DEMO_LOCK:
        slug = _create_ephemeral_business(location, refresh_token)
        try:
            config.use_business(slug)
            result = _run_agent_headless(_build_demo_prompt(slug))
            if result.returncode != 0:
                raise DemoRunError(
                    f"agent run failed (exit {result.returncode}): {result.stderr[-2000:]}"
                )

            conn = store.connect()
            reviews = store.list_reviews(conn)
            out_reviews = []
            for review in reviews:
                entry = {
                    "author_name": review["author_name"],
                    "rating": review["rating"],
                    "text": review["text"],
                    "category": review["category"],
                    "sentiment": review["sentiment"],
                    "urgency": review["urgency"],
                    "draft_reply": review["draft_reply"],
                    "status_label": _STATUS_LABELS.get(review["status"], review["status"]),
                    "social_image": None,
                    "social_caption": None,
                }
                if review["rating"] == 5:
                    posts = store.list_social_posts(conn, review["id"])
                    facebook_post = next((p for p in posts if p["platform"] == "facebook"), None)
                    if facebook_post:
                        entry["social_caption"] = facebook_post["text"]
                        entry["social_image"] = _inline_image(facebook_post["image_path"])
                out_reviews.append(entry)

            return {"business_name": location.title, "reviews": out_reviews}
        finally:
            _cleanup_ephemeral_business(slug)
