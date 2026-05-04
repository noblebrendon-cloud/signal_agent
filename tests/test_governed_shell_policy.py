from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.governed_shell.errors import PolicyDeniedError, PolicyLoadError
from app.governed_shell.normalize import NormalizedProposal, PathValidationResult, normalize_and_hash_proposal
from app.governed_shell.policy import (
    evaluate_policy,
    load_policy,
    require_policy_allowed,
)
from app.governed_shell.proposal import dump_canonical_json


def _valid_policy_proposal(*, recurse: bool = False) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_policy_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List governed shell reports",
            "justification": "Review a reports directory through the default-deny policy.",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase3",
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


def _normalize(proposal: dict) -> NormalizedProposal:
    return normalize_and_hash_proposal(proposal)


def _manual_normalized(proposal: dict) -> NormalizedProposal:
    return NormalizedProposal(
        proposal=proposal,
        canonical_json=dump_canonical_json(proposal),
        proposal_hash="sha256:" + ("a" * 64),
        path_validation=PathValidationResult(
            clean=True,
            errors=[],
            normalized_paths={
                path_ref["path_ref_id"]: path_ref["relative_path"]
                for path_ref in proposal.get("path_refs", [])
                if type(path_ref) is dict and isinstance(path_ref.get("path_ref_id"), str)
            },
        ),
    )


def test_valid_ps_get_child_items_non_recursive_is_allowed() -> None:
    normalized = _normalize(_valid_policy_proposal(recurse=False))

    decision = evaluate_policy(normalized)

    assert decision.clean is True
    assert decision.decision == "allow"
    assert decision.reason_code == "allowed"
    assert decision.matched_binding_id == "ps.get_child_items_v1"
    assert decision.effective_risk == "low"
    assert decision.confirmation_required is False
    assert decision.declared_writes == []
    assert decision.network_allowed is False
    assert decision.privilege_escalation_allowed is False


def test_recursive_listing_requires_confirmation_and_medium_risk() -> None:
    normalized = _normalize(_valid_policy_proposal(recurse=True))

    decision = evaluate_policy(normalized)

    assert decision.clean is True
    assert decision.decision == "require_confirmation"
    assert decision.reason_code == "risk_requires_confirmation"
    assert decision.effective_risk == "medium"
    assert decision.confirmation_required is True
    assert decision.confirmation_mode == "session_confirmation"


def test_unknown_cmdlet_id_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["operations"][0]["cmdlet_id"] = "ps.unknown_v1"

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.decision == "deny"
    assert decision.reason_code == "unknown_binding"


def test_unknown_operation_type_bypass_fixture_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["operations"][0]["operation_type"] = "shell_command"

    decision = evaluate_policy(_manual_normalized(proposal))

    assert decision.clean is False
    assert decision.decision == "deny"
    assert decision.reason_code == "unsupported_operation_type"


def test_registered_script_disabled_in_policy_is_denied() -> None:
    proposal = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_policy_script_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "Shape a dry-run script request",
            "justification": "Validate policy review only.",
            "requested_effect": "simulate",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase3",
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

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.decision == "deny"
    assert decision.reason_code == "disabled_binding"


def test_registered_native_is_denied_in_mvp() -> None:
    proposal = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_policy_native_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "Shape a native request",
            "justification": "Validate policy review only.",
            "requested_effect": "simulate",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase3",
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

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "native_denied_mvp"


def test_unknown_parameter_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["operations"][0]["parameters"].append(
        {
            "name": "bogus_flag",
            "value_type": "boolean",
            "boolean_value": True,
        }
    )

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "unknown_parameter"


def test_root_not_allowed_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["path_refs"][0]["root_id"] = "data_state"

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "root_not_allowed"


def test_declared_write_path_on_read_only_binding_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["path_refs"].append(
        {
            "path_ref_id": "write_target",
            "root_id": "reports",
            "relative_path": "operator/output",
            "path_kind": "directory",
            "must_exist": False,
        }
    )
    proposal["operations"][0]["parameters"].append(
        {
            "name": "write_path",
            "value_type": "path_ref",
            "path_ref": "write_target",
        }
    )

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "write_not_allowed"
    assert decision.effective_risk == "high"


def test_network_access_true_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["operations"][0]["parameters"].append(
        {
            "name": "network_access",
            "value_type": "boolean",
            "boolean_value": True,
        }
    )

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "network_denied_mvp"


def test_privilege_change_true_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["operations"][0]["parameters"].append(
        {
            "name": "privilege_change",
            "value_type": "boolean",
            "boolean_value": True,
        }
    )

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "privilege_denied_mvp"


def test_model_declared_low_but_recursive_read_escalates_to_medium() -> None:
    proposal = _valid_policy_proposal(recurse=True)
    proposal["model_annotations"]["model_declared_risk_level"] = "low"

    decision = evaluate_policy(_normalize(proposal))

    assert decision.effective_risk == "medium"
    assert "recursive_read" in decision.issues


def test_model_declared_low_but_write_path_is_denied() -> None:
    proposal = _valid_policy_proposal()
    proposal["path_refs"].append(
        {
            "path_ref_id": "write_target",
            "root_id": "reports",
            "relative_path": "operator/output",
            "path_kind": "directory",
            "must_exist": False,
        }
    )
    proposal["operations"][0]["parameters"].append(
        {
            "name": "write_path",
            "value_type": "path_ref",
            "path_ref": "write_target",
        }
    )
    proposal["model_annotations"]["model_declared_risk_level"] = "low"

    decision = evaluate_policy(_normalize(proposal))

    assert decision.clean is False
    assert decision.reason_code == "write_not_allowed"
    assert decision.effective_risk == "high"


def test_missing_policy_file_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing_path = tmp_path / "missing_policy.yaml"
    proposal = _valid_policy_proposal()
    normalized = _normalize(proposal)

    import app.governed_shell.policy as policy_module

    monkeypatch.setattr(policy_module, "DEFAULT_POLICY_PATH", missing_path)

    decision = evaluate_policy(normalized)

    assert decision.clean is False
    assert decision.reason_code == "policy_missing"
    with pytest.raises(PolicyLoadError):
        load_policy(missing_path)


def test_malformed_policy_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malformed_path = tmp_path / "malformed_policy.yaml"
    malformed_path.write_text("policy_id: [\n", encoding="utf-8")
    normalized = _normalize(_valid_policy_proposal())

    import app.governed_shell.policy as policy_module

    monkeypatch.setattr(policy_module, "DEFAULT_POLICY_PATH", malformed_path)

    decision = evaluate_policy(normalized)

    assert decision.clean is False
    assert decision.reason_code == "policy_invalid"


def test_policy_hash_is_stable_across_loads() -> None:
    normalized = _normalize(_valid_policy_proposal())

    decision_a = evaluate_policy(normalized)
    decision_b = evaluate_policy(normalized, policy=load_policy())

    assert decision_a.policy_hash == decision_b.policy_hash


def test_require_policy_allowed_raises_explicit_exception_on_deny() -> None:
    proposal = _valid_policy_proposal(recurse=True)
    normalized = _normalize(proposal)

    with pytest.raises(PolicyDeniedError):
        require_policy_allowed(normalized)
