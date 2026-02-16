"""
Queue Contract: social_queue_v1 — strict, deterministic, fail-closed.

Defines the SocialQueueV1 frozen dataclass with strict validation.
All failures raise ValueError. No silent defaults.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

QUEUE_VERSION_CANONICAL = "social_queue_v1"

VALID_LANES = frozenset({"artifact_channel", "human_channel"})
VALID_PLATFORMS = frozenset({"linkedin", "substack", "github", "facebook", "youtube"})
VALID_INTENTS = frozenset({"post", "description", "thread"})

# Repo root for path resolution
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def normalize_text(s: str) -> str:
    """Collapse CRLF → LF, strip trailing spaces per line, strip trailing newlines."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in s.split("\n")]
    return "\n".join(lines).rstrip("\n")


def safe_slug(s: str, *, max_len: int = 64) -> str:
    """
    Deterministic filename slug: lowercase, dash-separated, max 64 chars.
    Non-alphanumeric → dash, collapse runs, strip leading/trailing dashes.
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len]


def ensure_file_exists(path_str: str) -> Path:
    """
    Resolve path relative to repo root. Deny path traversal.
    Raises ValueError if file does not exist or escapes repo root.
    """
    raw = Path(path_str)
    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        resolved = (_REPO_ROOT / raw).resolve()

    # Deny path traversal
    try:
        resolved.relative_to(_REPO_ROOT.resolve())
    except ValueError:
        raise ValueError(
            f"Path traversal denied: '{path_str}' resolves outside repo root"
        )

    if not resolved.exists():
        raise ValueError(f"File does not exist: '{path_str}' (resolved: {resolved})")

    return resolved


def _require_str(data: Dict[str, Any], key: str, context: str = "") -> str:
    """Extract a required non-empty string from dict."""
    val = data.get(key)
    if val is None:
        raise ValueError(f"Missing required field: '{key}'{context}")
    if not isinstance(val, str):
        raise ValueError(f"Field '{key}' must be a string, got {type(val).__name__}{context}")
    if not val.strip():
        raise ValueError(f"Field '{key}' must be non-empty{context}")
    return val


def _require_list(data: Dict[str, Any], key: str, context: str = "") -> list:
    """Extract a required non-empty list from dict."""
    val = data.get(key)
    if val is None:
        raise ValueError(f"Missing required field: '{key}'{context}")
    if not isinstance(val, list):
        raise ValueError(f"Field '{key}' must be a list, got {type(val).__name__}{context}")
    if len(val) == 0:
        raise ValueError(f"Field '{key}' must be non-empty{context}")
    return val


def _require_dict(data: Dict[str, Any], key: str, context: str = "") -> dict:
    """Extract a required dict from dict."""
    val = data.get(key)
    if val is None:
        raise ValueError(f"Missing required field: '{key}'{context}")
    if not isinstance(val, dict):
        raise ValueError(f"Field '{key}' must be a dict, got {type(val).__name__}{context}")
    return val


def _compute_queue_id(data: Dict[str, Any]) -> str:
    """
    Deterministic queue_id from content fields.
    sha256(queue_version + lane + platform + intent +
           normalized(headline+body) + sorted(render_paths) +
           sorted(artifact_links by label+path))[:12]
    """
    copy_data = data.get("copy", {})
    headline = copy_data.get("headline", "")
    body = copy_data.get("body", "")

    render_paths = sorted(data.get("render_paths", []))
    artifact_links = data.get("artifact_links", [])
    sorted_links = sorted(artifact_links, key=lambda x: (x.get("label", ""), x.get("path", "")))
    links_str = "|".join(f"{a.get('label','')}/{a.get('path','')}" for a in sorted_links)

    canon = (
        data.get("queue_version", "")
        + data.get("lane", "")
        + data.get("platform", "")
        + data.get("intent", "")
        + data.get("meme_id", "")
        + normalize_text(headline + body)
        + "|".join(render_paths)
        + links_str
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class SocialQueueV1:
    """Strict, immutable queue contract for social signal pipeline."""

    queue_version: str
    queue_id: str
    lane: str
    platform: str
    intent: str
    meme_id: str
    render_paths: tuple  # tuple[str, ...]
    artifact_links: tuple  # tuple[dict, ...]
    copy_headline: str
    copy_body: str
    pack_id: str
    pack_hash: str
    source_artifact_id: str
    session_id: str
    created_at_utc: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SocialQueueV1":
        """
        Construct and validate from raw dict (loaded from JSON).
        Fail-closed on any missing or invalid field.
        """
        # 1. queue_version
        qv = _require_str(data, "queue_version")
        if qv != QUEUE_VERSION_CANONICAL:
            raise ValueError(
                f"Invalid queue_version: '{qv}'. Must be '{QUEUE_VERSION_CANONICAL}'"
            )

        # 2. lane
        lane = _require_str(data, "lane")
        if lane not in VALID_LANES:
            raise ValueError(f"Invalid lane: '{lane}'. Must be one of {sorted(VALID_LANES)}")

        # 3. platform
        platform = _require_str(data, "platform")
        if platform not in VALID_PLATFORMS:
            raise ValueError(
                f"Invalid platform: '{platform}'. Must be one of {sorted(VALID_PLATFORMS)}"
            )

        # 4. intent
        intent = _require_str(data, "intent")
        if intent not in VALID_INTENTS:
            raise ValueError(
                f"Invalid intent: '{intent}'. Must be one of {sorted(VALID_INTENTS)}"
            )

        # 5. meme_id
        meme_id = _require_str(data, "meme_id")

        # 6. render_paths
        render_paths_list = _require_list(data, "render_paths")
        for i, rp in enumerate(render_paths_list):
            if not isinstance(rp, str) or not rp.strip():
                raise ValueError(f"render_paths[{i}] must be a non-empty string")

        # 7. artifact_links
        artifact_links_list = _require_list(data, "artifact_links")
        for i, al in enumerate(artifact_links_list):
            if not isinstance(al, dict):
                raise ValueError(f"artifact_links[{i}] must be a dict")
            if "label" not in al or "path" not in al:
                raise ValueError(f"artifact_links[{i}] must have 'label' and 'path'")

        # 8. copy
        copy_data = _require_dict(data, "copy")
        headline = copy_data.get("headline")
        if headline is None:
            raise ValueError("Missing required field: 'copy.headline'")
        if not isinstance(headline, str):
            raise ValueError(f"'copy.headline' must be a string, got {type(headline).__name__}")
        body = _require_str(copy_data, "body", context=" in 'copy'")

        # 9. pack
        pack_data = _require_dict(data, "pack")
        pack_id = _require_str(pack_data, "pack_id", context=" in 'pack'")
        pack_hash = _require_str(pack_data, "pack_hash", context=" in 'pack'")

        # 10. provenance
        prov = _require_dict(data, "provenance")
        source_artifact_id = _require_str(prov, "source_artifact_id", context=" in 'provenance'")
        session_id = _require_str(prov, "session_id", context=" in 'provenance'")
        created_at_utc = _require_str(prov, "created_at_utc", context=" in 'provenance'")

        # 11. queue_id: use provided if valid, else compute
        raw_qid = data.get("queue_id")
        if isinstance(raw_qid, str) and len(raw_qid) == 12:
            try:
                int(raw_qid, 16)
                queue_id = raw_qid
            except ValueError:
                queue_id = _compute_queue_id(data)
        else:
            queue_id = _compute_queue_id(data)

        return SocialQueueV1(
            queue_version=qv,
            queue_id=queue_id,
            lane=lane,
            platform=platform,
            intent=intent,
            meme_id=meme_id,
            render_paths=tuple(sorted(render_paths_list)),
            artifact_links=tuple(
                sorted(artifact_links_list, key=lambda x: (x.get("label", ""), x.get("path", "")))
            ),
            copy_headline=normalize_text(headline),
            copy_body=normalize_text(body),
            pack_id=pack_id,
            pack_hash=pack_hash,
            source_artifact_id=source_artifact_id,
            session_id=session_id,
            created_at_utc=created_at_utc,
        )

    def validate_render_paths(self) -> None:
        """Verify all render_paths exist on disk. Fail-closed."""
        for rp in self.render_paths:
            ensure_file_exists(rp)
