from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema>=4 is recommended for governed shell Phase 2 schema validation",
)
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "app" / "governed_shell" / "schemas"


def _load_schema(name: str) -> dict:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _validate(schema_name: str, payload: dict) -> list:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    return sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))


def _assert_valid(schema_name: str, payload: dict) -> None:
    errors = _validate(schema_name, payload)
    assert not errors, [error.message for error in errors]


def _assert_invalid(schema_name: str, payload: dict) -> list:
    errors = _validate(schema_name, payload)
    assert errors, "expected schema validation failure"
    return errors


def _valid_read_only_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_read_only_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List operator docs",
            "justification": "Review the governed shell docs directory",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase1",
        },
        "path_refs": [
            {
                "path_ref_id": "docs_operator_dir",
                "root_id": "workspace",
                "relative_path": "docs/operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_list_docs",
                "operation_type": "powershell_cmdlet",
                "cmdlet_id": "ps.get_child_items_v1",
                "parameters": [
                    {
                        "name": "target_path",
                        "value_type": "path_ref",
                        "path_ref": "docs_operator_dir",
                    },
                    {
                        "name": "recurse",
                        "value_type": "boolean",
                        "boolean_value": False,
                    },
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
            "rationale": "Read-only listing only",
        },
    }


def _valid_dry_run_script_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_dry_run_script_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "Prepare retention dry run",
            "justification": "Shape a dry-run registered script proposal only",
            "requested_effect": "simulate",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase1",
        },
        "path_refs": [
            {
                "path_ref_id": "send_authorization_file",
                "root_id": "data_state",
                "relative_path": "state/send_authorization.json",
                "path_kind": "file",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_script_dry_run",
                "operation_type": "registered_script",
                "script_id": "retention.simulate_execute_send_v1",
                "execution_mode": "dry_run",
                "arguments": [
                    {
                        "name": "authorization_path",
                        "value_type": "path_ref",
                        "path_ref": "send_authorization_file",
                    },
                    {
                        "name": "adapter",
                        "value_type": "string",
                        "string_value": "dry-run-gmail",
                    },
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "medium",
            "rationale": "Dry-run shape only; execution is not implemented in Phase 1",
        },
    }


def test_all_governed_shell_schemas_are_valid_draft_2020_12_schemas() -> None:
    for schema_name in (
        "command_proposal.v1.json",
        "audit_event.v1.json",
        "execution_plan.v1.json",
    ):
        _load_schema(schema_name)


def test_valid_read_only_proposal_passes_schema_validation() -> None:
    _assert_valid("command_proposal.v1.json", _valid_read_only_proposal())


def test_valid_dry_run_registered_script_proposal_passes_schema_validation() -> None:
    _assert_valid("command_proposal.v1.json", _valid_dry_run_script_proposal())


def test_malformed_proposal_fails_schema_validation() -> None:
    payload = _valid_read_only_proposal()
    payload["operations"] = "not-a-list"
    _assert_invalid("command_proposal.v1.json", payload)


def test_additional_unknown_field_fails() -> None:
    payload = _valid_read_only_proposal()
    payload["unexpected"] = True
    _assert_invalid("command_proposal.v1.json", payload)


def test_path_traversal_using_parent_segments_fails() -> None:
    payload = _valid_read_only_proposal()
    payload["path_refs"][0]["relative_path"] = "../docs/operator"
    _assert_invalid("command_proposal.v1.json", payload)


def test_absolute_path_fails() -> None:
    payload = _valid_read_only_proposal()
    payload["path_refs"][0]["relative_path"] = "C:\\temp\\operator"
    _assert_invalid("command_proposal.v1.json", payload)


def test_unknown_operation_type_fails() -> None:
    payload = _valid_read_only_proposal()
    payload["operations"][0]["operation_type"] = "shell_command"
    _assert_invalid("command_proposal.v1.json", payload)


def test_model_declared_risk_is_annotation_only_shape() -> None:
    payload = _valid_read_only_proposal()
    payload["model_annotations"]["proposal_hash_hint"] = "sha256:" + ("a" * 64)
    _assert_valid("command_proposal.v1.json", payload)


def test_valid_audit_event_schema_shape() -> None:
    payload = {
        "schema_version": "audit_event.v1",
        "record_type": "governed_shell_audit_event",
        "event_id": "event_001",
        "session_id": "session_001",
        "event_index": 0,
        "timestamp_utc": "2026-05-03T12:00:00Z",
        "event_type": "proposal_reviewed",
        "status": "rejected",
        "proposal_id": "proposal_001",
        "proposal_hash": "sha256:" + ("1" * 64),
        "plan_id": "plan_001",
        "plan_hash": "sha256:" + ("2" * 64),
        "policy_hash": "sha256:" + ("3" * 64),
        "risk_level": "medium",
        "decision_code": "schema_invalid",
        "snapshot_ref": "data/state/governed_shell/snapshots/session_001.json",
        "receipt_ref": "data/state/governed_shell/approved/plan_001.json",
        "prev_hash": None,
        "record_hash": "sha256:" + ("4" * 64),
    }
    _assert_valid("audit_event.v1.json", payload)


def test_valid_execution_plan_schema_shape() -> None:
    payload = {
        "schema_version": "execution_plan.v1",
        "plan_id": "plan_001",
        "created_at": "2026-05-03T12:00:00Z",
        "session_id": "session_001",
        "proposal_hash": "sha256:" + ("1" * 64),
        "policy_hash": "sha256:" + ("2" * 64),
        "execution_mode": "simulate",
        "network_allowed": False,
        "privilege_escalation_allowed": False,
        "risk": {
            "level": "medium",
            "authoritative": True,
            "model_declared_risk_level": "low",
        },
        "confirmation": {
            "required": True,
            "operator_supplied_hash": "sha256:" + ("3" * 64),
            "matched": True,
        },
        "sealed_operations": [
            {
                "op_id": "op_list_docs",
                "operation_type": "powershell_cmdlet",
                "binding_id": "ps.get_child_items_v1",
                "resolved_root": "E:\\signal_agent",
                "binding_hash": "sha256:" + ("4" * 64),
                "simulate_supported": True,
                "arguments": [
                    {
                        "name": "target_path",
                        "value_type": "path",
                        "resolved_abs_path": "E:\\signal_agent\\docs\\operator",
                    },
                    {
                        "name": "recurse",
                        "value_type": "boolean",
                        "boolean_value": False,
                    },
                ],
            }
        ],
        "plan_hash": "sha256:" + ("5" * 64),
    }
    _assert_valid("execution_plan.v1.json", payload)
