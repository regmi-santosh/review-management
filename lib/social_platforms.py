"""Per-platform social post templates — draft-only text rendering today,
the seam for real auto-posting later. See docs/ARCHITECTURE.md "Social
platform layer".

Same pluggable-adapter shape as lib/notifier.py: an ABC with one method per
capability, plus a registry dict. To add a platform: write a class
implementing SocialPlatform, add it to _PLATFORMS below. Nothing else in
this file, or any caller, needs to know a given platform exists.

Phase 1 (today): render() only, formatting one agent-drafted caption per
platform's hashtag/length conventions. Phase 2 (not yet built): post()
becomes a real API call once that platform's credentials exist.
"""
from abc import ABC
from typing import Dict, List, Optional, Tuple

from lib import social_image
from lib.notifier import post_multipart


class SocialPlatform(ABC):
    name: str
    char_limit: Optional[int] = None
    max_hashtags: int = 0
    image_size: Tuple[int, int] = (1080, 1080)

    def render(self, caption: str, hashtags: List[str]) -> str:
        """Format `caption` for this platform: append up to max_hashtags of
        the shared hashtag pool, dropping the lowest-priority ones first if
        the result is too long, and only truncating the caption itself (on
        a word boundary, with a trailing ellipsis) as a last resort."""
        tags = list(hashtags[: self.max_hashtags])
        while True:
            tag_str = " ".join(tags)
            text = f"{caption} {tag_str}".strip() if tag_str else caption
            if self.char_limit is None or len(text) <= self.char_limit:
                return text
            if tags:
                tags.pop()
                continue
            return self._truncate_caption(text)

    def _truncate_caption(self, text: str) -> str:
        ellipsis = "…"
        limit = self.char_limit - len(ellipsis)
        truncated = text[:limit].rsplit(" ", 1)[0]
        return f"{truncated}{ellipsis}"

    def render_image(self, business, review: dict) -> bytes:
        """Render this platform's branded quote-card PNG for `review` at
        its own aspect ratio. See lib/social_image.py."""
        return social_image.render_quote_card(business, review, self.image_size)

    def post(self, business, image_path: Optional[str], caption: str) -> str:
        """Publish `image_path` (a rendered quote-card PNG, see render_image)
        with `caption` to this platform and return an external post id.
        Default raises - not implemented until this platform's API
        credentials exist — see docs/ARCHITECTURE.md "Social platform
        layer" (Phase 2). Override only once a platform is actually wired
        up (see FacebookPlatform)."""
        raise NotImplementedError(f"{self.name}: auto-posting not configured yet")


class FacebookPlatform(SocialPlatform):
    name = "facebook"
    char_limit = None  # no practical limit
    max_hashtags = 2  # Facebook culture uses hashtags sparingly
    image_size = (1200, 630)  # standard link/share image ratio

    def post(self, business, image_path: Optional[str], caption: str) -> str:
        if not (business.facebook_page_id and business.facebook_page_access_token):
            raise RuntimeError(
                "facebook: FACEBOOK_PAGE_ID/FACEBOOK_PAGE_ACCESS_TOKEN not configured "
                f"in businesses/{business.slug}/.env"
            )
        if not image_path:
            raise RuntimeError(
                "facebook: no image to post for this review - either save_social_draft.py "
                "hasn't run yet, or its image render failed for this platform (check the "
                "save_social_draft logger output/log file for why)"
            )
        url = f"https://graph.facebook.com/v25.0/{business.facebook_page_id}/photos"
        result = post_multipart(
            url,
            {"caption": caption, "access_token": business.facebook_page_access_token},
            "source",
            image_path,
        )
        post_id = result.get("post_id") or result.get("id")
        if not post_id:
            raise RuntimeError(f"facebook: unexpected response {result}")
        return post_id


class InstagramPlatform(SocialPlatform):
    name = "instagram"
    char_limit = 2200
    max_hashtags = 10
    image_size = (1080, 1080)  # square feed post


class TwitterPlatform(SocialPlatform):
    name = "twitter"
    char_limit = 280
    max_hashtags = 2
    image_size = (1200, 675)  # 16:9 card


class TikTokPlatform(SocialPlatform):
    name = "tiktok"
    char_limit = 2200
    max_hashtags = 6
    image_size = (1080, 1920)  # vertical


# Each entry: platform name -> adapter instance. Add a new platform here —
# nothing else in this file needs to change.
_PLATFORMS: Dict[str, SocialPlatform] = {
    "facebook": FacebookPlatform(),
    "instagram": InstagramPlatform(),
    "twitter": TwitterPlatform(),
    "tiktok": TikTokPlatform(),
}


def available_platforms() -> List[str]:
    return list(_PLATFORMS)


def get_platform(name: str) -> SocialPlatform:
    return _PLATFORMS[name]


def render_all(
    caption: str, hashtags: List[str], platforms: Optional[List[str]] = None
) -> Dict[str, str]:
    """Render `caption` for every requested platform (`platforms=None`
    means all registered platforms; `platforms=[]` means none - checked
    with `is None`, not truthiness, so an explicit empty list is honored).
    Unknown platform names are silently skipped — tools/check_health.py is
    what surfaces a business.json typo."""
    names = platforms if platforms is not None else available_platforms()
    return {name: _PLATFORMS[name].render(caption, hashtags) for name in names if name in _PLATFORMS}
