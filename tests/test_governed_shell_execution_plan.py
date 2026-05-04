from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.governed_shell.confirm import check_confirmation, require_confirmation
from app.governed_shell.errors import ConfirmationError, ExecutionPlanError
from app.governed_shell.execution_plan import (
    build_execution_plan,
    canonical_plan_json,
    verify_execution_plan,
    write_sealed_plan,
)
from app.governed_shell.normalize import normalize_and_hash_proposal
from app.governed_shell.policy import evaluate_policy


def _listing_proposal(*, recurse: bool = False) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_phase5_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List reports",
            "justification": "Create a governed shell plan only.",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase5",
        },
        "path_refs": [
            {
                "path_ref_id": "reports_dir",
                "root_id": "reports",
                "relative_path": "operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_list_reports",
                "operation_type": "powershell_cmdlet",
                "cmdlet_id": "ps.get_child_items_v1",
                "parameters": [
                    {
                        "name": "target_path_ref",
                        "value_type": "path_ref",
                        "path_ref": "reports_dir",
                    },
                    {
                        "name": "recurse",
                        "value_type": "boolean",
                        "boolean_value": recurse,
                    },
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
            "rationale": "Annotation only.",
        },
    }


def _registered_script_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_phase5_script_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "Dry-run script",
            "justification": "Policy denial proof only.",
            "requested_effect": "simulate",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase5",
        },
        "path_refs": [
            {
                "path_ref_id": "reports_dir",
                "root_id": "reports",
                "relative_path": "operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_script",
                "operation_type": "registered_script",
                "script_id": "retention.simulate_execute_send_v1",
                "execution_mode": "dry_run",
                "arguments": [
                    {
                        "name": "target_path_ref",
                        "value_type": "path_ref",
                        "path_ref": "reports_dir",
                    }
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
        },
    }


def _registered_native_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_phase5_native_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "Native request",
            "justification": "Policy denial proof only.",
            "requested_effect": "simulate",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase5",
        },
        "path_refs": [
            {
                "path_ref_id": "reports_dir",
                "root_id": "reports",
                "relative_path": "operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_native",
                "operation_type": "registered_native",
                "native_id": "native.safe_tool_v1",
                "arguments": [
                    {
                        "name": "target_path_ref",
                        "value_type": "path_ref",
                        "path_ref": "reports_dir",
                    }
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
        },
    }


def test_no_confirmation_required_passes_with_no_supplied_hash() -> None:
    result = check_confirmation("sha256:" + ("1" * 64), None, False, "none")

    assert result.clean is True
    assert result.required is False
    assert result.matched is False
    assert result.reason_code == "confirmation_not_required"


def test_confirmation_required_fails_when_supplied_hash_is_missing() -> None:
    result = check_confirmation("sha256:" + ("1" * 64), None, True, "exact_proposal_hash")

    assert result.clean is False
    assert result.reason_code == "confirmation_missing"


def test_confirmation_required_fails_when_supplied_hash_differs() -> None:
    result = check_confirmation(
        "sha256:" + ("1" * 64),
        "sha256:" + ("2" * 64),
        True,
        "exact_proposal_hash",
    )

    assert result.clean is False
    assert result.reason_code == "confirmation_mismatch"


def test_confirmation_required_passes_only_on_exact_full_proposal_hash() -> None:
    proposal_hash = "sha256:" + ("1" * 64)
    result = require_confirmation(proposal_hash, proposal_hash, True, "exact_proposal_hash")

    assert result.clean is True
    assert result.matched is True
    assert result.reason_code == "confirmation_matched"


def test_partial_hash_fails() -> None:
    proposal_hash = "sha256:" + ("1" * 64)
    partial_hash = proposal_hash[:16]

    with pytest.raises(ConfirmationError):
        require_confirmation(proposal_hash, partial_hash, True, "exact_proposal_hash")


def test_uppercase_lowercase_mismatch_fails() -> None:
    proposal_hash = "sha256:" + ("a" * 64)
    uppercase_hash = proposal_hash.upper()

    with pytest.raises(ConfirmationError):
        require_confirmation(proposal_hash, uppercase_hash, True, "exact_proposal_hash")


def test_valid_low_risk_listing_creates_sealed_plan() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal(recurse=False))
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    plan = build_execution_plan(normalized, decision, confirmation)

    assert verify_execution_plan(plan).clean is True
    assert plan["proposal_hash"] == normalized.proposal_hash
    assert plan["policy_hash"] == decision.policy_hash
    assert plan["matched_binding_id"] == "ps.get_child_items_v1"
    assert plan["effective_risk"] == "low"
    assert plan["declared_reads"]
    assert plan["declared_writes"] == []
    assert "command_text" not in canonical_plan_json(plan)
    assert "shell_text" not in canonical_plan_json(plan)
    assert "script_text" not in canonical_plan_json(plan)


def test_denied_policy_decision_cannot_create_plan() -> None:
    proposal = _listing_proposal()
    proposal["operations"][0]["cmdlet_id"] = "ps.unknown_v1"
    normalized = normalize_and_hash_proposal(proposal)
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    with pytest.raises(ExecutionPlanError):
        build_execution_plan(normalized, decision, confirmation)


def test_registered_script_denied_by_mvp_policy_cannot_create_plan() -> None:
    normalized = normalize_and_hash_proposal(_registered_script_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    with pytest.raises(ExecutionPlanError):
        build_execution_plan(normalized, decision, confirmation)


def test_registered_native_denied_by_mvp_policy_cannot_create_plan() -> None:
    normalized = normalize_and_hash_proposal(_registered_native_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    with pytest.raises(ExecutionPlanError):
        build_execution_plan(normalized, decision, confirmation)


def test_confirmation_required_proposal_cannot_create_plan_without_matching_hash() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal(recurse=True))
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    with pytest.raises(ExecutionPlanError):
        build_execution_plan(normalized, decision, confirmation)


def test_confirmation_required_proposal_creates_plan_with_matching_hash() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal(recurse=True))
    decision = evaluate_policy(normalized)
    confirmation = require_confirmation(
        normalized.proposal_hash,
        normalized.proposal_hash,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    plan = build_execution_plan(normalized, decision, confirmation)

    assert verify_execution_plan(plan).clean is True
    assert plan["decision"] == "require_confirmation"
    assert plan["confirmation"]["matched"] is True


def test_plan_hash_verifies_after_creation() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    plan = build_execution_plan(normalized, decision, confirmation)

    verification = verify_execution_plan(plan)

    assert verification.clean is True
    assert verification.plan_hash == plan["plan_hash"]


def test_plan_hash_fails_verification_after_mutation() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    plan = build_execution_plan(normalized, decision, confirmation)
    mutated = copy.deepcopy(plan)
    mutated["declared_reads"][0]["relative_path"] = "tampered"

    verification = verify_execution_plan(mutated)

    assert verification.clean is False
    assert any("plan_hash_mismatch" in issue for issue in verification.issues)


def test_writing_sealed_plan_writes_deterministic_json_file(tmp_path: Path) -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    plan = build_execution_plan(normalized, decision, confirmation)
    path = tmp_path / "sealed_plan.json"

    written_path = write_sealed_plan(path, plan)

    assert written_path == path
    assert path.read_text(encoding="utf-8") == canonical_plan_json(plan)


def test_sealed_plan_contains_expected_governance_fields() -> None:
    normalized = normalize_and_hash_proposal(_listing_proposal())
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )

    plan = build_execution_plan(normalized, decision, confirmation)

    assert plan["proposal_hash"] == normalized.proposal_hash
    assert plan["policy_hash"] == decision.policy_hash
    assert plan["matched_binding_id"] == decision.matched_binding_id
    assert plan["effective_risk"] == decision.effective_risk
    assert plan["declared_reads"] == decision.declared_reads
    assert plan["declared_writes"] == decision.declared_writes
