"""Renders a branded quote-card PNG for one review — the image companion
to lib/social_platforms.py's per-platform caption text. See
docs/ARCHITECTURE.md "Social platform layer".

Pillow is this repo's one deliberate non-stdlib dependency (see
requirements.txt) — there's no reasonable way to rasterize text/logos into
a PNG with the standard library alone.
"""
from __future__ import annotations

import io
import math
import re
from pathlib import Path
from typing import List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_IMPORT_ERROR = None
except ImportError as exc:
    _PIL_IMPORT_ERROR = exc


def is_available() -> bool:
    """Whether Pillow actually imported - tools/check_health.py uses this
    instead of importing PIL itself, so it doesn't need to know this
    module's rendering library is Pillow specifically."""
    return _PIL_IMPORT_ERROR is None


_SYSTEM_FONT_CANDIDATES = ["/System/Library/Fonts/Helvetica.ttc"]
_STAR_FILLED_COLOR = "#D4A017"
_STAR_EMPTY_COLOR = "#DDDDDD"

# Helvetica (this repo's only rendered font - see _load_font) has no color
# emoji glyphs, so an emoji in a review's own text renders as a tofu box
# instead of silently being skipped. Stripped before any text reaches
# draw.text() - the Facebook/etc. caption text (lib/social_platforms.py)
# is unaffected and still shows emoji normally, since that's posted as
# plain text, never rasterized.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001FAFF"  # flags, symbols, pictographs, supplemental
    "\U0001F000-\U0001F0FF"  # mahjong/dominoes/playing cards
    "\U00002600-\U000027BF"  # misc symbols & dingbats (e.g. ❤ ☀ ✨)
    "\U0000FE0F"  # variation selector-16 (emoji presentation)
    "\U0000200D"  # zero-width joiner (multi-codepoint emoji sequences)
    "]+"
)


def _strip_emoji(text: str) -> str:
    without_emoji = _EMOJI_PATTERN.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", without_emoji).strip()


def _load_font(business, size: int, bold: bool = False):
    if business.brand_font_path and Path(business.brand_font_path).exists():
        try:
            return ImageFont.truetype(business.brand_font_path, size)
        except OSError:
            pass
    for path in _SYSTEM_FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=1 if bold else 0)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_quote(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> List[str]:
    """Word-wrap `text` to `max_width`, then truncate to `max_lines` on a
    word boundary with a trailing ellipsis if it doesn't fit — never cuts
    mid-word, same principle as SocialPlatform._truncate_caption."""
    lines = _wrap_to_width(draw, text, font, max_width)
    if len(lines) <= max_lines:
        return lines
    lines = lines[:max_lines]
    last = lines[-1]
    while " " in last and draw.textlength(last + "…", font=font) > max_width:
        last = last.rsplit(" ", 1)[0]
    lines[-1] = f"{last}…"
    return lines


def _quote_lines(draw: ImageDraw.ImageDraw, quote_text: str, font, max_width: int, max_lines: int) -> List[str]:
    """Word-wrapped, quote-mark-wrapped lines for `quote_text`, or `[]` for
    an empty/emoji-only review (e.g. a bare star rating with no comment) -
    deliberately NOT `['“”']`, which is what naively wrapping an empty
    string in quote marks would produce (an empty pair of quote marks is
    not a lower-effort quote, it's a card that looks broken)."""
    if not quote_text:
        return []
    return _fit_quote(draw, f"“{quote_text}”", font, max_width, max_lines)


def _star_points(cx: float, cy: float, outer_r: float, inner_r: float) -> List[Tuple[float, float]]:
    """Ten alternating outer/inner vertices of a 5-pointed star. Drawn as a
    polygon rather than a ★ glyph - most fonts (Helvetica included) don't
    actually have that Unicode character, which silently renders as a
    tofu/empty box."""
    points = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = outer_r if i % 2 == 0 else inner_r
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _draw_stars(draw: ImageDraw.ImageDraw, center_x: float, y: float, rating: int, star_size: float) -> None:
    spacing = star_size * 1.3
    start_x = center_x - (spacing * 5) / 2 + spacing / 2
    for i in range(5):
        cx = start_x + i * spacing
        filled = i < rating
        color = _STAR_FILLED_COLOR if filled else _STAR_EMPTY_COLOR
        points = _star_points(cx, y + star_size / 2, star_size / 2, star_size * 0.19)
        draw.polygon(points, fill=color)


def render_quote_card(business, review: dict, size: Tuple[int, int]) -> bytes:
    """Render a branded testimonial card for `review` at `size` (w, h) and
    return PNG bytes. Never includes the reviewer's name (same anonymity
    rule as the text caption) — only the quote and a star rating."""
    if not is_available():
        raise RuntimeError(
            "Pillow not installed (pip install -r requirements.txt) - can't render quote-card images"
        ) from _PIL_IMPORT_ERROR
    width, height = size
    card = Image.new("RGB", size, business.brand_color)
    draw = ImageDraw.Draw(card)

    # Horizontal and vertical spacing scale off width and height
    # separately - a wide-short card (Facebook 1200x630, Twitter 1200x675)
    # must not inherit a width-sized top/bottom margin or its logo will eat
    # the whole vertical budget before the quote is even drawn.
    margin_x = int(width * 0.08)
    margin_y = int(height * 0.08)
    content_width = width - 2 * margin_x
    y = margin_y

    logo_path = business.logo_path
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        # Fit within both a width-based and a height-based cap - whichever
        # is smaller wins, so a square logo never overflows a short card.
        logo_w = min(int(content_width * 0.45), int(logo.width * (height * 0.38) / logo.height))
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h))
        card.paste(logo, (int((width - logo_w) / 2), y), logo)
        y += logo_h + int(height * 0.03)
    else:
        name_font_size = max(int(height * 0.05), 16)
        name_font = _load_font(business, name_font_size, bold=True)
        name_lines = _wrap_to_width(draw, _strip_emoji(business.name), name_font, content_width)
        name_line_height = int(name_font_size * 1.25)
        for line in name_lines:
            line_w = draw.textlength(line, font=name_font)
            draw.text(((width - line_w) / 2, y), line, font=name_font, fill=business.brand_text_color)
            y += name_line_height
        y += int(height * 0.04)

    rating = max(0, min(5, review.get("rating") or 0))
    star_size = height * 0.06
    _draw_stars(draw, width / 2, y, rating, star_size)
    y += int(star_size + height * 0.04)

    footer_font = _load_font(business, max(int(height * 0.035), 16))
    footer = "Google review"
    footer_h = int(height * 0.05)

    quote_font_size = max(int(height * 0.045), 16)
    quote_font = _load_font(business, quote_font_size)
    line_height = int(quote_font_size * 1.4)
    available = height - y - margin_y - footer_h
    max_lines = max(1, available // line_height)

    quote_text = _strip_emoji(review.get("text") or "")
    lines = _quote_lines(draw, quote_text, quote_font, content_width, max_lines)

    block_height = len(lines) * line_height
    text_y = y + max(0, (available - block_height) // 2)
    for line in lines:
        line_w = draw.textlength(line, font=quote_font)
        draw.text(((width - line_w) / 2, text_y), line, font=quote_font, fill=business.brand_text_color)
        text_y += line_height

    footer_w = draw.textlength(footer, font=footer_font)
    draw.text(((width - footer_w) / 2, height - margin_y - footer_h), footer, font=footer_font, fill=business.brand_text_color)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    return buf.getvalue()


def render_milestone_card(business, headline: str, subline: str, size: Tuple[int, int]) -> bytes:
    """Render a branded milestone card (e.g. "500 Reviews!") for
    tools/save_milestone_draft.py - same visual system as
    render_quote_card (brand-color background, logo-or-name header) but
    built around a big headline instead of one review's quote, since a
    milestone isn't about any single review."""
    if not is_available():
        raise RuntimeError(
            "Pillow not installed (pip install -r requirements.txt) - can't render milestone-card images"
        ) from _PIL_IMPORT_ERROR
    width, height = size
    card = Image.new("RGB", size, business.brand_color)
    draw = ImageDraw.Draw(card)

    margin_x = int(width * 0.08)
    margin_y = int(height * 0.08)
    content_width = width - 2 * margin_x
    y = margin_y

    logo_path = business.logo_path
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        logo_w = min(int(content_width * 0.4), int(logo.width * (height * 0.3) / logo.height))
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h))
        card.paste(logo, (int((width - logo_w) / 2), y), logo)
        y += logo_h + int(height * 0.04)
    else:
        name_font_size = max(int(height * 0.045), 16)
        name_font = _load_font(business, name_font_size, bold=True)
        name_lines = _wrap_to_width(draw, _strip_emoji(business.name), name_font, content_width)
        name_line_height = int(name_font_size * 1.25)
        for line in name_lines:
            line_w = draw.textlength(line, font=name_font)
            draw.text(((width - line_w) / 2, y), line, font=name_font, fill=business.brand_text_color)
            y += name_line_height
        y += int(height * 0.05)

    subline_font_size = max(int(height * 0.035), 14)
    subline_font = _load_font(business, subline_font_size)
    subline_line_height = int(subline_font_size * 1.3)
    subline = _strip_emoji(subline)
    subline_lines = _wrap_to_width(draw, subline, subline_font, content_width) if subline else []
    subline_block_height = len(subline_lines) * subline_line_height

    headline_font_size = max(int(height * 0.12), 24)
    headline_font = _load_font(business, headline_font_size, bold=True)
    headline_line_height = int(headline_font_size * 1.15)
    headline_lines = _fit_quote(draw, _strip_emoji(headline), headline_font, content_width, 2)

    available = height - y - margin_y - subline_block_height - int(height * 0.03)
    block_height = len(headline_lines) * headline_line_height
    text_y = y + max(0, (available - block_height) // 2)
    for line in headline_lines:
        line_w = draw.textlength(line, font=headline_font)
        draw.text(((width - line_w) / 2, text_y), line, font=headline_font, fill=business.brand_text_color)
        text_y += headline_line_height

    sub_y = height - margin_y - subline_block_height
    for line in subline_lines:
        line_w = draw.textlength(line, font=subline_font)
        draw.text(((width - line_w) / 2, sub_y), line, font=subline_font, fill=business.brand_text_color)
        sub_y += subline_line_height

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    return buf.getvalue()
