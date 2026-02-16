"""
Meme Renderer — deterministic Pillow-based image generation.

Formats: two_panel, infographic_list
Default canvas: 1080x1080
No network calls. Pure local rendering.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.agents.meme_offload.schema import (
    MemeSpecV1, MemeTextTwoPanel, MemeTextInfographic,
)

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False


# ---------------------------------------------------------------------------
# Font loading (deterministic, no network)
# ---------------------------------------------------------------------------

_FONT_CACHE: dict = {}

def _get_font(size: int) -> any:
    """Load font deterministically. Falls back to default if DejaVuSans missing."""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    font = None
    if _HAS_PILLOW:
        # Try common system paths
        for path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]:
            try:
                font = ImageFont.truetype(path, size)
                break
            except (OSError, IOError):
                continue
        if font is None:
            font = ImageFont.load_default()

    _FONT_CACHE[size] = font
    return font


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_two_panel(spec: MemeSpecV1) -> Image.Image:
    """Render a two-panel meme: top text + bottom text on solid background."""
    w, h = spec.canvas.w, spec.canvas.h
    bg = spec.canvas.bg
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    text = spec.text
    top_text = text.top if isinstance(text, MemeTextTwoPanel) else ""
    bottom_text = text.bottom if isinstance(text, MemeTextTwoPanel) else ""

    font_large = _get_font(42)
    font_small = _get_font(36)

    # Divider line at center
    mid_y = h // 2
    draw.line([(40, mid_y), (w - 40, mid_y)], fill="#e94560", width=3)

    # Top text
    if top_text:
        _draw_wrapped_text(draw, top_text, font_large, w, 60, mid_y - 40, fill="#ffffff")

    # Bottom text
    if bottom_text:
        _draw_wrapped_text(draw, bottom_text, font_small, w, mid_y + 40, h - 40, fill="#cccccc")

    return img


def _render_infographic_list(spec: MemeSpecV1) -> Image.Image:
    """Render an infographic list: title + bullet points."""
    w, h = spec.canvas.w, spec.canvas.h
    bg = spec.canvas.bg
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    text = spec.text
    title = text.title if isinstance(text, MemeTextInfographic) else ""
    bullets = text.bullets if isinstance(text, MemeTextInfographic) else ()

    font_title = _get_font(48)
    font_bullet = _get_font(32)

    # Title
    y_cursor = 60
    if title:
        _draw_wrapped_text(draw, title, font_title, w, y_cursor, y_cursor + 120, fill="#e94560")
        y_cursor += 140

    # Divider
    draw.line([(60, y_cursor), (w - 60, y_cursor)], fill="#444444", width=2)
    y_cursor += 30

    # Bullets
    for bullet in bullets:
        bullet_text = f"• {bullet}"
        _draw_wrapped_text(draw, bullet_text, font_bullet, w - 80, 80, y_cursor + 60, fill="#ffffff", draw_obj=draw, img_w=w)
        y_cursor += 70
        if y_cursor > h - 80:
            break

    return img


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    y_start: int,
    y_end: int,
    fill: str = "#ffffff",
    draw_obj=None,
    img_w: Optional[int] = None,
) -> None:
    """Draw text with basic word wrapping, centered horizontally."""
    effective_w = img_w if img_w else max_width
    margin = 60
    available = effective_w - 2 * margin

    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= available:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    y = y_start
    for line in lines:
        if y > y_end:
            break
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (effective_w - tw) // 2
        draw.text((x, y), line, font=font, fill=fill)
        th = bbox[3] - bbox[1]
        y += th + 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_meme(spec: MemeSpecV1) -> Path:
    """
    Render a meme spec to PNG. Returns output path.
    Raises ImportError if Pillow not installed.
    """
    if not _HAS_PILLOW:
        raise ImportError("Pillow is required for meme rendering: pip install Pillow")

    if spec.format == "infographic_list":
        img = _render_infographic_list(spec)
    else:
        img = _render_two_panel(spec)

    out_dir = Path(spec.output.render_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / spec.output.filename

    img.save(str(out_path), "PNG")
    return out_path
