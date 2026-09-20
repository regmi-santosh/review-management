import sqlite3
from typing import Optional, Tuple

from lib import config, social_platforms, store
from lib.google_client import get_google_client
from lib.logging_setup import get_logger
from lib.notifier import notify_social_draft


def post_review_reply(conn: sqlite3.Connection, review_id: int, text: Optional[str] = None) -> dict:
    """Post `text` (or the review's draft_reply) to Google and mark it posted.

    Raises on failure; caller decides how to recover the review's status.
    """
    logger = get_logger("actions")
    review = store.get_review(conn, review_id)
    if not review:
        raise ValueError(f"no review with id {review_id}")

    reply_text = text or review.get("draft_reply")
    if not reply_text:
        raise ValueError(f"review {review_id} has no draft_reply to post")

    client = get_google_client()
    try:
        client.post_reply(review["external_id"], review.get("location_id"), reply_text)
    except Exception:
        logger.exception(f"failed to post reply for review {review_id} (external_id={review['external_id']})")
        raise

    store.update_review(conn, review_id, posted_reply=reply_text, status="posted", reply_source="agent")
    logger.info(f"posted reply for review {review_id} (external_id={review['external_id']})")
    return store.get_review(conn, review_id)


def fetch_and_store_new_reviews(
    conn: sqlite3.Connection,
    client,
    max_batch: int = 50,
    allow_large_batch: bool = False,
) -> dict:
    """Pull reviews from `client` and insert any not already in the local
    DB (see store.insert_review's existing-reply protection), then return
    every review still awaiting action. Extracted from
    tools/fetch_reviews.py so a non-CLI caller (e.g. an MCP tool) can
    reuse the exact same logic - the "batch too large" safety guardrail is
    expressed as a `batch_too_large: True` key in the returned dict rather
    than a process exit code, since only a CLI caller can usefully exit(2);
    a library caller makes its own judgment call about what to do with
    that signal.
    """
    logger = get_logger("actions")
    fetched = client.fetch_reviews()

    already_replied = 0
    for raw in fetched:
        new_id = store.insert_review(
            conn,
            raw.external_id,
            raw.author_name,
            raw.rating,
            raw.text,
            raw.create_time,
            existing_reply=raw.existing_reply,
            location_id=raw.location_id,
            profile_photo_url=raw.profile_photo_url,
            is_anonymous=raw.is_anonymous,
        )
        if new_id is None:
            continue
        row = store.get_review(conn, new_id)
        if row["status"] != "new":
            already_replied += 1

    actionable = store.list_reviews(conn, status="new")
    logger.info(f"fetched={len(fetched)} already_replied={already_replied} actionable={len(actionable)}")

    if len(actionable) > max_batch and not allow_large_batch:
        logger.warning(f"batch_too_large: {len(actionable)} actionable reviews exceeds max_batch={max_batch}")
        return {
            "fetched": len(fetched),
            "already_replied": already_replied,
            "batch_too_large": True,
            "actionable_count": len(actionable),
            "max_batch": max_batch,
            "message": (
                f"{len(actionable)} reviews need action, exceeding max_batch={max_batch}. This is "
                "unusual - confirm with a human this is expected (e.g. a large backlog on a "
                "first-ever fetch) before processing. Nothing is lost: all reviews are safely "
                "stored as status=new."
            ),
            "new": [],
        }

    return {"fetched": len(fetched), "already_replied": already_replied, "new": actionable}


def draft_social_post_for_review(conn: sqlite3.Connection, review_id: int, caption: str) -> dict:
    """Render and store a per-platform social draft for one review -
    extracted from tools/save_social_draft.py so a non-CLI caller can
    reuse the exact same logic. Raises ValueError if the review doesn't
    exist; returns {"rendered": {...}, "images": {...}, "warning":
    Optional[str]} - a platform whose image render failed is still
    included in "rendered" (the text draft is unaffected) but absent from
    "images", same graceful-degradation behavior as the CLI version."""
    logger = get_logger("actions")
    review = store.get_review(conn, review_id)
    if not review:
        raise ValueError(f"no review with id {review_id}")

    store.update_review(conn, review_id, draft_social_post=caption)

    business = config.active()
    rendered = social_platforms.render_all(caption, business.social_hashtags, business.social_platforms)
    warning = None
    if not rendered and business.social_platforms:
        warning = (
            f"business.json social_platforms {business.social_platforms} matched no registered "
            "platform (see lib/social_platforms.py) - nothing drafted. Check for a typo."
        )
        logger.warning(warning)

    images = {}
    out_dir = business.dir / "social_images"
    for platform in rendered:
        try:
            png_bytes = social_platforms.get_platform(platform).render_image(business, review)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{review_id}_{platform}.png"
            path.write_bytes(png_bytes)
        except Exception as exc:
            logger.warning(f"social image generation failed for {platform} (review {review_id}): {exc}")
            continue
        images[platform] = str(path)

    store.save_social_posts(conn, review_id, rendered, images)

    for platform, text in sorted(rendered.items()):
        notify_caption = f"\U0001F4F1 {platform} post idea (review {review_id}, {review['rating']}★):\n{text}"
        notify_social_draft(notify_caption, image_path=images.get(platform))

    return {"rendered": rendered, "images": images, "warning": warning}


def _milestone_headline(milestone: dict) -> Tuple[str, str]:
    """The card's business name/logo header already identifies the
    business, so the subline adds context instead of repeating the name."""
    threshold = milestone["threshold"]
    milestone_type = milestone["type"]
    if milestone_type == "review_count":
        return f"{threshold}+ Reviews!", "Thank you for trusting us"
    if milestone_type == "rating_streak":
        return f"{threshold} Five-Star{'' if threshold == 1 else 's'} in a Row!", "We couldn't do it without you"
    if milestone_type == "anniversary":
        return f"{threshold} Year{'s' if threshold != 1 else ''} Strong!", "Thank you for growing with us"
    raise ValueError(f"unknown milestone type: {milestone_type}")


def draft_social_post_for_milestone(conn: sqlite3.Connection, milestone_id: int, caption: str) -> dict:
    """The milestone equivalent of draft_social_post_for_review() -
    extracted from tools/save_milestone_draft.py. Same return shape."""
    logger = get_logger("actions")
    milestone = store.get_milestone(conn, milestone_id)
    if not milestone:
        raise ValueError(f"no milestone with id {milestone_id}")

    business = config.active()
    rendered = social_platforms.render_all(caption, business.social_hashtags, business.social_platforms)
    warning = None
    if not rendered and business.social_platforms:
        warning = (
            f"business.json social_platforms {business.social_platforms} matched no registered "
            "platform (see lib/social_platforms.py) - nothing drafted. Check for a typo."
        )
        logger.warning(warning)

    headline, subline = _milestone_headline(milestone)
    images = {}
    out_dir = business.dir / "social_images"
    for platform in rendered:
        try:
            png_bytes = social_platforms.get_platform(platform).render_milestone_image(business, headline, subline)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"milestone_{milestone_id}_{platform}.png"
            path.write_bytes(png_bytes)
        except Exception as exc:
            logger.warning(f"milestone image generation failed for {platform} (milestone {milestone_id}): {exc}")
            continue
        images[platform] = str(path)

    store.save_milestone_posts(conn, milestone_id, rendered, images)

    for platform, text in sorted(rendered.items()):
        notify_caption = (
            f"\U0001F389 {platform} milestone post idea "
            f"({milestone['type']} {milestone['threshold']}):\n{text}"
        )
        notify_social_draft(notify_caption, image_path=images.get(platform))

    return {"rendered": rendered, "images": images, "warning": warning}


def publish_social_post(
    conn: sqlite3.Connection,
    platform_name: str,
    review_id: Optional[int] = None,
    milestone_id: Optional[int] = None,
) -> str:
    """Actually publish an already-drafted social post to `platform_name` -
    extracted from tools/post_social.py. Exactly one of review_id/
    milestone_id must be given. Raises ValueError/RuntimeError on any
    failure (no draft, already posted, platform API error) instead of
    exiting the process, so a non-CLI caller can handle it. Returns the
    external post id."""
    if (review_id is None) == (milestone_id is None):
        raise ValueError("exactly one of review_id or milestone_id must be given")

    business = config.active()
    platform = social_platforms.get_platform(platform_name)

    if review_id is not None:
        kind, target_id = "review", review_id
        posts = {p["platform"]: p for p in store.list_social_posts(conn, target_id)}
        draft_tool, mark_posted = "draft_social_post_for_review", store.mark_social_post_posted
    else:
        kind, target_id = "milestone", milestone_id
        posts = {p["platform"]: p for p in store.list_milestone_posts(conn, target_id)}
        draft_tool, mark_posted = "draft_social_post_for_milestone", store.mark_milestone_post_posted

    post = posts.get(platform_name)
    if not post:
        raise ValueError(f"no drafted social post for {kind} {target_id} on {platform_name} - call {draft_tool} first")
    if post["status"] == "posted":
        raise ValueError(
            f"{kind} {target_id} was already posted to {platform_name} (external id {post['external_post_id']})"
        )

    external_id = platform.post(business, post["image_path"], post["text"])
    mark_posted(conn, target_id, platform_name, external_id)
    get_logger("actions").info(f"posted {kind} {target_id} to {platform_name}: {external_id}")
    return external_id


def reject_review(conn: sqlite3.Connection, review_id: int) -> dict:
    review = store.get_review(conn, review_id)
    if not review:
        raise ValueError(f"no review with id {review_id}")
    store.update_review(conn, review_id, status="rejected")
    get_logger("actions").info(f"rejected review {review_id} (external_id={review['external_id']})")
    return store.get_review(conn, review_id)
