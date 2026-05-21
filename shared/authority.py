"""
shared/authority.py — Thin truth-precedence layer.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path

AUTHORITY_ORDER = [
    "coherence_guard",
    "lifecycle_rules",
    "state_registry",
    "event_log",
    "path_convention",
]

def evaluate_authority(
    *,
    artifact_id: Optional[str] = None,
    expected_state: Optional[str] = None,
    current_state: Optional[str] = None,
    target_state: Optional[str] = None,
    transition_lane_id: Optional[str] = None,
    transition_context: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
    coherence_result: Optional[Dict[str, Any]] = None,
    recent_events: Optional[List[Dict[str, Any]]] = None,
    path_hint: Optional[str] = None,
) -> Dict[str, Any]:
    decision_trace = []
    authoritative_source = None
    allowed = False
    blocking_reason = None

    if coherence_result:
        is_coherent = coherence_result.get("coherent", False)
        reason = coherence_result.get("reason", "unknown")
        decision_trace.append({
            "source": "coherence_guard",
            "considered": True,
            "result": "pass" if is_coherent else "block",
            "details": {"reason": reason}
        })
        if not is_coherent:
            authoritative_source = "coherence_guard"
            allowed = False
            blocking_reason = reason
            return {
                "artifact_id": artifact_id,
                "expected_state": expected_state,
                "authority_order": AUTHORITY_ORDER,
                "authoritative_source": authoritative_source,
                "allowed": allowed,
                "blocking_reason": blocking_reason,
                "decision_trace": decision_trace,
            }

    if current_state and target_state:
        from app.hq.governance import validate_transition
        gate_result = validate_transition(
            current_state=current_state,
            next_state=target_state,
            lane_id=transition_lane_id,
            context=transition_context or {},
        )
        if not gate_result.get("allowed"):
            decision_trace.append({
                "source": "lifecycle_rules",
                "considered": True,
                "result": "block",
                "details": {
                    "current_state": current_state,
                    "target_state": target_state,
                    "gate_reason": gate_result.get("reason"),
                }
            })
            authoritative_source = "lifecycle_rules"
            allowed = False
            blocking_reason = gate_result.get("reason", "invalid_transition")
            return {
                "artifact_id": artifact_id,
                "expected_state": expected_state,
                "authority_order": AUTHORITY_ORDER,
                "authoritative_source": authoritative_source,
                "allowed": allowed,
                "blocking_reason": blocking_reason,
                "decision_trace": decision_trace,
            }

    if registry_entry and "state" in registry_entry:
        reg_state = registry_entry["state"]
        if expected_state and reg_state != expected_state:
            decision_trace.append({
                "source": "state_registry",
                "considered": True,
                "result": "block",
                "details": {"registry_state": reg_state, "expected_state": expected_state}
            })
            authoritative_source = "state_registry"
            allowed = False
            blocking_reason = "state_mismatch"
            return {
                "artifact_id": artifact_id,
                "expected_state": expected_state,
                "authority_order": AUTHORITY_ORDER,
                "authoritative_source": authoritative_source,
                "allowed": allowed,
                "blocking_reason": blocking_reason,
                "decision_trace": decision_trace,
            }
        elif expected_state and reg_state == expected_state:
            decision_trace.append({
                "source": "state_registry",
                "considered": True,
                "result": "allow",
                "details": {"registry_state": reg_state}
            })
            authoritative_source = "state_registry"
            allowed = True
            return {
                "artifact_id": artifact_id,
                "expected_state": expected_state,
                "authority_order": AUTHORITY_ORDER,
                "authoritative_source": authoritative_source,
                "allowed": allowed,
                "blocking_reason": blocking_reason,
                "decision_trace": decision_trace,
            }

    if recent_events:
        decision_trace.append({
            "source": "event_log",
            "considered": True,
            "result": "inform",
            "details": {"event_count": len(recent_events)}
        })

    if path_hint:
        decision_trace.append({
            "source": "path_convention",
            "considered": True,
            "result": "inform",
            "details": {"path_hint": path_hint}
        })

    if authoritative_source is None:
        authoritative_source = "default_conservative"
        allowed = False
        blocking_reason = "insufficient_authority"

    return {
        "artifact_id": artifact_id,
        "expected_state": expected_state,
        "authority_order": AUTHORITY_ORDER,
        "authoritative_source": authoritative_source,
        "allowed": allowed,
        "blocking_reason": blocking_reason,
        "decision_trace": decision_trace,
    }

def check_preconditions_for_routing(
    artifact_id: str,
    expected_state: str = "promoted",
    target_state: Optional[str] = None,
    transition_lane_id: Optional[str] = None,
    transition_context: Optional[Dict[str, Any]] = None,
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    from shared.state_registry import get_state
    from shared.coherence import check_artifact_coherence
    from shared.inspect import recent_events
    
    entry = get_state(artifact_id, registry_path=registry_path)
    coherence_res = check_artifact_coherence(
        artifact_id=artifact_id,
        expected_state=expected_state,
        registry_path=registry_path
    )
    events = recent_events(artifact_id, limit=50, event_log_path=event_log_path)
    
    authority_eval = evaluate_authority(
        artifact_id=artifact_id,
        expected_state=expected_state,
        current_state=entry.get("state") if entry else None,
        target_state=target_state,
        transition_lane_id=transition_lane_id,
        transition_context=transition_context,
        registry_entry=entry,
        coherence_result=coherence_res,
        recent_events=events,
        path_hint=None,
    )
    
    registry_summary = {
        "found": bool(entry),
        "state": entry.get("state") if entry else None,
        "path": entry.get("path") if entry else None,
        "updated_at": entry.get("updated_at") if entry else None,
    }
    
    return {
        "artifact_id": artifact_id,
        "expected_state": expected_state,
        "authority": authority_eval,
        "coherence": coherence_res,
        "registry": registry_summary,
        "events": events,
    }
