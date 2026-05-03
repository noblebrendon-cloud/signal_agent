from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema>=4 is recommended for governed shell Phase 2 schema validation",
)
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "app" / "governed_shell" / "schemas" / "command_proposal.v1.json"


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_no_raw_shell_001",
        "created_at": "2026-05-03T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List docs",
            "justification": "Read-only proof payload",
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
                    }
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
            "rationale": "Annotation only",
        },
    }


def _assert_invalid(payload: dict) -> None:
    validator = _validator()
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    assert errors, "expected schema validation failure"


def test_command_text_field_fails() -> None:
    payload = _valid_proposal()
    payload["command_text"] = "Get-ChildItem docs/operator"
    _assert_invalid(payload)


def test_shell_text_field_fails() -> None:
    payload = _valid_proposal()
    payload["shell_text"] = "Get-ChildItem docs/operator"
    _assert_invalid(payload)


def test_script_text_field_fails() -> None:
    payload = _valid_proposal()
    payload["script_text"] = "Write-Host 'unsafe'"
    _assert_invalid(payload)


def test_raw_powershell_dash_command_fails() -> None:
    payload = _valid_proposal()
    payload["operations"][0]["cmdlet_id"] = "-Command"
    _assert_invalid(payload)


def test_invoke_expression_fails() -> None:
    payload = _valid_proposal()
    payload["operations"][0]["cmdlet_id"] = "Invoke-Expression"
    _assert_invalid(payload)


def test_start_process_fails() -> None:
    payload = _valid_proposal()
    payload["operations"][0]["cmdlet_id"] = "Start-Process"
    _assert_invalid(payload)
