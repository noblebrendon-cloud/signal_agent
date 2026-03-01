"""OIL → Interaction Signals bridge (v0.1).

Converts an OIL incident artifact (the JSON envelope written by reporter.py)
into a sequence of Event objects suitable for process_event().

Mapping:
  actor_id:  "system:<origin_service>" for the hypothesized root cause,
             "oncall"                  for the human narrative block
  thread_id: run_id (incident identifier)
  channel:   "oil"
  text:      assembled from the most informative fields in the report

Typical usage:
    from signal_agent.leviathan.interaction_signals.oil_bridge import events_from_artifact
    from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
    from pathlib import Path

    store   = StateStore()
    events  = events_from_artifact(Path("oil/artifacts/incident_xxx.json"))
    results = [process_event(ev, store) for ev in events]
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from .core.types import Event


# ─── helpers ──────────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int = 600) -> str:
    """Truncate to max_chars with ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " …"


def _join(*parts: str) -> str:
    """Join non-empty parts with single space."""
    return " ".join(p.strip() for p in parts if p and p.strip())


def _safe_str(obj: Any) -> str:
    """Convert arbitrary JSON value to a clean string."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, list):
        return "; ".join(_safe_str(x) for x in obj[:6])
    if isinstance(obj, dict):
        return " ".join(f"{k}={_safe_str(v)}" for k, v in list(obj.items())[:6])
    return str(obj)


# ─── text assembly ─────────────────────────────────────────────────────────────

def _make_system_text(report: dict) -> str:
    """
    Build the 'system actor' text from machine-readable report fields:
    top_ranked_cause, evidence, business_effect, recommended_human_action.
    """
    parts = []
    tc = report.get("top_ranked_cause", "")
    if tc:
        parts.append(f"Top cause: {_safe_str(tc)}.")
    be = report.get("business_effect", "")
    if be:
        parts.append(f"Business effect: {_safe_str(be)}.")
    evid = report.get("evidence", [])
    if evid:
        ev_text = "; ".join(
            _safe_str(e.get("description", e)) for e in (evid[:3] if isinstance(evid, list) else [])
        )
        if ev_text:
            parts.append(f"Evidence: {ev_text}.")
    rec = report.get("recommended_human_action", "")
    if rec:
        parts.append(f"Recommendation: {_safe_str(rec)}.")
    return _truncate(_join(*parts))


def _make_oncall_text(report: dict) -> str:
    """
    Build the 'oncall actor' text from the human narrative block.
    human_readable_block or top_ranked_cause + similar_incidents narrative.
    """
    parts = []
    hrb = report.get("human_readable_block", "")
    if hrb:
        parts.append(_safe_str(hrb))
    else:
        # Fall back: incident summary from primary impact + hypotheses
        pi = report.get("primary_impact", "")
        if pi:
            parts.append(f"Incident impact: {_safe_str(pi)}.")
        hyps = report.get("hypotheses", [])
        if isinstance(hyps, list) and hyps:
            top = hyps[0]
            if isinstance(top, dict):
                parts.append(
                    f"Leading hypothesis: {_safe_str(top.get('suspected_origin', ''))} "
                    f"confidence={_safe_str(top.get('score', ''))}."
                )
    sim = report.get("similar_incidents", {})
    if isinstance(sim, dict):
        count = sim.get("total_similar", 0)
        if count:
            parts.append(f"Similar past incidents: {count}.")
        ex = sim.get("recent_examples", [])
        if isinstance(ex, list) and ex:
            parts.append(f"Prior example: {_safe_str(ex[0])}.")
    return _truncate(_join(*parts)) if parts else "Incident processed by OIL pipeline."


# ─── public API ───────────────────────────────────────────────────────────────

def events_from_artifact(artifact_path: Path) -> list[Event]:
    """
    Parse an OIL incident artifact JSON file and return 1–2 Event objects:

    1. system:<origin_service> event — the machine diagnosis text
    2. oncall event — the operator-facing narrative text (if non-empty)

    Returns an empty list if the artifact is malformed.
    """
    try:
        envelope = json.loads(artifact_path.read_bytes())
    except Exception:
        return []

    run_id     = envelope.get("run_id", artifact_path.stem)
    created_utc = envelope.get("created_utc", "1970-01-01T00:00:00Z")
    report     = envelope.get("report", {})
    if not isinstance(report, dict):
        return []

    origin_service = report.get("origin_service", "unknown")
    # Flatten compound origin_id e.g. "payment:deploy:abc" → "payment"
    if ":" in origin_service:
        origin_service = origin_service.split(":")[0]

    events: list[Event] = []

    # ── Event 1: system actor (machine analysis) ──────────────────────────
    sys_text = _make_system_text(report)
    events.append(Event(
        event_id=f"{run_id}:sys",
        actor_id=f"system:{origin_service}",
        thread_id=run_id,
        timestamp=created_utc,
        text=sys_text,
        meta={
            "channel":      "oil",
            "artifact_path": str(artifact_path),
            "run_id":        run_id,
            "origin_service": origin_service,
            "source":        "system_diagnosis",
        },
    ))

    # ── Event 2: oncall actor (human-readable narrative) ──────────────────
    oncall_text = _make_oncall_text(report)
    if oncall_text:
        events.append(Event(
            event_id=f"{run_id}:oncall",
            actor_id="oncall",
            thread_id=run_id,
            timestamp=created_utc,
            text=oncall_text,
            meta={
                "channel":       "oil",
                "artifact_path": str(artifact_path),
                "run_id":        run_id,
                "source":        "oncall_narrative",
                "reply_to":      sys_text[:200],  # scope: reply context
            },
        ))

    return events


def events_from_artifacts_dir(
    artifacts_dir: Path,
    max_artifacts: int = 50,
) -> list[Event]:
    """
    Enumerate incident_*.json files in artifacts_dir and convert all to Events.
    Sorted deterministically by filename (= by timestamp in the naming scheme).
    Returns flat list of Events ordered artifact-by-artifact.
    """
    files = sorted(artifacts_dir.glob("incident_*.json"))[:max_artifacts]
    all_events: list[Event] = []
    for f in files:
        all_events.extend(events_from_artifact(f))
    return all_events
