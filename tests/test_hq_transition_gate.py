from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.hq.governance.transition_gate import (
    emit_transition_event,
    load_lanes,
    load_policies,
    load_state_machine,
    validate_transition,
)


@pytest.fixture(autouse=True)
def use_repo_foundation_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(Path(__file__).resolve().parents[1]))


def test_foundation_config_loads_state_machine_lanes_and_policies() -> None:
    state_machine = load_state_machine()
    lanes = load_lanes()
    policies = load_policies()

    assert state_machine["model"] == "path2_canonical_state_machine"
    assert "promoted" in state_machine["states"]
    assert lanes["model"] == "path2_lane_registry"
    assert {"intake_policy", "promotion_policy", "routing_policy", "publication_policy"} <= set(
        policies
    )


def test_validate_transition_allows_configured_route() -> None:
    result = validate_transition(
        current_state="promoted",
        next_state="routed",
        lane_id="content_publishing",
        context={
            "bundle_filename": "bundle.md",
            "router_ruleset_hash": "ruleset_sha256",
        },
    )

    assert result["allowed"] is True
    assert result["policy_id"] == "routing_policy"
    assert result["policy_result"]["failures"] == []


def test_validate_transition_rejects_forbidden_skip() -> None:
    result = validate_transition(
        current_state="captured",
        next_state="routed",
        lane_id="volatile_capture",
        context={},
    )

    assert result["allowed"] is False
    assert result["policy_result"]["failures"] == ["forbidden_transition"]


def test_validate_transition_fails_closed_without_promotion_context() -> None:
    result = validate_transition(
        current_state="constrained",
        next_state="promoted",
        lane_id="content_publishing",
        context={},
    )

    assert result["allowed"] is False
    assert result["policy_id"] == "promotion_policy"
    assert {
        "candidate_cluster_members_present",
        "bundle_identity_present",
    } <= set(result["policy_result"]["failures"])


def test_control_state_ttl_forces_rejection() -> None:
    entered_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    result = validate_transition(
        current_state="held",
        next_state="captured",
        lane_id=None,
        context={"entered_at": entered_at},
    )

    assert result["allowed"] is True
    assert result["ttl_expired"] is True
    assert result["next_state"] == "rejected"
    assert result["forced_target"] == "rejected"


def _emit_test_event(tmp_path: Path, validation: dict, context: dict | None = None) -> dict:
    ledger = tmp_path / "transition_gate_events.jsonl"
    payload = emit_transition_event(
        validation,
        run_id="transition_test",
        ledger_path=ledger,
        context=context or {},
    )
    persisted = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert persisted == payload
    return payload


def test_emit_transition_event_allowed_has_null_denial_fields(tmp_path: Path) -> None:
    payload = _emit_test_event(
        tmp_path,
        {
            "allowed": True,
            "current_state": "captured",
            "next_state": "promoted",
            "lane_id": "content_publishing",
            "policy_id": "promotion_policy",
            "policy_result": {"allowed": True, "failures": [], "policy_id": "promotion_policy"},
            "reason": None,
        },
        {"module": "module.alpha", "operation": "promote"},
    )

    assert payload["denial_reason"] is None
    assert payload["denial_category"] is None
    assert payload["denial_subtype"] is None
    assert payload["source_module"] == "module.alpha"
    assert payload["source_operation"] == "promote"
    assert payload["state_from"] == "captured"
    assert payload["state_to"] == "promoted"
    assert payload["policy_rule_id"] == "promotion_policy"


@pytest.mark.parametrize(
    ("validation", "expected_category", "expected_subtype"),
    [
        (
            {
                "allowed": False,
                "current_state": "captured",
                "next_state": "promoted",
                "policy_result": None,
                "reason": "duplicate_record_detected",
            },
            "duplicate_protection",
            "duplicate_record_detected",
        ),
        (
            {
                "allowed": False,
                "current_state": None,
                "next_state": "promoted",
                "policy_result": {"allowed": False, "failures": ["invalid_current_state"]},
                "reason": "invalid_current_state:empty",
            },
            "state_integrity",
            "invalid_current_state",
        ),
        (
            {
                "allowed": False,
                "current_state": "captured",
                "next_state": "routed",
                "policy_result": {"allowed": False, "failures": ["forbidden_transition"]},
                "reason": "early_state_skip_forbidden",
            },
            "forbidden_transition",
            "forbidden_transition",
        ),
        (
            {
                "allowed": False,
                "current_state": "promoted",
                "next_state": "promoted",
                "policy_result": {"allowed": False, "failures": ["transition_not_defined"]},
                "reason": "transition_not_defined:promoted->promoted",
            },
            "undefined_transition",
            "transition_not_defined",
        ),
        (
            {
                "allowed": False,
                "current_state": "constrained",
                "next_state": "promoted",
                "policy_result": {"allowed": False, "failures": ["lane_operational"]},
                "reason": "lane_not_operational:content_publishing:inactive",
            },
            "policy_rejection",
            "lane_not_operational",
        ),
        (
            {
                "allowed": False,
                "current_state": "constrained",
                "next_state": "promoted",
                "policy_result": {"allowed": False, "failures": ["bundle_identity_present"]},
                "reason": "bundle_identity_present",
            },
            "missing_prerequisite",
            "bundle_identity_present",
        ),
        (
            {
                "allowed": False,
                "current_state": "captured",
                "next_state": "promoted",
                "policy_result": None,
                "reason": "unsupported_execution_mode",
            },
            "operator_error",
            "unsupported_execution_mode",
        ),
        (
            {
                "allowed": False,
                "current_state": "captured",
                "next_state": "promoted",
                "policy_result": None,
                "reason": "provider_unavailable",
            },
            "provider_failure",
            "provider_unavailable",
        ),
    ],
)
def test_emit_transition_event_classifies_rejected_events(
    tmp_path: Path,
    validation: dict,
    expected_category: str,
    expected_subtype: str,
) -> None:
    payload = _emit_test_event(
        tmp_path,
        validation,
        {"module": "signal_agent.operator.runtime", "operation": "compound_gate_rejected"},
    )

    assert payload["denial_reason"]
    assert payload["denial_category"] == expected_category
    assert payload["denial_subtype"] == expected_subtype


def test_emit_transition_event_classifies_activation_event_without_reason(tmp_path: Path) -> None:
    payload = _emit_test_event(
        tmp_path,
        {
            "allowed": None,
            "current_state": None,
            "next_state": None,
            "lane_id": None,
            "policy_result": None,
            "reason": None,
        },
        {"module": "app.governor.activation_governor", "operation": "REVIEW_INIT"},
    )

    assert payload["status"] == "rejected"
    assert payload["denial_reason"] == "activation_event_without_denial_reason"
    assert payload["denial_category"] == "unknown"
    assert payload["denial_subtype"] == "activation_event_without_denial_reason"
