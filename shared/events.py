"""
shared/events.py — Minimal typed event emitter.

Appends to: data/state/event_log.jsonl
(resolved from repo root via SIGNAL_AGENT_ROOT env var)

Per-line schema:
  {
    "event_type":  str,
    "artifact_id": str,
    "timestamp":   str,   # ISO-8601 UTC
    "payload":     dict
  }

Public API:
    emit_event(event_type, artifact_id, payload, event_log_path=None) -> None

Design constraints:
  - Best-effort only — never raises, all errors silently swallowed
  - event_log_path kwarg allows explicit override for isolated tests
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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


def _default_event_log_path() -> Path:
    return _get_root() / "data" / "state" / "event_log.jsonl"


def emit_event(
    event_type: str,
    artifact_id: str,
    payload: Dict[str, Any],
    event_log_path: Optional[Path] = None,
) -> None:
    """
    Emit a typed event to the event log. Best-effort — never raises.

    Args:
        event_type:     Event name string, e.g. "PromotionSucceeded"
        artifact_id:    Artifact identity the event pertains to
        payload:        Event-type-specific fields dict
        event_log_path: Override path for tests (default: data/state/event_log.jsonl)
    """
    try:
        target = event_log_path or _default_event_log_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "event_type": event_type,
            "artifact_id": artifact_id,
            "timestamp": _utc_now(),
            "payload": payload if payload is not None else {},
        }
        serializable_entry = json.loads(json.dumps(entry, ensure_ascii=False, default=str))
        append_jsonl_atomic(target, serializable_entry)
    except Exception:
        # Best-effort: never raise from event emission
        pass
