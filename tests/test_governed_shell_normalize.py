from __future__ import annotations

import copy

import pytest

from app.governed_shell.errors import ProposalPathError
from app.governed_shell.normalize import (
    canonicalize_proposal,
    compute_proposal_hash,
    normalize_and_hash_proposal,
    validate_path_refs,
)
from app.governed_shell.proposal import dump_canonical_json, load_json_text


def _valid_read_only_proposal() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_normalize_001",
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
            "agent_id": "phase2",
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


def test_same_proposal_with_different_key_ordering_has_identical_hash() -> None:
    proposal_a = _valid_read_only_proposal()
    proposal_b = load_json_text(
        """
        {
          "model_annotations": {
            "rationale": "Read-only listing only",
            "model_declared_risk_level": "low",
            "proposal_source": "model_authored"
          },
          "operations": [
            {
              "parameters": [
                {
                  "path_ref": "docs_operator_dir",
                  "value_type": "path_ref",
                  "name": "target_path"
                },
                {
                  "boolean_value": false,
                  "value_type": "boolean",
                  "name": "recurse"
                }
              ],
              "cmdlet_id": "ps.get_child_items_v1",
              "operation_type": "powershell_cmdlet",
              "op_id": "op_list_docs"
            }
          ],
          "path_refs": [
            {
              "must_exist": true,
              "path_kind": "directory",
              "relative_path": "docs/operator",
              "root_id": "workspace",
              "path_ref_id": "docs_operator_dir"
            }
          ],
          "proposer": {
            "agent_id": "phase2",
            "agent_family": "codex",
            "proposal_only": true,
            "kind": "agent"
          },
          "intent": {
            "requested_effect": "inspect",
            "justification": "Review the governed shell docs directory",
            "summary": "List operator docs"
          },
          "requested_execution_mode": "simulate",
          "created_at": "2026-05-03T12:00:00Z",
          "proposal_id": "proposal_normalize_001",
          "schema_version": "command_proposal.v1",
          "$schema": "https://json-schema.org/draft/2020-12/schema"
        }
        """
    )

    assert compute_proposal_hash(proposal_a) == compute_proposal_hash(proposal_b)


def test_changed_intent_summary_changes_hash() -> None:
    baseline = _valid_read_only_proposal()
    changed = _valid_read_only_proposal()
    changed["intent"]["summary"] = "List governance docs"

    assert compute_proposal_hash(baseline) != compute_proposal_hash(changed)


def test_changed_operation_parameter_changes_hash() -> None:
    baseline = _valid_read_only_proposal()
    changed = _valid_read_only_proposal()
    changed["operations"][0]["parameters"][1]["boolean_value"] = True

    assert compute_proposal_hash(baseline) != compute_proposal_hash(changed)


def test_canonical_json_is_deterministic() -> None:
    proposal = _valid_read_only_proposal()

    normalized_a = normalize_and_hash_proposal(proposal)
    normalized_b = normalize_and_hash_proposal(copy.deepcopy(proposal))

    assert normalized_a.canonical_json == normalized_b.canonical_json
    assert normalized_a.canonical_json == dump_canonical_json(normalized_a.proposal)


def test_normalization_does_not_mutate_original_proposal_input() -> None:
    proposal = _valid_read_only_proposal()
    original = copy.deepcopy(proposal)
    proposal["path_refs"][0]["relative_path"] = "docs\\operator"

    normalized = normalize_and_hash_proposal(proposal)

    assert proposal["path_refs"][0]["relative_path"] == "docs\\operator"
    assert original["path_refs"][0]["relative_path"] == "docs/operator"
    assert normalized.proposal["path_refs"][0]["relative_path"] == "docs/operator"


def test_normal_relative_path_passes() -> None:
    result = validate_path_refs(_valid_read_only_proposal())

    assert result.clean is True
    assert result.errors == []
    assert result.normalized_paths == {"docs_operator_dir": "docs/operator"}


@pytest.mark.parametrize(
    ("relative_path", "expected_fragment"),
    [
        ("C:\\temp\\operator", "must not be absolute"),
        ("/tmp/operator", "must not be absolute"),
        ("../docs/operator", "must not contain parent traversal"),
        ("..\\docs\\operator", "must not contain parent traversal"),
        ("safe/../../escape", "must not contain parent traversal"),
        ("docs/operator;whoami", "forbidden shell metacharacters"),
    ],
)
def test_invalid_relative_paths_fail(relative_path: str, expected_fragment: str) -> None:
    proposal = _valid_read_only_proposal()
    proposal["path_refs"][0]["relative_path"] = relative_path

    result = validate_path_refs(proposal)

    assert result.clean is False
    assert any(expected_fragment in error for error in result.errors)


def test_unknown_path_ref_reference_fails_path_validation() -> None:
    proposal = _valid_read_only_proposal()
    proposal["operations"][0]["parameters"][0]["path_ref"] = "missing_ref"

    result = validate_path_refs(proposal)

    assert result.clean is False
    assert any("unknown path_ref" in error for error in result.errors)


def test_canonicalize_proposal_raises_on_invalid_path() -> None:
    proposal = _valid_read_only_proposal()
    proposal["path_refs"][0]["relative_path"] = "docs/operator;whoami"

    with pytest.raises(ProposalPathError):
        canonicalize_proposal(proposal)
