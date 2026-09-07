#!/usr/bin/env python3
"""Save a drafted social-media caption for a review, render a per-platform
quote-card image (lib/social_image.py) for each enabled platform (see
lib/social_platforms.py), and push each one through every configured
notification channel (Telegram/Slack - see docs/API_SETUP.md) as a photo
where an image rendered, plain text otherwise. Called by the
review-handler agent for every 5-star review it processes (Step 5) -
draft-only, nothing gets auto-posted to any social platform, this repo has
no such integration.

Usage:
  python3 tools/save_social_draft.py --review-id 3 --caption "One of our regulars stopped by for a fresh brow shape and left glowing - exactly the kind of visit we love. 🌸"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, social_platforms, store
from lib.cli import add_business_arg, apply_business_arg
from lib.logging_setup import get_logger
from lib.notifier import notify_social_draft


def _render_images(business, review: dict, rendered: dict) -> dict:
    """Render one quote-card PNG per platform in `rendered`, saved under
    businesses/<slug>/social_images/. A platform's image generation
    failing (missing Pillow, bad font, etc.) just leaves it out - the text
    draft for that platform is unaffected."""
    logger = get_logger("save_social_draft")
    out_dir = business.dir / "social_images"
    images = {}
    for platform in rendered:
        try:
            png_bytes = social_platforms.get_platform(platform).render_image(business, review)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{review['id']}_{platform}.png"
            path.write_bytes(png_bytes)
        except Exception as exc:
            logger.warning(f"social image generation failed for {platform} (review {review['id']}): {exc}")
            continue
        images[platform] = str(path)
    return images


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--caption", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    review = store.get_review(conn, args.review_id)
    if not review:
        print(f"error: no review with id {args.review_id}", file=sys.stderr)
        sys.exit(1)

    store.update_review(conn, args.review_id, draft_social_post=args.caption)

    business = config.active()
    rendered = social_platforms.render_all(
        args.caption, business.social_hashtags, business.social_platforms
    )
    if not rendered and business.social_platforms:
        print(
            f"warning: business.json social_platforms {business.social_platforms} matched no "
            "registered platform (see lib/social_platforms.py) - nothing drafted. Check for a typo.",
            file=sys.stderr,
        )
    images = _render_images(business, review, rendered)
    store.save_social_posts(conn, args.review_id, rendered, images)

    for platform, text in sorted(rendered.items()):
        caption = f"\U0001F4F1 {platform} post idea (review {args.review_id}, {review['rating']}★):\n{text}"
        notify_social_draft(caption, image_path=images.get(platform))
    print("Social draft saved.")


if __name__ == "__main__":
    main()
