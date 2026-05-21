"""
shared/state_registry.py — Minimal append-only artifact state registry.

Writes to: data/state/artifact_registry.jsonl
(resolved from repo root via SIGNAL_AGENT_ROOT env var or file-relative heuristic)

Per-line schema:
  {
    "artifact_id": str,
    "state":       str,
    "path":        str,
    "updated_at":  str   # ISO-8601 UTC
  }

Public API:
    record_state(artifact_id, state, path, registry_path=None) -> None
    get_state(artifact_id, registry_path=None) -> dict | None

Design constraints:
  - Append-only; never rewrites existing lines
  - No indexing, no DB, no optimization
  - Default registry path is ALWAYS under data/state/ (not beside capture dir)
    to satisfy TestCaptureDoesNotTouchArtifactRegistry
  - registry_path kwarg allows explicit override for isolated tests
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.utils.io_contract import append_jsonl_atomic


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_root() -> Path:
    """Resolve repo root. Reads SIGNAL_AGENT_ROOT env var, follows existing pattern."""
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    # Walk up from this file: shared/ -> repo root
    return Path(__file__).resolve().parent.parent


def _default_registry_path() -> Path:
    return _get_root() / "data" / "state" / "artifact_registry.jsonl"


def _normalize_artifact_fact(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("current_state", record.get("state"))
    normalized.setdefault("artifact_path", record.get("path"))
    return normalized


def record_state(
    artifact_id: str,
    state: str,
    path: str,
    registry_path: Optional[Path] = None,
) -> None:
    """
    Append one state record to the registry.

    Args:
        artifact_id:   Stable identity for the artifact (run_id, cluster_id, etc.)
        state:         Lifecycle state string ("captured", "promoted", "routed", ...)
        path:          Absolute or relative path to the artifact file on disk
        registry_path: Override path for tests (default: data/state/artifact_registry.jsonl)
    """
    target = registry_path or _default_registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "artifact_id": artifact_id,
        "state": state,
        "path": path,
        "updated_at": _utc_now(),
    }
    append_jsonl_atomic(target, entry)


def get_state(
    artifact_id: str,
    registry_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Return the most recent state record for the given artifact_id, or None.

    Linear scan from the end of file; returns the last matching entry.
    Malformed lines are silently skipped.

    Args:
        artifact_id:   Artifact identity to look up
        registry_path: Override path for tests
    """
    target = registry_path or _default_registry_path()
    if not target.exists():
        return None

    last_match: Optional[dict] = None
    try:
        for raw_line in target.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if entry.get("artifact_id") == artifact_id:
                last_match = entry
    except OSError:
        return None

    return last_match


def list_latest_states(
    registry_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """
    Return the latest append-only registry row for each artifact_id.

    Records preserve file-order recency: later rows win.
    Malformed lines and rows without a valid artifact_id are skipped.
    """
    target = registry_path or _default_registry_path()
    if not target.exists():
        return []

    latest_by_artifact: dict[str, dict[str, Any]] = {}
    latest_index: dict[str, int] = {}

    try:
        with open(target, "r", encoding="utf-8") as handle:
            for index, raw_line in enumerate(handle):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                artifact_id = entry.get("artifact_id")
                if not isinstance(artifact_id, str) or not artifact_id:
                    continue
                latest_by_artifact[artifact_id] = entry
                latest_index[artifact_id] = index
    except OSError:
        return []

    return sorted(
        latest_by_artifact.values(),
        key=lambda rec: latest_index.get(str(rec.get("artifact_id")), -1),
    )


def list_latest_artifact_facts(
    registry_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """
    Return the latest canonical artifact-state rows normalized to the
    memory/graph artifact-fact shape.
    """
    return [
        _normalize_artifact_fact(record)
        for record in list_latest_states(registry_path=registry_path)
    ]
