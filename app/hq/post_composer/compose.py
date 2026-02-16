"""
Post Composer — deterministic queue → HTML/MD/manifest staging.

Internal tooling only. No network calls. No external templates.
Deterministic output bytes. Fail-closed on ambiguity.
Atomic writes via temp-file + os.replace.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.hq.post_composer.queue_contract import SocialQueueV1, normalize_text

# Output root
_SOCIAL_OUT = Path("data/social_out")

# Template directory
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Template selection map: platform → template filename
_PLATFORM_TEMPLATES: Dict[str, str] = {
    "linkedin": "linkedin_post.html",
    "facebook": "facebook_post.html",
    "youtube": "youtube_description.html",
    "substack": "substack_post.html",
    "github": "",  # MD-only, no HTML template
}


def _sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """Compute SHA256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_template(platform: str) -> Optional[str]:
    """
    Load HTML template for platform. Returns None for github (MD-only).
    Fail-closed if template file missing.
    """
    tpl_name = _PLATFORM_TEMPLATES.get(platform)
    if tpl_name is None:
        raise ValueError(f"No template mapping for platform: '{platform}'")
    if tpl_name == "":
        return None  # github — MD-only

    tpl_path = _TEMPLATE_DIR / tpl_name
    if not tpl_path.exists():
        raise FileNotFoundError(
            f"Template not found: {tpl_path} (platform='{platform}')"
        )
    return tpl_path.read_text(encoding="utf-8")


def _body_to_html(body: str) -> str:
    """Escape HTML special chars and convert newlines to <br/>."""
    escaped = html.escape(body, quote=True)
    return escaped.replace("\n", "<br/>\n")


def _render_artifact_links_html(links: tuple) -> str:
    """Render artifact links as HTML list items."""
    items = []
    for link in links:
        label = html.escape(str(link.get("label", "")), quote=True)
        path = html.escape(str(link.get("path", "")), quote=True)
        items.append(f'    <li><a href="{path}">{label}</a></li>')
    return "\n".join(items)


def _render_paths_html(paths: tuple) -> str:
    """Render render_paths as HTML list items."""
    items = []
    for p in paths:
        escaped = html.escape(str(p), quote=True)
        items.append(f'    <li><code>{escaped}</code></li>')
    return "\n".join(items)


def _render_md(queue: SocialQueueV1) -> str:
    """Render Markdown post content. Deterministic, UTF-8, LF-only."""
    lines = []

    if queue.copy_headline:
        lines.append(f"# {queue.copy_headline}")
        lines.append("")

    lines.append(queue.copy_body)
    lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    for link in queue.artifact_links:
        label = link.get("label", "")
        path = link.get("path", "")
        lines.append(f"- [{label}]({path})")
    lines.append("")

    lines.append("## Renders")
    lines.append("")
    for rp in queue.render_paths:
        lines.append(f"- `{rp}`")
    lines.append("")

    return "\n".join(lines)


def _render_html(queue: SocialQueueV1, template: str) -> str:
    """Render HTML post using template. Deterministic, UTF-8, LF-only."""
    body_html = _body_to_html(queue.copy_body)
    artifact_links_html = _render_artifact_links_html(queue.artifact_links)
    render_paths_html = _render_paths_html(queue.render_paths)
    pack_footer = f"pack: {queue.pack_id} ({queue.pack_hash})"

    result = template.format(
        headline=html.escape(queue.copy_headline, quote=True),
        body_html=body_html,
        artifact_links_html=artifact_links_html,
        render_paths_html=render_paths_html,
        pack_footer=html.escape(pack_footer, quote=True),
    )
    # Normalize to LF
    return result.replace("\r\n", "\n")


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes atomically: temp file → os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp_path, str(path))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _check_idempotent(path: Path, new_bytes: bytes, *, force: bool) -> bool:
    """
    Check idempotency for an output file.
    Returns True if write should proceed, False if identical (skip).
    Raises ValueError if different and not force.
    """
    if not path.exists():
        return True  # New file — write

    existing = path.read_bytes()
    if existing == new_bytes:
        return False  # Identical — skip

    if not force:
        raise ValueError(
            f"Output exists with different content: {path}. "
            f"Use --force to overwrite."
        )
    return True  # Force overwrite


def compose_queue_item(
    queue_path: str,
    *,
    force: bool = False,
    out_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Compose a social queue item into HTML/MD/manifest.

    Steps:
    1. Load JSON queue item
    2. Validate with SocialQueueV1
    3. Verify render_paths exist
    4. Select template
    5. Compute output directory
    6. Render HTML + MD
    7. Build manifest with SHA256 hashes
    8. Write atomically with idempotency check

    Returns summary dict with output paths.
    """
    # 1. Load JSON
    queue_file = Path(queue_path)
    if not queue_file.exists():
        raise FileNotFoundError(f"Queue file not found: {queue_path}")

    with open(queue_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 2. Validate
    queue = SocialQueueV1.from_dict(raw)

    # 3. Verify render_paths
    queue.validate_render_paths()

    # 4. Select template
    template = _load_template(queue.platform)

    # 5. Output directory
    base = out_root or _SOCIAL_OUT
    out_dir = base / queue.lane / queue.platform / queue.queue_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 6. Render content
    md_content = _render_md(queue)
    md_bytes = md_content.encode("utf-8")
    md_path = out_dir / "post.md"

    html_bytes: Optional[bytes] = None
    html_path: Optional[Path] = None
    if template is not None:
        html_content = _render_html(queue, template)
        html_bytes = html_content.encode("utf-8")
        html_path = out_dir / "post.html"

    # 7. Build manifest
    manifest_data: Dict[str, Any] = {
        "manifest_version": "signal_manifest_v1",
        "queue_id": queue.queue_id,
        "meme_id": queue.meme_id,
        "lane": queue.lane,
        "platform": queue.platform,
        "intent": queue.intent,
        "pack": {
            "pack_id": queue.pack_id,
            "pack_hash": queue.pack_hash,
        },
        "rendered": {
            "md_sha256": _sha256_bytes(md_bytes),
        },
        "provenance": {
            "source_artifact_id": queue.source_artifact_id,
            "session_id": queue.session_id,
            "created_at_utc": queue.created_at_utc,
        },
    }

    if html_bytes is not None:
        manifest_data["rendered"]["html_sha256"] = _sha256_bytes(html_bytes)

    # Serialize manifest deterministically (sorted keys, 2-space indent, LF)
    manifest_str = json.dumps(manifest_data, sort_keys=True, indent=2, ensure_ascii=False)
    manifest_str = manifest_str.replace("\r\n", "\n") + "\n"
    manifest_bytes = manifest_str.encode("utf-8")
    manifest_data["rendered"]["manifest_sha256"] = _sha256_bytes(manifest_bytes)

    # Re-serialize with manifest hash included
    manifest_str = json.dumps(manifest_data, sort_keys=True, indent=2, ensure_ascii=False)
    manifest_str = manifest_str.replace("\r\n", "\n") + "\n"
    manifest_bytes = manifest_str.encode("utf-8")

    manifest_path = out_dir / "manifest.json"

    # 8. Write with idempotency checks
    result: Dict[str, Any] = {
        "queue_path": str(queue_file),
        "queue_id": queue.queue_id,
        "out_dir": str(out_dir),
        "md_path": str(md_path),
        "manifest_path": str(manifest_path),
        "skipped_files": [],
        "written_files": [],
    }

    # MD
    if _check_idempotent(md_path, md_bytes, force=force):
        _atomic_write(md_path, md_bytes)
        result["written_files"].append(str(md_path))
    else:
        result["skipped_files"].append(str(md_path))

    # HTML
    if html_bytes is not None and html_path is not None:
        result["html_path"] = str(html_path)
        if _check_idempotent(html_path, html_bytes, force=force):
            _atomic_write(html_path, html_bytes)
            result["written_files"].append(str(html_path))
        else:
            result["skipped_files"].append(str(html_path))

    # Manifest
    if _check_idempotent(manifest_path, manifest_bytes, force=force):
        _atomic_write(manifest_path, manifest_bytes)
        result["written_files"].append(str(manifest_path))
    else:
        result["skipped_files"].append(str(manifest_path))

    return result
