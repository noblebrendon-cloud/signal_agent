from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.governed_shell.confirm import check_confirmation, require_confirmation
from app.governed_shell.errors import SimulationError, SnapshotError
from app.governed_shell.execution_plan import build_execution_plan
from app.governed_shell.executor import (
    build_simulation_receipt,
    compute_receipt_hash,
    simulate_plan,
    verify_simulation_receipt,
)
from app.governed_shell.logstore import read_audit_events
from app.governed_shell.normalize import normalize_and_hash_proposal
from app.governed_shell.policy import evaluate_policy
from app.governed_shell.replay import replay_session, verify_log
from app.governed_shell.snapshot import (
    build_snapshot_manifest,
    compute_snapshot_hash,
    verify_snapshot_manifest,
    write_snapshot_manifest,
)


def _listing_proposal(*, recurse: bool = False) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_phase6_001",
        "created_at": "2026-05-04T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List reports",
            "justification": "Create a governed shell simulation receipt only.",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "phase6",
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
            "rationale": "Simulation only.",
        },
    }


def _sealed_listing_plan(*, recurse: bool = False) -> dict:
    normalized = normalize_and_hash_proposal(_listing_proposal(recurse=recurse))
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    if decision.confirmation_required:
        confirmation = require_confirmation(
            normalized.proposal_hash,
            normalized.proposal_hash,
            decision.confirmation_required,
            decision.confirmation_mode,
        )
    return build_execution_plan(normalized, decision, confirmation)


def test_snapshot_manifest_is_created_from_declared_paths(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports" / "operator"
    reports_dir.mkdir(parents=True)
    plan = _sealed_listing_plan()

    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    assert snapshot["targets"][0]["root_id"] == "reports"
    assert snapshot["targets"][0]["relative_path"] == "operator"
    assert snapshot["filesystem_observations"][0]["path_type"] == "directory"


def test_snapshot_contains_plan_hash_and_proposal_hash(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()

    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    assert snapshot["plan_hash"] == plan["plan_hash"]
    assert snapshot["proposal_hash"] == plan["proposal_hash"]


def test_snapshot_hash_verifies(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()
    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    verification = verify_snapshot_manifest(snapshot)

    assert verification.clean is True
    assert verification.snapshot_hash == snapshot["snapshot_hash"]


def test_changing_snapshot_content_invalidates_snapshot_hash(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()
    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)
    mutated = copy.deepcopy(snapshot)
    mutated["filesystem_observations"][0]["path_type"] = "file"

    verification = verify_snapshot_manifest(mutated)

    assert verification.clean is False
    assert any("snapshot_hash_mismatch" in issue for issue in verification.issues)


def test_snapshot_does_not_read_undeclared_paths(tmp_path: Path) -> None:
    declared_dir = tmp_path / "reports" / "operator"
    declared_dir.mkdir(parents=True)
    undeclared_file = tmp_path / "reports" / "secret.txt"
    undeclared_file.write_text("ignored", encoding="utf-8")
    plan = _sealed_listing_plan()

    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    observed_paths = {
        f"{row['root_id']}/{row['relative_path']}" for row in snapshot["filesystem_observations"]
    }
    assert "reports/operator" in observed_paths
    assert "reports/secret.txt" not in observed_paths


def test_snapshot_handles_missing_target_paths_explicitly(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()

    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    assert snapshot["filesystem_observations"][0]["exists"] is False
    assert snapshot["filesystem_observations"][0]["path_type"] == "missing"


def test_valid_sealed_read_only_plan_produces_simulation_receipt(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports" / "operator"
    reports_dir.mkdir(parents=True)
    plan = _sealed_listing_plan()

    receipt = simulate_plan(plan, snapshot_dir=tmp_path / "snapshots")

    assert receipt["plan_hash"] == plan["plan_hash"]
    assert receipt["mode"] == "simulation_only"


def test_receipt_has_executed_false(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")

    assert receipt["executed"] is False


def test_receipt_has_powershell_invoked_false(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")

    assert receipt["powershell_invoked"] is False


def test_receipt_has_network_accessed_false(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")

    assert receipt["network_accessed"] is False


def test_observed_writes_is_empty(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")

    assert receipt["observed_writes"] == []


def test_receipt_hash_verifies(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")

    verification = verify_simulation_receipt(receipt)

    assert verification.clean is True
    assert verification.receipt_hash == receipt["receipt_hash"]


def test_changing_receipt_content_invalidates_receipt_hash(tmp_path: Path) -> None:
    receipt = simulate_plan(_sealed_listing_plan(), snapshot_dir=tmp_path / "snapshots")
    mutated = copy.deepcopy(receipt)
    mutated["matched_binding_id"] = "tampered.binding"

    verification = verify_simulation_receipt(mutated)

    assert verification.clean is False
    assert any("receipt_hash_mismatch" in issue for issue in verification.issues)


def test_invalid_plan_hash_fails_simulation(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()
    plan["plan_hash"] = "sha256:" + ("f" * 64)

    with pytest.raises(SimulationError):
        simulate_plan(plan, snapshot_dir=tmp_path / "snapshots")


def test_audit_append_failure_fails_simulation(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked_parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    plan = _sealed_listing_plan()

    with pytest.raises(SimulationError):
        simulate_plan(
            plan,
            audit_path=blocked_parent / "audit.jsonl",
            snapshot_dir=tmp_path / "snapshots",
        )


def test_snapshot_failure_fails_simulation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _sealed_listing_plan()

    def _boom(*args, **kwargs):
        raise SnapshotError("snapshot failed")

    monkeypatch.setattr("app.governed_shell.executor.build_snapshot_manifest", _boom)

    with pytest.raises(SimulationError):
        simulate_plan(plan, snapshot_dir=tmp_path / "snapshots")


def test_simulation_with_audit_path_appends_started_and_finished(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"
    plan = _sealed_listing_plan()

    simulate_plan(plan, audit_path=audit_path, snapshot_dir=snapshot_dir)
    events = read_audit_events(audit_path)

    assert [event["event_type"] for event in events] == [
        "simulation_started",
        "simulation_finished",
    ]


def test_verify_log_passes_after_simulation_audit_events(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    simulate_plan(_sealed_listing_plan(), audit_path=audit_path, snapshot_dir=tmp_path / "snapshots")

    result = verify_log(audit_path)

    assert result.clean is True
    assert result.event_count == 2


def test_replay_session_includes_simulation_decision_trail(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    plan = _sealed_listing_plan()

    simulate_plan(plan, audit_path=audit_path, snapshot_dir=tmp_path / "snapshots")
    replay = replay_session(audit_path, plan["session_id"])

    assert replay.clean is True
    assert replay.decision_codes == ["simulation_started", "simulation_finished"]
    assert replay.latest_status == "simulated"


def test_snapshot_manifest_can_be_written_deterministically(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()
    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)
    path = tmp_path / "snapshot.json"

    written_path = write_snapshot_manifest(path, snapshot)

    assert written_path == path
    assert compute_snapshot_hash(snapshot) == snapshot["snapshot_hash"]


def test_build_simulation_receipt_preserves_empty_observed_writes(tmp_path: Path) -> None:
    plan = _sealed_listing_plan()
    snapshot = build_snapshot_manifest(plan, state_root=tmp_path)

    receipt = build_simulation_receipt(plan, snapshot)

    assert receipt["observed_writes"] == []
    assert compute_receipt_hash(receipt) == receipt["receipt_hash"]


def test_executor_module_contains_no_subprocess_usage() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "governed_shell" / "executor.py").read_text(
        encoding="utf-8"
    )

    assert "import subprocess" not in source
    assert "Popen(" not in source
    assert ".run(" not in source


def test_executor_module_contains_no_shell_invocation_tokens() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "governed_shell" / "executor.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "pwsh" not in source
    assert "powershell.exe" not in source
    assert "-command" not in source
    assert "start-process" not in source


def test_runner_placeholder_is_not_added_in_this_phase() -> None:
    runner_path = Path(__file__).resolve().parents[1] / "app" / "governed_shell" / "runner.ps1"
    assert runner_path.exists() is False
