"""
Social Signal Pipeline — internal automation hook.

Produces platform-ready payloads for social signaling.
NO network calls. Internal queue only.
Writes to: data/social_queue/<platform>/<timestamp>_<meme_id>.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.meme_offload.schema import MemeSpecV1

SOCIAL_QUEUE_DIR = Path("data/social_queue")
SUPPORTED_PLATFORMS = frozenset({"reddit", "linkedin", "youtube"})


def schedule_meme_signal(
    meme_spec: MemeSpecV1,
    platform: str,
    *,
    queue_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Schedule a meme for social signaling. Internal use only.

    Produces a platform-ready text payload + image path.
    Writes to: data/social_queue/<platform>/<timestamp>_<meme_id>.json

    No network calls. No direct posting.

    Returns: the queue entry dict.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform: '{platform}'. "
            f"Must be one of: {sorted(SUPPORTED_PLATFORMS)}"
        )

    base = queue_dir or SOCIAL_QUEUE_DIR
    platform_dir = base / platform
    platform_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y%m%dT%H%M%SZ")

    # Build platform-ready payload
    payload = _build_payload(meme_spec, platform, now_utc)

    # Write queue file
    filename = f"{ts}_{meme_spec.meme_id}.json"
    queue_path = platform_dir / filename

    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True, indent=2)

    return payload


def _build_payload(
    spec: MemeSpecV1,
    platform: str,
    now_utc: datetime,
) -> Dict[str, Any]:
    """Build platform-specific payload from meme spec."""
    # Extract text content
    text_content = ""
    if hasattr(spec.text, "top") and hasattr(spec.text, "bottom"):
        text_content = f"{spec.text.top}\n{spec.text.bottom}"
    elif hasattr(spec.text, "title") and hasattr(spec.text, "bullets"):
        bullets = "\n".join(f"• {b}" for b in spec.text.bullets)
        text_content = f"{spec.text.title}\n{bullets}"

    # Determine render path
    render_dir = spec.output.render_dir
    render_file = spec.output.filename
    render_path = str(Path(render_dir) / render_file)

    return {
        "platform": platform,
        "meme_id": spec.meme_id,
        "spec_version": spec.spec_version,
        "pack_id": spec.pack.pack_id,
        "pack_hash": spec.pack.pack_hash,
        "text_content": text_content,
        "image_path": render_path,
        "render_mode": spec.render_mode,
        "format": spec.format,
        "scheduled_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "queued",
        "internal_only": True,
    }
