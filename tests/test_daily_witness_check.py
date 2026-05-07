from pathlib import Path
import json

import pytest

from signal_agent.health import daily_check
from signal_agent.health.daily_check import (
    _assert_within,
    _build_snapshot,
    _classify,
    _print_compact_summary,
    _render_markdown_report,
    _stable_json,
    _stage_git_state,
    _summary_from_stages,
    StageResult,
)


def test_classify_chooses_most_conservative_status() -> None:
    stages = [
        StageResult(name="git_state", status="healthy"),
        StageResult(name="runtime_health", status="degraded"),
        StageResult(name="targeted_tests", status="failed"),
    ]

    assert _classify(stages) == "failed"


def test_classify_hard_failure_wins_over_unverified() -> None:
    stages = [
        StageResult(name="runtime_health", status="unverified"),
        StageResult(name="ledger_validation", status="degraded", hard_failures=["malformed canonical ledger"]),
    ]

    assert _classify(stages) == "failed"


def test_classify_unverified_wins_over_degraded_without_hard_failure() -> None:
    stages = [
        StageResult(name="git_state", status="degraded", drift_warnings=["dirty tree"]),
        StageResult(name="targeted_tests", status="unverified", soft_failures=["tests skipped"]),
    ]

    assert _classify(stages) == "unverified"


def test_summary_counts_degraded_unverified_and_failed_stages() -> None:
    stages = [
        StageResult(name="git_state", status="degraded", drift_warnings=["dirty tree"]),
        StageResult(name="targeted_tests", status="unverified", soft_failures=["tests skipped"]),
        StageResult(name="ledger_validation", status="failed", hard_failures=["bad ledger"]),
    ]

    summary = _summary_from_stages(stages)

    assert summary["hard_failure_count"] == 1
    assert summary["soft_degradation_count"] == 1
    assert summary["drift_warning_count"] == 1
    assert summary["failed_stage_count"] == 1
    assert summary["degraded_stage_count"] == 1
    assert summary["unverified_stage_count"] == 1


def test_snapshot_json_declares_operator_action_and_prohibited_operations(tmp_path: Path) -> None:
    stages = [StageResult(name="git_state", status="healthy", informational=["git metadata captured"])]

    snapshot = _build_snapshot(
        repo_root=tmp_path,
        run_id="daily-witness-test",
        started_at="2026-05-07T00:00:00Z",
        finished_at="2026-05-07T00:00:01Z",
        status="healthy",
        stages=stages,
        command_logs=[],
    )
    decoded = json.loads(_stable_json(snapshot))

    assert decoded["status_meaning"] == "no hard failures or known drift warnings"
    assert decoded["next_operator_action"] == "review_summary_no_intervention_required"
    assert "auto-commit" in decoded["safe_execution_boundaries"]["prohibited_operations"]
    assert decoded["safe_execution_boundaries"]["network_actions"] == []
    assert decoded["safe_execution_boundaries"]["production_state_mutations"] == []


def test_markdown_report_includes_status_semantics_and_next_action(tmp_path: Path) -> None:
    stages = [StageResult(name="git_state", status="degraded", drift_warnings=["dirty tree"])]
    snapshot = _build_snapshot(
        repo_root=tmp_path,
        run_id="daily-witness-test",
        started_at="2026-05-07T00:00:00Z",
        finished_at="2026-05-07T00:00:01Z",
        status="degraded",
        stages=stages,
        command_logs=[],
    )

    report = _render_markdown_report(snapshot)

    assert "Meaning: review required, not emergency" in report
    assert "Next operator action: `review_report_and_plan_remediation_if_repeated`" in report
    assert "| unverified_stages | `0` |" in report
    assert "hard failures classify the run as failed" in report


def test_console_summary_includes_next_action_and_stage_counts(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    stages = [StageResult(name="git_state", status="degraded", drift_warnings=["dirty tree"])]
    snapshot = _build_snapshot(
        repo_root=tmp_path,
        run_id="daily-witness-test",
        started_at="2026-05-07T00:00:00Z",
        finished_at="2026-05-07T00:00:01Z",
        status="degraded",
        stages=stages,
        command_logs=[],
    )
    snapshot["artifacts"]["snapshot"] = {"path": "data/state/witness/snapshots/test.json"}
    snapshot["artifacts"]["report"] = {"path": "data/state/witness/reports/test.md"}
    snapshot["artifacts"]["manifest"] = {"path": "data/state/witness/manifests/test.manifest.json"}

    _print_compact_summary(snapshot)

    output = capsys.readouterr().out
    assert "final_status=degraded" in output
    assert "next_operator_action=review_report_and_plan_remediation_if_repeated" in output
    assert "unverified_stages=0" in output
    assert "degraded_stages=1" in output
    assert "report=data/state/witness/reports/test.md" in output


def test_dirty_repo_state_degrades_without_running_real_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict:
        del cwd, timeout_seconds
        if command == ["git", "rev-parse", "HEAD"]:
            stdout = "abc123\n"
        elif command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            stdout = "main\n"
        elif command == ["git", "status", "--short"]:
            stdout = " M file.py\n?? new.txt\n"
        else:
            raise AssertionError(f"unexpected command: {command}")
        return {
            "command": command,
            "status": "completed",
            "returncode": 0,
            "duration_seconds": 0.001,
            "stdout": stdout,
            "stderr": "",
        }

    monkeypatch.setattr(daily_check, "_run_command", fake_run_command)

    stage = _stage_git_state(tmp_path, timeout_seconds=1)

    assert stage.status == "degraded"
    assert stage.data["dirty_count"] == 2
    assert stage.drift_warnings == ["working tree has 2 changed or untracked paths"]


def test_witness_write_boundary_rejects_outside_path(tmp_path: Path) -> None:
    witness_root = tmp_path / "data" / "state" / "witness"
    outside_path = tmp_path / "data" / "state" / "module_artifacts.jsonl"

    with pytest.raises(ValueError, match="witness_write_outside_owned_root"):
        _assert_within(witness_root, outside_path)
