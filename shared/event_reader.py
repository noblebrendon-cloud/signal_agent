"""
shared/event_reader.py — Minimal event log reader with checkpoint-based deduplication.

Public API:
    read_events(event_log_path=None, event_type=None, limit=None) -> list[dict]
    iter_unprocessed_events(checkpoint_path, event_log_path=None, event_type=None) -> list[dict]
    mark_event_processed(event_id: str, checkpoint_path) -> None

Event IDs:
    Events are identified by `event_id` if present in the schema, or derived
    deterministically as sha256(event_type|artifact_id|timestamp)[:16].
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def _default_event_log_path() -> Path:
    return _get_root() / "data" / "state" / "event_log.jsonl"


def _derive_event_id(event: Dict[str, Any]) -> str:
    """
    Return the event's own event_id if present, otherwise derive one
    deterministically from event_type|artifact_id|timestamp.
    """
    if "event_id" in event:
        return str(event["event_id"])
    raw = "|".join([
        str(event.get("event_type", "")),
        str(event.get("artifact_id", "")),
        str(event.get("timestamp", "")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def read_events(
    event_log_path: Optional[Path] = None,
    event_type: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Read events from event_log.jsonl in chronological order.

    Args:
        event_log_path: Override path (defaults to data/state/event_log.jsonl)
        event_type:     If set, filter to exact event_type matches only
        limit:          Return only the most recent N matching events

    Returns:
        List of event dicts, chronological order, malformed lines skipped.
    """
    target = event_log_path or _default_event_log_path()
    if not target.exists():
        return []

    try:
        raw_lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    events: List[Dict[str, Any]] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type is None or entry.get("event_type") == event_type:
            events.append(entry)

    if limit is not None:
        events = events[-limit:]

    return events


def _load_checkpoint(checkpoint_path: Path) -> Dict[str, Any]:
    """Load checkpoint file, returning empty structure on any failure."""
    if not checkpoint_path.exists():
        return {"processed_event_ids": []}
    try:
        raw = checkpoint_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"processed_event_ids": []}
        if "processed_event_ids" not in data:
            data["processed_event_ids"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"processed_event_ids": []}


def iter_unprocessed_events(
    checkpoint_path: Path,
    event_log_path: Optional[Path] = None,
    event_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return events that have not yet been processed (not listed in checkpoint).

    Args:
        checkpoint_path:  Path to checkpoint JSON file
        event_log_path:   Override path for event log
        event_type:       If set, filter to exact event_type matches only

    Returns:
        List of unprocessed event dicts in chronological order.
    """
    checkpoint = _load_checkpoint(checkpoint_path)
    processed_ids = set(checkpoint.get("processed_event_ids", []))

    all_events = read_events(event_log_path=event_log_path, event_type=event_type)
    return [
        e for e in all_events
        if _derive_event_id(e) not in processed_ids
    ]


def mark_event_processed(event_id: str, checkpoint_path: Path) -> None:
    """
    Record event_id as processed in the checkpoint file.

    Fails silently if the checkpoint cannot be written, ensuring
    the caller's main logic is never blocked by checkpoint I/O.
    """
    try:
        checkpoint = _load_checkpoint(checkpoint_path)
        ids: list = checkpoint.setdefault("processed_event_ids", [])
        if event_id not in ids:
            ids.append(event_id)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # Best-effort; never crash the caller
