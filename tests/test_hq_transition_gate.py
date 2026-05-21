from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.hq.governance.transition_gate import (
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
