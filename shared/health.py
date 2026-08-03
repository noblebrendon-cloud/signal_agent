"""
shared/health.py — System Health Report Layer.

Unifies existing system truth into one structured report summarizing:
1. reconciliation issues
2. recent coherence failures
3. blocked/failed transitions
4. unprocessed events
5. artifact counts by state
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from shared.state_registry import _default_registry_path
from shared.events import _default_event_log_path
from shared.reconcile import reconciliation_report
from shared.event_reader import read_events, iter_unprocessed_events


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def _default_checkpoint_path() -> Path:
    return _get_root() / "data" / "state" / "reaction_checkpoint.json"


def _default_routing_log_path() -> Path:
    override = os.environ.get("CAPTURE_DIR")
    if override:
        return Path(override) / "routing_log.jsonl"
    return _get_root() / "data" / "capture" / "routing_log.jsonl"


def system_health_report(
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
    checkpoint_path: Optional[Path] = None,
) -> Dict[str, Any]:
    reg_target = registry_path or _default_registry_path()
    evt_target = event_log_path or _default_event_log_path()
    ckpt_target = checkpoint_path or _default_checkpoint_path()
    
    # ---------------------------------------------------------
    # 1. Artifact Counts by State (latest known state)
    # ---------------------------------------------------------
    latest_states: Dict[str, str] = {}
    if reg_target.exists():
        try:
            for line in reg_target.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if "artifact_id" in entry and "state" in entry:
                        latest_states[entry["artifact_id"]] = entry["state"]
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
            
    known_buckets = {"captured", "promoted", "routed"}
    counts = {
        "captured": 0,
        "promoted": 0,
        "routed": 0,
        "unknown": 0,
    }
    
    for aid, st in latest_states.items():
        if st in known_buckets:
            counts[st] += 1
        else:
            counts["unknown"] += 1
            
    # ---------------------------------------------------------
    # 2. Reconciliation Issues
    # ---------------------------------------------------------
    recon = reconciliation_report(registry_path=reg_target, event_log_path=evt_target)
    
    # ---------------------------------------------------------
    # 3. Recent Coherence Failures
    # ---------------------------------------------------------
    coherence_failures = read_events(event_log_path=evt_target, event_type="CoherenceCheckFailed")
    
    # ---------------------------------------------------------
    # 4. Blocked or Failed Transitions
    # ---------------------------------------------------------
    transitions_issues: List[Dict[str, Any]] = []
    rout_log = _default_routing_log_path()
    if rout_log.exists():
        try:
            for line in rout_log.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    status = entry.get("status")
                    if status in ("fail", "blocked"):
                        # Support older keys like bundle_filename
                        aid = entry.get("artifact_id") or entry.get("bundle_filename")
                        from shared.result_schemas import make_health_transition_entry
                        transitions_issues.append(make_health_transition_entry(
                            source="routing_log",
                            artifact_id=str(aid) if aid else None,
                            status=str(status),
                            error=entry.get("error"),
                            details=entry,
                        ))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
            
            
    # ---------------------------------------------------------
    # 5. Unprocessed Events
    # ---------------------------------------------------------
    # Do not mutate checkpoint, just parse
    unprocessed_events = iter_unprocessed_events(
        checkpoint_path=ckpt_target,
        event_log_path=evt_target,
    )
    
    return {
        "summary": {
            "artifact_counts_by_state": counts,
            "reconciliation_issue_count": len(recon.get("issues", [])),
            "recent_coherence_failure_count": len(coherence_failures),
            "blocked_or_failed_transition_count": len(transitions_issues),
            "unprocessed_event_count": len(unprocessed_events),
        },
        "reconciliation": recon,
        "recent_coherence_failures": coherence_failures,
        "blocked_or_failed_transitions": transitions_issues,
        "unprocessed_events": unprocessed_events,
    }

