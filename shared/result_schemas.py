"""
shared/result_schemas.py — Shared deterministic result shapes.
"""
from typing import Any, Dict, Optional


def make_coherence_result(
    artifact_id: Optional[str],
    expected_state: Optional[str],
    registry_found: bool,
    registry_state: Optional[str],
    registry_path: Optional[str],
    filesystem_exists: bool,
    coherent: bool,
    reason: str,
) -> Dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "expected_state": expected_state,
        "registry_found": registry_found,
        "registry_state": registry_state,
        "registry_path": registry_path,
        "filesystem_exists": filesystem_exists,
        "coherent": coherent,
        "reason": reason,
    }


def make_route_result(
    status: str,
    artifact_id: Optional[str] = None,
    contract_source: Optional[str] = None,
    confidence: Optional[Any] = None,
    error: Optional[str] = None,
    coherence: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    d = details or {}
    base = {
        "status": status,
        "artifact_id": artifact_id,
        "contract_source": contract_source,
        "confidence": confidence,
        "error": error,
        "coherence": coherence,
        "details": d,
    }
    # Compatibility shim: hoist extras to top level so legacy tests don't break
    for k, v in d.items():
        if k not in base:
            base[k] = v
    return base


def make_reaction_result(
    event_type: str,
    artifact_id: str,
    action: str,
    status: str,
    bundle_path: Optional[str] = None,
    error: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "artifact_id": artifact_id,
        "action": action,
        "status": status,
        "bundle_path": bundle_path,
        "error": error,
        "details": details or {},
    }


def make_health_transition_entry(
    source: str,
    artifact_id: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "source": source,
        "artifact_id": artifact_id,
        "status": status,
        "error": error,
        "details": details or {},
    }
