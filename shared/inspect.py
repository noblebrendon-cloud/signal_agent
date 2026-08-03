"""
shared/inspect.py — Artifact inspection utility.

Reads the state registry and event log to answer:
  - What is the current known state of artifact X?
  - What events have been emitted for artifact X recently?

Public API:
    artifact_status(artifact_id, registry_path=None, event_log_path=None) -> dict
    recent_events(artifact_id, limit=10, event_log_path=None) -> list[dict]
"""
from __future__ import annotations

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


def artifact_status(
    artifact_id: str,
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Return the current known state for an artifact.

    Returns:
        {
            "artifact_id": str,
            "state": str | None,
            "path": str | None,
            "updated_at": str | None,
            "found": bool,
        }
    """
    try:
        from shared.state_registry import get_state
        entry = get_state(artifact_id, registry_path=registry_path)
    except Exception:
        entry = None

    if entry:
        return {
            "artifact_id": artifact_id,
            "state": entry.get("state"),
            "path": entry.get("path"),
            "updated_at": entry.get("updated_at"),
            "found": True,
        }

    return {
        "artifact_id": artifact_id,
        "state": None,
        "path": None,
        "updated_at": None,
        "found": False,
    }


def coherence_status(
    artifact_id: str,
    expected_state: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Programmatic entrypoint to check coherence status of an artifact.
    """
    from shared.coherence import check_artifact_coherence
    return check_artifact_coherence(artifact_id, expected_state, expected_hash=None, registry_path=registry_path)


def artifact_truth(
    artifact_id: str,
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Single artifact truth report unifying registry state, physical coherence, and history.
    """
    status = artifact_status(artifact_id, registry_path=registry_path)
    events = recent_events(artifact_id, limit=50, event_log_path=event_log_path)
    
    reg_state = status.get("state")
    coh = coherence_status(artifact_id, expected_state=reg_state, registry_path=registry_path)
    
    from shared.authority import evaluate_authority
    # Re-use known structures
    entry = None
    if status.get("found"):
        entry = {"state": status.get("state"), "path": status.get("path"), "updated_at": status.get("updated_at")}
    
    authority_eval = evaluate_authority(
        artifact_id=artifact_id,
        expected_state=reg_state,
        registry_entry=entry,
        coherence_result=coh,
        recent_events=events,
    )
    
    return {
        "artifact_id": artifact_id,
        "registry": {
            "found": status.get("found", False),
            "state": status.get("state"),
            "path": status.get("path"),
            "updated_at": status.get("updated_at"),
        },
        "coherence": coh,
        "authority": authority_eval,
        "events": events,
        "summary": {
            "known": status.get("found", False),
            "coherent": coh.get("coherent", False),
            "event_count": len(events),
        },
    }


def health_status(
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
    checkpoint_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return the canonical system health report through the inspection API."""
    from shared.health import system_health_report

    return system_health_report(
        registry_path=registry_path,
        event_log_path=event_log_path,
        checkpoint_path=checkpoint_path,
    )


def recent_events(
    artifact_id: str,
    limit: int = 10,
    event_log_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Return the last `limit` events for the given artifact_id.

    Events are returned in chronological order (oldest-first within the result set).
    Malformed lines are silently skipped.

    Args:
        artifact_id:    Artifact identity to filter on
        limit:          Maximum number of events to return
        event_log_path: Override path for tests

    Returns:
        List of event dicts matching artifact_id, capped at `limit`.
    """
    target = event_log_path or _default_event_log_path()
    if not target.exists():
        return []

    try:
        raw_lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    matches: List[Dict[str, Any]] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("artifact_id") == artifact_id:
            matches.append(entry)

    # Return the last `limit` matching events (most recent, in order)
    return matches[-limit:]
