"""
SVG Renderer — deterministic SVG meme output.

Pure Python. No external system fonts. No network calls.
CI-safe: produces identical output on any platform.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.meme_offload.schema import MemeSpecV1

# Fixed font stack — system-safe, deterministic
FONT_FAMILY = "monospace"
FONT_SIZE_TITLE = 36
FONT_SIZE_BODY = 28
FONT_SIZE_BULLET = 24


def _escape(text: str) -> str:
    """HTML-escape text for SVG embedding."""
    return html.escape(text, quote=True)


def _wrap_text_svg(text: str, max_chars: int = 30) -> list[str]:
    """Word-wrap text into lines of max_chars width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip() if current else word
    if current:
        lines.append(current)
    return lines or [""]


def _render_two_panel_svg(spec: MemeSpecV1) -> str:
    """Render a two-panel meme as SVG."""
    w = spec.canvas.w
    h = spec.canvas.h
    bg = spec.canvas.bg
    top_text = getattr(spec.text, "top", "")
    bottom_text = getattr(spec.text, "bottom", "")

    top_lines = _wrap_text_svg(top_text)
    bottom_lines = _wrap_text_svg(bottom_text)

    # Build top text elements
    top_y_start = h // 4
    top_elements = []
    for i, line in enumerate(top_lines):
        y = top_y_start + i * (FONT_SIZE_BODY + 6)
        top_elements.append(
            f'  <text x="{w // 2}" y="{y}" '
            f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_BODY}" '
            f'fill="white" text-anchor="middle">{_escape(line)}</text>'
        )

    # Build bottom text elements
    bottom_y_start = (h * 3) // 4
    bottom_elements = []
    for i, line in enumerate(bottom_lines):
        y = bottom_y_start + i * (FONT_SIZE_BODY + 6)
        bottom_elements.append(
            f'  <text x="{w // 2}" y="{y}" '
            f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_BODY}" '
            f'fill="white" text-anchor="middle">{_escape(line)}</text>'
        )

    # Divider line
    divider_y = h // 2
    divider = (
        f'  <line x1="40" y1="{divider_y}" x2="{w - 40}" y2="{divider_y}" '
        f'stroke="#555" stroke-width="2" />'
    )

    text_block = "\n".join(top_elements + [divider] + bottom_elements)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <rect width="{w}" height="{h}" fill="{bg}" />\n'
        f'{text_block}\n'
        f'</svg>\n'
    )


def _render_infographic_svg(spec: MemeSpecV1) -> str:
    """Render an infographic-list meme as SVG."""
    w = spec.canvas.w
    h = spec.canvas.h
    bg = spec.canvas.bg
    title = getattr(spec.text, "title", "")
    bullets = getattr(spec.text, "bullets", ())

    # Title
    title_el = (
        f'  <text x="{w // 2}" y="80" '
        f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_TITLE}" '
        f'fill="white" text-anchor="middle" font-weight="bold">'
        f'{_escape(title)}</text>'
    )

    # Bullets
    bullet_elements = []
    for i, bullet in enumerate(bullets):
        y = 160 + i * (FONT_SIZE_BULLET + 16)
        bullet_elements.append(
            f'  <text x="60" y="{y}" '
            f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_BULLET}" '
            f'fill="#cccccc">• {_escape(bullet)}</text>'
        )

    text_block = "\n".join([title_el] + bullet_elements)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <rect width="{w}" height="{h}" fill="{bg}" />\n'
        f'{text_block}\n'
        f'</svg>\n'
    )


def render_meme_svg(spec: MemeSpecV1) -> Path:
    """
    Render a MemeSpecV1 as an SVG file. Pure Python, deterministic.

    Returns: Path to the written SVG file.
    """
    out_dir = Path(spec.output.render_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Swap extension to .svg
    stem = Path(spec.output.filename).stem
    svg_filename = f"{stem}.svg"
    out_path = out_dir / svg_filename

    fmt = spec.format
    if fmt == "infographic_list":
        svg_content = _render_infographic_svg(spec)
    else:
        svg_content = _render_two_panel_svg(spec)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    return out_path
