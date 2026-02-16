"""
Artifact Registry — auto-ingest for rendered meme artifacts.

Appends entries to artifact_registry.jsonl after successful render.
Idempotent: deduplicates by artifact_id.
File-locked during write (Unix) or fallback (Windows).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Platform-safe locking
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


REGISTRY_PATH = Path("data/meme_offload/artifact_registry.jsonl")


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 of a file's contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_existing_ids(registry: Path) -> set:
    """Load existing artifact IDs from registry to prevent duplicates."""
    ids: set = set()
    if not registry.exists():
        return ids
    with open(registry, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ids.add(entry.get("artifact_id", ""))
            except json.JSONDecodeError:
                continue
    return ids


def ingest_artifact(
    rendered_path: Path,
    pack_id: str,
    pack_hash: str,
    meme_id: str,
    *,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Ingest a rendered artifact into the registry.

    Steps:
    1. Compute SHA256 of output file
    2. Canonical rename: <stem>__<hash12>.<ext>
    3. Append entry to artifact_registry.jsonl (idempotent, locked)

    Returns: the registry entry dict.
    """
    reg = registry_path or REGISTRY_PATH
    reg.parent.mkdir(parents=True, exist_ok=True)

    # 1. Compute hash
    file_hash = _compute_file_hash(rendered_path)
    hash12 = file_hash[:12]

    # 2. Canonical rename
    stem = rendered_path.stem
    ext = rendered_path.suffix
    canonical_name = f"{stem}__{hash12}{ext}"
    canonical_path = rendered_path.parent / canonical_name

    if not canonical_path.exists():
        shutil.copy2(str(rendered_path), str(canonical_path))

    # 3. Build entry
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "artifact_type": "meme_render",
        "artifact_id": hash12,
        "meme_id": meme_id,
        "path": str(canonical_path),
        "file_hash": f"sha256:{file_hash}",
        "pack_id": pack_id,
        "pack_hash": pack_hash,
        "created_at": now_utc,
    }

    # 4. Append (idempotent, with optional locking)
    _append_if_new(reg, entry, hash12)

    return entry


def _append_if_new(registry: Path, entry: Dict[str, Any], artifact_id: str) -> None:
    """Append entry to JSONL registry only if artifact_id is not present."""
    registry.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing
    existing_ids = _load_existing_ids(registry)
    if artifact_id in existing_ids:
        return  # Already exists — idempotent

    # Append with optional file locking
    with open(registry, "a", encoding="utf-8") as f:
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
