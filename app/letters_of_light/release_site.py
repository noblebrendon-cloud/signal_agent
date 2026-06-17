"""
app/letters_of_light/release_site.py - Owned-site publisher for exported Letters.

This module publishes an already-exported Letters of Light campaign package to
the static brendonrcoleman.com repository. It does not push, deploy, or call any
external platform API.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.letters_of_light.release import (
    _get_root,
    _letter_dir,
    _read_json,
    _resolve_artifact_path,
    _utc_now,
    _write_json,
    _write_text,
)


DEFAULT_BASE_URL = "https://brendonrcoleman.com"
SITE_ROOT_ENV_VARS = ("LETTERS_OF_LIGHT_SITE_ROOT", "BRENDONRCOLEMAN_SITE_ROOT")
PUBLISHABLE_STATES = {"exported", "published"}


def _looks_like_site_root(path: Path) -> bool:
    return path.exists() and path.is_dir() and (path / "index.html").exists()


def resolve_site_root(site_root: Optional[str] = None) -> Path:
    if site_root:
        path = Path(site_root).expanduser()
        if _looks_like_site_root(path):
            return path
        raise RuntimeError(f"Site root is not a static site checkout: {path}")

    for env_name in SITE_ROOT_ENV_VARS:
        env_value = os.environ.get(env_name)
        if env_value:
            path = Path(env_value).expanduser()
            if _looks_like_site_root(path):
                return path
            raise RuntimeError(f"{env_name} does not point to a static site checkout: {path}")

    root = _get_root()
    drive_root = Path(root.anchor) if root.anchor else root.parent
    candidates = [
        root.parent / "brendonrcoleman.com",
        root.parent / "brendonrcoleman.com-main",
        drive_root / "githubpage" / "brendonrcoleman.com-main" / "brendonrcoleman.com-main",
        drive_root / "githubpage" / "brendonrcoleman.com-main",
    ]

    for candidate in candidates:
        if _looks_like_site_root(candidate):
            return candidate
        nested = candidate / "brendonrcoleman.com-main"
        if _looks_like_site_root(nested):
            return nested

    envs = ", ".join(SITE_ROOT_ENV_VARS)
    raise RuntimeError(f"Unable to locate brendonrcoleman.com checkout. Set one of: {envs}")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "letter"


def _page_slug(letter_id: str, release: Dict[str, Any]) -> str:
    return _slugify(str(release.get("slug") or letter_id))


def _canonical_url(base_url: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/letters/{slug}/"


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"[*_`#>-]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_site_markdown(markdown: str, fallback_title: str, fallback_scripture: str) -> Dict[str, Any]:
    title = fallback_title
    scripture = fallback_scripture
    body_lines: List[str] = []
    reflect_lines: List[str] = []
    in_reflect = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or title
            continue
        if stripped.lower() == "## reflect":
            in_reflect = True
            continue
        if in_reflect:
            reflect_lines.append(line)
        else:
            body_lines.append(line)

    paragraphs: List[str] = []
    current: List[str] = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped or stripped == "---":
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 1:
            scripture = stripped.strip("*").strip() or scripture
            continue
        current.append(stripped)

    if current:
        paragraphs.append(" ".join(current).strip())

    questions: List[str] = []
    for line in reflect_lines:
        match = re.match(r"\s*\d+\.\s+(.+?)\s*$", line)
        if match:
            questions.append(match.group(1))

    description = ""
    for paragraph in paragraphs:
        description = _clean_markdown_text(paragraph)
        if description:
            break
    if len(description) > 160:
        description = description[:157].rstrip() + "..."

    return {
        "title": title,
        "scripture": scripture,
        "paragraphs": paragraphs,
        "questions": questions,
        "description": description or f"A Letters of Light reflection: {title}",
    }


def _copy_media(export_dir: Path, release: Dict[str, Any], site_root: Path, slug: str) -> Dict[str, str]:
    asset_dir = site_root / "assets" / "letters" / slug
    asset_dir.mkdir(parents=True, exist_ok=True)

    copied: Dict[str, str] = {}

    video_source = export_dir / "final.mp4"
    if not video_source.exists():
        video_source = _resolve_artifact_path(release.get("assets", {}).get("video_path", ""))
    if video_source.exists() and video_source.is_file():
        video_dest = asset_dir / "final.mp4"
        shutil.copy2(video_source, video_dest)
        copied["video_path"] = str(video_dest)
        copied["video_url"] = f"/assets/letters/{slug}/final.mp4"

    visual_source = export_dir / "visual.png"
    if not visual_source.exists():
        visual_source = _resolve_artifact_path(release.get("assets", {}).get("visual_path", ""))
    if visual_source.exists() and visual_source.is_file():
        visual_dest = asset_dir / "visual.png"
        shutil.copy2(visual_source, visual_dest)
        copied["visual_path"] = str(visual_dest)
        copied["visual_url"] = f"/assets/letters/{slug}/visual.png"

    return copied


def _paragraph_html(paragraphs: List[str]) -> str:
    return "\n".join(f"          <p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)


def _questions_html(questions: List[str]) -> str:
    if not questions:
        return "          <p class=\"muted\">Reflection prompts are being prepared.</p>"

    cards = []
    for question in questions:
        cards.append(
            "          <article class=\"card\">\n"
            "            <div class=\"card-content\">\n"
            f"              <p class=\"card-text\">{html.escape(question)}</p>\n"
            "            </div>\n"
            "          </article>"
        )
    return "\n".join(cards)


def _render_letter_page(*, page: Dict[str, Any], canonical_url: str, media: Dict[str, str]) -> str:
    title = str(page["title"])
    description = str(page["description"])
    scripture = str(page["scripture"])
    visual_url = media.get("visual_url", "")
    video_url = media.get("video_url", "")
    poster_attr = f' poster="{html.escape(visual_url)}"' if visual_url else ""

    video_block = ""
    if video_url:
        video_block = (
            "      <section class=\"section\">\n"
            f"        <video controls preload=\"metadata\"{poster_attr} "
            "style=\"width:100%;border:1px solid var(--border);border-radius:8px;background:#000;\">\n"
            f"          <source src=\"{html.escape(video_url)}\" type=\"video/mp4\" />\n"
            "        </video>\n"
            "      </section>\n"
        )

    image_meta = f'  <meta property="og:image" content="{html.escape(visual_url)}" />\n' if visual_url else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} | Letters of Light</title>
  <meta name="description" content="{html.escape(description)}" />
  <link rel="canonical" href="{html.escape(canonical_url)}" />
  <meta property="og:title" content="{html.escape(title)} | Letters of Light" />
  <meta property="og:description" content="{html.escape(description)}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="{html.escape(canonical_url)}" />
  <meta property="og:site_name" content="Brendon Coleman" />
{image_meta}  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html.escape(title)} | Letters of Light" />
  <meta name="twitter:description" content="{html.escape(description)}" />
  <link rel="stylesheet" href="/assets/style.css" />
</head>
<body>
  <div class="site-shell">
    <header class="site-header">
      <div class="brand">
        <a href="/">Brendon R. Coleman</a>
        <span class="tag">Letters of Light</span>
      </div>
      <nav class="nav" aria-label="Primary">
        <a href="/">Home</a>
        <a href="/whitepapers/">Whitepapers</a>
        <a href="/services/">Services</a>
      </nav>
    </header>

    <main>
      <section class="hero">
        <div class="hero-content">
          <span class="section-kicker">Letters of Light</span>
          <h1 class="hero-title">{html.escape(title)}</h1>
          <p class="hero-subtitle">{html.escape(scripture)}</p>
        </div>
      </section>

{video_block}      <section class="section">
        <header class="section-header">
          <span class="section-kicker">Letter</span>
          <h2 class="section-title">Read The Letter</h2>
        </header>
        <div class="contact-box" style="text-align:left;">
{_paragraph_html(page["paragraphs"])}
        </div>
      </section>

      <section class="section">
        <header class="section-header">
          <span class="section-kicker">Reflect</span>
          <h2 class="section-title">Questions For The Reader</h2>
        </header>
        <div class="card-grid">
{_questions_html(page["questions"])}
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <div class="footer-nav">
        <a href="/">Home</a>
        <a href="/whitepapers/">Whitepapers</a>
        <a href="/services/">Services</a>
      </div>
      <div class="footer-meta">&copy; <span id="y"></span> Brendon R. Coleman</div>
    </footer>
  </div>

  <script>document.getElementById("y").textContent = new Date().getFullYear();</script>
</body>
</html>
"""


def _caption_with_url(text: str, canonical_url: str) -> str:
    text = text.strip()
    if not text:
        return canonical_url + "\n"
    return text + "\n\n" + canonical_url + "\n"


def _refresh_social_exports(letter_id: str, release: Dict[str, Any], canonical_url: str) -> None:
    d = _letter_dir(letter_id)
    export_dir = d / "release_export"
    routing = _read_json(d / "routing.json")
    letter = _read_json(d / "letter.json")

    facebook = routing.get("facebook", {})
    youtube = routing.get("youtube", {})
    x_payload = routing.get("x", {})

    fb_message = str(facebook.get("message", ""))
    hashtags = " ".join(str(tag) for tag in facebook.get("hashtags", []))
    instagram = "\n\n".join(part for part in (fb_message.strip(), hashtags.strip()) if part)

    tweets = [str(tweet).strip() for tweet in x_payload.get("tweets", []) if str(tweet).strip()]
    x_thread = "\n\n---\n\n".join(tweets)

    _write_text(export_dir / "facebook.txt", _caption_with_url(fb_message, canonical_url))
    _write_text(export_dir / "instagram.txt", _caption_with_url(instagram, canonical_url))
    _write_text(export_dir / "x_thread.txt", _caption_with_url(x_thread, canonical_url))
    _write_text(
        export_dir / "youtube_description.txt",
        _caption_with_url(str(youtube.get("description", "")), canonical_url),
    )

    manifest_path = export_dir / "asset_manifest.json"
    manifest = _read_json(manifest_path)
    if manifest:
        manifest["canonical_url"] = canonical_url
        manifest["letter_id"] = letter_id
        manifest["campaign_id"] = release.get("campaign_id")
        manifest.setdefault("files", {})["site"] = str(export_dir / "site.md")
        manifest["updated_at"] = _utc_now()
        if letter:
            manifest["video_path"] = letter.get("video_path", manifest.get("video_path", ""))
            manifest["visual_path"] = letter.get("visual_path", manifest.get("visual_path", ""))
        _write_json(manifest_path, manifest)


def publish_release_site(
    letter_id: str,
    *,
    site_root: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    d = _letter_dir(letter_id)
    release_path = d / "release.json"
    release = _read_json(release_path)
    if not release:
        raise RuntimeError(f"release.json not found for letter: {letter_id}")

    if not release.get("approved"):
        raise RuntimeError("Release must be approved before site publish")

    release_state = str(release.get("release_state", ""))
    if release_state not in PUBLISHABLE_STATES:
        raise RuntimeError("Release must be exported before site publish")

    export_dir = d / "release_export"
    site_md_path = export_dir / "site.md"
    if not site_md_path.exists():
        raise RuntimeError(f"release_export/site.md not found for letter: {letter_id}")

    site = resolve_site_root(site_root)
    slug = _page_slug(letter_id, release)
    canonical = _canonical_url(base_url, slug)
    media = _copy_media(export_dir, release, site, slug)

    markdown = site_md_path.read_text(encoding="utf-8")
    page = _parse_site_markdown(
        markdown,
        str(release.get("title") or "Letter of Light"),
        str(release.get("scripture_ref") or ""),
    )
    page_html = _render_letter_page(page=page, canonical_url=canonical, media=media)

    page_dir = site / "letters" / slug
    page_path = page_dir / "index.html"
    _write_text(page_path, page_html)

    _refresh_social_exports(letter_id, release, canonical)

    now = _utc_now()
    release["release_state"] = "published"
    release["canonical_url"] = canonical
    release["updated_at"] = now
    site_target = release.setdefault("targets", {}).setdefault("site", {})
    site_target.update(
        {
            "enabled": True,
            "status": "published",
            "url": canonical,
            "site_root": str(site),
            "page_path": str(page_path),
        }
    )
    release.setdefault("events", []).append(
        {
            "event_type": "ReleaseSitePublished",
            "created_at": now,
            "canonical_url": canonical,
            "page_path": str(page_path),
            "site_root": str(site),
        }
    )
    _write_json(release_path, release)

    return {
        "letter_id": letter_id,
        "canonical_url": canonical,
        "page_path": str(page_path),
        "site_root": str(site),
        "media": media,
        "updated_at": now,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.letters_of_light.release_site",
        description="Publish an exported Letters of Light release to the owned static site",
    )
    parser.add_argument("--letter-id", required=True)
    parser.add_argument("--site-root", default=None)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args(argv)

    result = publish_release_site(
        args.letter_id,
        site_root=args.site_root,
        base_url=args.base_url,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
