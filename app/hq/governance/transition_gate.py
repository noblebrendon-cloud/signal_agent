from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.utils.io_contract import append_jsonl_atomic


_OPERATIONAL_LANE_STATUSES = {"active", "partial"}
_SPINE_TO_LANE = {"misc": "misc_review"}
_ROUTE_TO_LANE = {
    "docs": "content_publishing",
    "outputs": "content_publishing",
    "video_source": "video_packaging",
    "archive": "misc_review",
    "trash": "misc_review",
}


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id(prefix: str = "transition") -> str:
    basis = f"{prefix}|{_utc_now_iso()}"
    token = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{token}"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def load_state_machine() -> dict[str, Any]:
    return _load_yaml(_get_root() / "config" / "state_machine.yaml")


def load_policies() -> dict[str, dict[str, Any]]:
    policies_dir = _get_root() / "config" / "policies"
    payload: dict[str, dict[str, Any]] = {}
    if not policies_dir.exists():
        return payload
    for path in sorted(policies_dir.glob("*.yaml")):
        data = _load_yaml(path)
        policy_id = str(data.get("policy_id") or path.stem).strip()
        if policy_id:
            payload[policy_id] = data
    return payload


def load_lanes() -> dict[str, Any]:
    return _load_yaml(_get_root() / "config" / "lanes.yaml")


def resolve_lane_for_spine(spine_name: str | None) -> str | None:
    if not spine_name:
        return None
    return _SPINE_TO_LANE.get(spine_name, spine_name)


def resolve_lane_for_route(route_key: str | None, kind: str | None = None) -> str | None:
    route = str(route_key or "").strip().lower()
    if route:
        if route in _ROUTE_TO_LANE:
            return _ROUTE_TO_LANE[route]
        if route in {"content_publishing", "ai_stability_diagnostic", "misc_review", "concept_formalization", "video_packaging"}:
            return route
    if str(kind or "").strip().lower() == "video_source":
        return "video_packaging"
    return "misc_review"


def _lane_lookup(lane_id: str | None, lanes: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    if not lane_id:
        return None, None
    for lane in lanes.get("lanes", []):
        if isinstance(lane, dict) and lane.get("lane_id") == lane_id:
            return str(lane.get("status") or ""), lane
    for reserved in lanes.get("reserved_spines", []):
        if isinstance(reserved, dict) and reserved.get("spine_id") == lane_id:
            return str(reserved.get("status") or ""), reserved
    return None, None


def _normalize_state(value: str | None) -> str:
    return str(value or "").strip()


def _forbidden_reason(state_machine: dict[str, Any], current_state: str, next_state: str) -> str | None:
    for entry in state_machine.get("forbidden_transitions", []):
        if not isinstance(entry, dict):
            continue
        source = _normalize_state(entry.get("from"))
        targets = entry.get("to")
        if source != current_state:
            continue
        if targets == "any":
            return str(entry.get("reason") or "forbidden_transition")
        if isinstance(targets, list) and next_state in {str(item) for item in targets}:
            return str(entry.get("reason") or "forbidden_transition")
        if isinstance(targets, str) and targets == next_state:
            return str(entry.get("reason") or "forbidden_transition")
    return None


def _transition_entry(state_machine: dict[str, Any], current_state: str | None, next_state: str) -> dict[str, Any] | None:
    for entry in state_machine.get("transitions", []):
        if not isinstance(entry, dict):
            continue
        if not current_state and entry.get("from_missing") is True and _normalize_state(entry.get("to")) == next_state:
            return entry
        source = _normalize_state(entry.get("from"))
        target = _normalize_state(entry.get("to"))
        from_any = entry.get("from_any")
        if isinstance(from_any, list) and current_state in {str(item) for item in from_any} and target == next_state:
            return entry
        if source == current_state and target == next_state:
            return entry
    return None


def _check(name: str, ok: bool, detail: Any = None) -> dict[str, Any]:
    payload = {"name": name, "ok": bool(ok)}
    if detail is not None:
        payload["detail"] = detail
    return payload


def _evaluate_intake_policy(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _check(
            "input_reference_present",
            any(context.get(key) for key in ("source_path", "payload", "clipboard_payload", "file_path")),
        )
    ]


def _evaluate_promotion_policy(context: dict[str, Any]) -> list[dict[str, Any]]:
    members = context.get("candidate_cluster_members") or []
    return [
        _check("candidate_cluster_members_present", isinstance(members, list) and len(members) > 0, len(members) if isinstance(members, list) else 0),
        _check(
            "bundle_identity_present",
            bool(context.get("cluster_id") or context.get("bundle_filename")),
        ),
    ]


def _evaluate_routing_policy(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _check(
            "bundle_reference_present",
            bool(context.get("bundle_path") or context.get("bundle_filename")),
        ),
        _check(
            "router_ruleset_hash_present",
            bool(context.get("router_ruleset_hash")),
        ),
    ]


def _evaluate_publication_policy(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _check("durable_identity_present", bool(context.get("artifact_id") or context.get("sha256"))),
        _check("final_path_present", bool(context.get("final_path"))),
        _check("route_key_present", bool(context.get("route_key"))),
    ]


_POLICY_VALIDATORS = {
    "intake_policy": _evaluate_intake_policy,
    "promotion_policy": _evaluate_promotion_policy,
    "routing_policy": _evaluate_routing_policy,
    "publication_policy": _evaluate_publication_policy,
}


def _evaluate_policy(
    policy_id: str | None,
    lane_id: str | None,
    context: dict[str, Any],
    lanes: dict[str, Any],
    policies: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lane_status, lane_entry = _lane_lookup(lane_id, lanes)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    if lane_id:
        checks.append(_check("lane_registered", lane_status is not None, lane_status or "missing"))
        checks.append(
            _check(
                "lane_operational",
                lane_status in _OPERATIONAL_LANE_STATUSES,
                lane_status or "missing",
            )
        )
        if lane_status is None:
            failures.append(f"lane_not_registered:{lane_id}")
        elif lane_status not in _OPERATIONAL_LANE_STATUSES:
            failures.append(f"lane_not_operational:{lane_id}:{lane_status}")

    policy = policies.get(str(policy_id or ""), {})
    validator = _POLICY_VALIDATORS.get(str(policy_id or ""))
    if validator is not None:
        checks.extend(validator(context))

    failures.extend(check["name"] for check in checks if not check.get("ok"))
    return {
        "policy_id": policy_id,
        "allowed": not failures,
        "declared_required_conditions": list(policy.get("required_conditions") or []),
        "declared_allowed_actions": list(policy.get("allowed_actions") or []),
        "declared_forbidden_actions": list(policy.get("forbidden_actions") or []),
        "lane_status": lane_status,
        "lane_entry": lane_entry.get("lane_id") if isinstance(lane_entry, dict) and lane_entry.get("lane_id") else lane_id,
        "runtime_checks": checks,
        "failures": failures,
    }


def validate_transition(
    current_state: str | None,
    next_state: str,
    lane_id: str | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    state_machine = load_state_machine()
    policies = load_policies()
    lanes = load_lanes()

    resolved_current = _normalize_state(current_state or context.get("assumed_current_state") or context.get("legacy_current_state"))
    state_source = "provided" if current_state else "legacy_assumption" if resolved_current else "missing"
    resolved_next = _normalize_state(next_state)
    current_state_value = resolved_current or None

    states = state_machine.get("states") or {}

    # ── FAIL-CLOSED STATE VALIDATION (P0 FIX) ────────────────────────
    # The gate must never evaluate a transition whose endpoints are
    # outside the declared state space.
    #
    # Missing current_state (None / empty) is permitted ONLY when the
    # state machine declares a from_missing transition to the target
    # state.  This is the canonical bootstrap path for first-time
    # capture / promotion.  All other missing / unknown current_state
    # values are hard-rejected.
    if not resolved_current:
        has_bootstrap_rule = any(
            isinstance(entry, dict)
            and entry.get("from_missing") is True
            and _normalize_state(entry.get("to")) == resolved_next
            for entry in state_machine.get("transitions", [])
        )
        if not has_bootstrap_rule:
            return {
                "allowed": False,
                "current_state": current_state_value,
                "next_state": resolved_next,
                "lane_id": lane_id,
                "state_source": state_source,
                "gate": None,
                "policy_id": None,
                "policy_result": {
                    "allowed": False,
                    "failures": ["invalid_current_state"],
                },
                "reason": f"invalid_current_state:{resolved_current or 'empty'}",
                "details": {
                    "current_state": current_state_value,
                    "known_states": sorted(states.keys()),
                },
            }
    elif resolved_current not in states:
        return {
            "allowed": False,
            "current_state": current_state_value,
            "next_state": resolved_next,
            "lane_id": lane_id,
            "state_source": state_source,
            "gate": None,
            "policy_id": None,
            "policy_result": {
                "allowed": False,
                "failures": ["invalid_current_state"],
            },
            "reason": f"invalid_current_state:{resolved_current}",
            "details": {
                "current_state": current_state_value,
                "known_states": sorted(states.keys()),
            },
        }

    # Reject empty, None, or unknown next_state.
    if not resolved_next or resolved_next not in states:
        return {
            "allowed": False,
            "current_state": current_state_value,
            "next_state": resolved_next,
            "lane_id": lane_id,
            "state_source": state_source,
            "gate": None,
            "policy_id": None,
            "policy_result": {
                "allowed": False,
                "failures": ["invalid_next_state"],
            },
            "reason": f"invalid_next_state:{resolved_next or 'empty'}",
            "details": {
                "next_state": resolved_next,
                "known_states": sorted(states.keys()),
            },
        }
    # ── END P0 FIX ───────────────────────────────────────────────────

    forbidden = _forbidden_reason(state_machine, resolved_current, resolved_next)
    if forbidden is not None:
        return {
            "allowed": False,
            "current_state": current_state_value,
            "next_state": resolved_next,
            "lane_id": lane_id,
            "state_source": state_source,
            "gate": None,
            "policy_id": None,
            "policy_result": {"allowed": False, "failures": ["forbidden_transition"]},
            "reason": forbidden,
        }

    # ── TTL ENFORCEMENT: control state expiry ─────────────────────────
    # If the current state declares max_duration_seconds and context
    # provides entered_at, check whether the hold has expired.
    # Expired → force transition to expiry_target (default: rejected).
    current_state_def = states.get(resolved_current) or {}
    max_duration = current_state_def.get("max_duration_seconds")
    entered_at_raw = context.get("entered_at")
    if max_duration is not None and entered_at_raw is not None:
        try:
            entered_at = datetime.fromisoformat(
                str(entered_at_raw).replace("Z", "+00:00")
            )
            if entered_at.tzinfo is None:
                entered_at = entered_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - entered_at).total_seconds()
            if elapsed > float(max_duration):
                expiry_target = str(
                    current_state_def.get("expiry_target", "rejected")
                )
                return {
                    "allowed": True,
                    "current_state": current_state_value,
                    "next_state": expiry_target,
                    "lane_id": lane_id,
                    "state_source": state_source,
                    "gate": "governance_gate",
                    "policy_id": None,
                    "policy_result": {
                        "allowed": True,
                        "failures": [],
                        "ttl_enforced": True,
                        "elapsed_seconds": elapsed,
                        "max_duration_seconds": max_duration,
                    },
                    "reason": None,
                    "ttl_expired": True,
                    "forced_target": expiry_target,
                }
        except (ValueError, TypeError, OverflowError):
            pass  # Malformed entered_at — fall through to normal validation.

    transition = _transition_entry(state_machine, current_state_value, resolved_next)
    if transition is None:
        current_label = resolved_current if resolved_current else "missing"
        return {
            "allowed": False,
            "current_state": current_state_value,
            "next_state": resolved_next,
            "lane_id": lane_id,
            "state_source": state_source,
            "gate": None,
            "policy_id": None,
            "policy_result": {"allowed": False, "failures": ["transition_not_defined"]},
            "reason": f"transition_not_defined:{current_label}->{resolved_next}",
        }

    gate = str(transition.get("gate") or "")
    policy_id = gate if gate in policies else str(context.get("policy_id") or "")
    policy_result = _evaluate_policy(policy_id, lane_id, context, lanes, policies)
    allowed = bool(policy_result.get("allowed"))
    reason = None if allowed else ",".join(policy_result.get("failures") or ["policy_rejected"])

    return {
        "allowed": allowed,
        "current_state": current_state_value,
        "next_state": resolved_next,
        "lane_id": lane_id,
        "state_source": state_source,
        "gate": gate or None,
        "policy_id": policy_id or None,
        "policy_result": policy_result,
        "reason": reason,
    }


def make_lifecycle_metadata(validation: dict[str, Any], final_state: str | None = None) -> dict[str, Any]:
    return {
        "state": final_state or validation.get("next_state"),
        "current_state": validation.get("current_state"),
        "attempted_state": validation.get("next_state"),
        "lane_id": validation.get("lane_id"),
        "state_source": validation.get("state_source"),
        "gate": validation.get("gate"),
        "policy_id": validation.get("policy_id"),
        "policy_result": validation.get("policy_result"),
    }


def emit_transition_event(
    validation: dict[str, Any],
    *,
    run_id: str | None = None,
    envelope_id: str | None = None,
    artifact_id: str | None = None,
    ledger_path: Path | None = None,
    context: dict[str, Any] | None = None,
    event_type: str = "transition_attempt",
) -> dict[str, Any]:
    context = dict(context or {})
    payload = {
        "event_type": event_type,
        "timestamp_utc": _utc_now_iso(),
        "run_id": run_id or context.get("run_id") or new_run_id("transition"),
        "envelope_id": envelope_id or context.get("envelope_id") or context.get("cluster_id") or context.get("bundle_filename"),
        "artifact_id": artifact_id or context.get("artifact_id") or context.get("sha256"),
        "lane_id": validation.get("lane_id"),
        "current_state": validation.get("current_state"),
        "attempted_state": validation.get("next_state"),
        "policy_result": validation.get("policy_result"),
        "status": "allowed" if validation.get("allowed") else "rejected",
        "reason": validation.get("reason"),
    }
    module_name = context.get("module")
    operation = context.get("operation")
    if module_name:
        payload["module"] = module_name
    if operation:
        payload["operation"] = operation

    target = ledger_path or (_get_root() / "data" / "state" / "transition_gate_events.jsonl")
    append_jsonl_atomic(target, payload)
    return payload
