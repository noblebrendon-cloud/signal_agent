from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from signal_agent.analytics import (
    build_self_observation_report,
    read_jsonl_with_metadata,
    render_self_observation_markdown,
    write_self_observation_report,
)


ANALYTICS_PKG = Path(__file__).resolve().parents[1] / "signal_agent" / "analytics"
ALLOWED_ANALYTICS_FILES = {
    "__init__.py",
    "metrics.py",
    "proposal_intake.py",
    "report_builder.py",
    "review_loop.py",
    "review_state.py",
    "self_observation.py",
    "subsystem_detection.py",
}
ALLOWED_ANALYTICS_WRITER_FILES = {"proposal_intake.py", "report_builder.py", "review_loop.py"}


def _write_jsonl(path: Path, rows: list[dict | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        row if isinstance(row, str) else json.dumps(row, sort_keys=True)
        for row in rows
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sample_workspace(root: Path) -> Path:
    state_dir = root / "data" / "state"
    runs_dir = root / "data" / "operator" / "runs"

    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "run_id": "transition_001",
                "artifact_id": "artifact-a",
                "lane_id": "content_publishing",
                "current_state": "captured",
                "attempted_state": "promoted",
                "policy_result": {"allowed": True, "failures": []},
                "status": "allowed",
                "module": "module.alpha",
                "operation": "promote",
            },
            {
                "event_type": "transition_attempt",
                "timestamp_utc": "2026-01-01T00:01:00Z",
                "run_id": "transition_002",
                "artifact_id": "artifact-a",
                "lane_id": "content_publishing",
                "current_state": "promoted",
                "attempted_state": "routed",
                "policy_result": {"allowed": False, "failures": ["lane_operational"]},
                "status": "rejected",
                "reason": "lane_not_operational",
                "module": "module.alpha",
                "operation": "route",
            },
            {
                "event_type": "transition_attempt",
                "timestamp_utc": "2026-01-01T00:02:00Z",
                "run_id": "transition_003",
                "artifact_id": "artifact-b",
                "lane_id": "content_publishing",
                "current_state": "captured",
                "attempted_state": "promoted",
                "policy_result": {"allowed": True, "failures": []},
                "status": "allowed",
                "module": "module.alpha",
                "operation": "promote",
            },
            {
                "event_type": "transition_attempt",
                "timestamp_utc": "2026-01-01T00:03:00Z",
                "run_id": "transition_004",
                "artifact_id": "artifact-b",
                "lane_id": "content_publishing",
                "current_state": "promoted",
                "attempted_state": "routed",
                "policy_result": {"allowed": False, "failures": ["lane_operational"]},
                "status": "rejected",
                "reason": "lane_not_operational",
                "module": "module.alpha",
                "operation": "route",
            },
        ],
    )
    _write_jsonl(
        state_dir / "event_log.jsonl",
        [
            {
                "event_type": "semantic_cache_hit_validated",
                "artifact_id": "artifact-a",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "workflow_id": "wf-alpha",
                    "artifact_id": "artifact-a",
                    "semantic_reuse_attempted": True,
                },
            },
            {
                "event_type": "semantic_cache_miss",
                "artifact_id": "artifact-b",
                "timestamp": "2026-01-01T00:01:00Z",
                "payload": {
                    "workflow_id": "wf-alpha",
                    "artifact_id": "artifact-b",
                    "semantic_reuse_attempted": True,
                    "reason_code": "threshold_not_met",
                },
            },
        ],
    )
    _write_jsonl(
        state_dir / "artifact_registry.jsonl",
        [
            {
                "artifact_id": "artifact-a",
                "state": "captured",
                "path": str(root / "data" / "outputs" / "alpha.md"),
            },
            {
                "artifact_id": "artifact-b",
                "state": "captured",
                "path": str(root / "data" / "outputs" / "beta.md"),
            },
            {
                "artifact_id": "artifact-c",
                "state": "captured",
                "path": str(root / "data" / "outputs" / "gamma.md"),
            },
        ],
    )
    _write_jsonl(
        state_dir / "provider_events.jsonl",
        [
            {
                "event": "provider_unavailable",
                "request_id": "req-1",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "event": "retry_attempt",
                "request_id": "req-1",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:00:01Z",
            },
            {
                "event": "circuit_opened",
                "request_id": "req-1",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:00:02Z",
            },
            {
                "event": "fallback_selected",
                "request_id": "req-1",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:00:03Z",
            },
            {
                "event": "provider_unavailable",
                "request_id": "req-2",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:01:00Z",
            },
            {
                "event": "retry_attempt",
                "request_id": "req-2",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:01:01Z",
            },
            {
                "event": "circuit_opened",
                "request_id": "req-2",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:01:02Z",
            },
            {
                "event": "fallback_selected",
                "request_id": "req-2",
                "provider_id": "google",
                "model_id": "gemini-test",
                "timestamp": "2026-01-01T00:01:03Z",
            },
        ],
    )
    _write_jsonl(
        runs_dir / "operator_runs.jsonl",
        [
            {
                "run_id": "operator-1",
                "status": "ok",
                "workflow_id": "wf-alpha",
                "target_workflow_id": "wf-alpha",
            },
            {
                "run_id": "operator-2",
                "status": "rejected",
                "workflow_id": "wf-alpha",
                "target_workflow_id": "wf-alpha",
            },
            {
                "run_id": "operator-3",
                "status": "ok",
                "workflow_id": "wf-beta",
                "target_workflow_id": "wf-beta",
            },
        ],
    )
    _write_jsonl(
        state_dir / "inference_cache_registry.jsonl",
        [
            {
                "record_type": "semantic_cache_entry",
                "record_version": "1",
                "entry_id": "entry-a",
                "workflow_id": "wf-alpha",
                "workflow_mode": "read_only",
                "artifact_id": "artifact-a",
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-02T00:00:00Z",
            }
        ],
    )
    return root


def test_parser_reports_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write_jsonl(path, [{"ok": True}, "{bad json", ["not", "an", "object"]])

    result = read_jsonl_with_metadata(path, source_name="events")

    assert result.exists is True
    assert result.sha256
    assert len(result.parsed_rows) == 1
    assert len(result.malformed_lines) == 2
    assert result.malformed_lines[0]["line_number"] == 2
    assert "line_sha256" in result.malformed_lines[0]


def test_metrics_are_explicit_and_cache_summary_is_available(tmp_path: Path) -> None:
    workspace = _sample_workspace(tmp_path)

    report = build_self_observation_report(workspace)
    metrics = report["metrics"]

    assert metrics["transition_counts_by_status"] == {"allowed": 2, "rejected": 2}
    assert metrics["failed_transition_count"] == 2
    assert metrics["policy_denial_count"] == 2
    assert metrics["policy_denials_by_reason"]["lane_not_operational"] == 2
    assert metrics["workflow_invocation_counts"]["wf-alpha"] == 2
    assert metrics["provider_retry_count"] == 2
    assert metrics["provider_fallback_count"] == 2
    assert metrics["circuit_breaker_count"] == 2
    assert metrics["provider_failures_by_model"]["google:gemini-test"] == 2
    cache_summary = metrics["cache_summary"]
    if cache_summary["available"]:
        assert cache_summary["semantic_reuse_attempted_count"] == 2
    else:
        assert cache_summary["reason"] == "inference_cache_audit_unavailable"


def test_metrics_prefer_classified_denial_reason_and_keep_old_events(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "denial_reason": "classified_duplicate",
                "reason": "legacy_duplicate",
                "policy_result": {"allowed": False, "failures": ["legacy_failure"]},
            },
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "reason": "legacy_reason",
                "policy_result": {"allowed": False, "failures": ["legacy_failure"]},
            },
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "policy_result": {"allowed": False, "failures": ["policy_failure_only"]},
            },
        ],
    )

    report = build_self_observation_report(tmp_path)

    assert report["metrics"]["policy_denials_by_reason"] == {
        "classified_duplicate": 1,
        "legacy_reason": 1,
        "policy_failure_only": 1,
    }


def test_transition_classification_coverage_separates_evidence_quality(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            _classified_transition_row(index=1),
            {
                "event_type": "activation_review_init",
                "status": "rejected",
                "run_id": "explicit-unknown",
                "source_module": "app.governor.activation_governor",
                "source_operation": "REVIEW_INIT",
                "denial_reason": "activation_event_without_denial_reason",
                "denial_category": "unknown",
                "denial_subtype": "activation_event_without_denial_reason",
            },
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "run_id": "legacy-reason",
                "reason": "legacy_reason",
                "policy_result": {"allowed": False, "failures": ["legacy_failure"]},
            },
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "run_id": "legacy-policy",
                "policy_result": {"allowed": False, "failures": ["policy_failure_only"]},
            },
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "run_id": "legacy-unknown",
            },
        ],
    )

    metrics = build_self_observation_report(tmp_path)["metrics"]

    assert metrics["rejected_transition_count"] == 5
    assert metrics["explicitly_classified_rejection_count"] == 2
    assert metrics["legacy_fallback_rejection_count"] == 2
    assert metrics["legacy_unknown_rejection_count"] == 1
    assert metrics["classification_coverage_ratio"] == 0.4
    assert metrics["rejection_evidence_quality_counts"] == {
        "explicit_classification": 2,
        "legacy_reason": 1,
        "legacy_policy_failure": 1,
        "legacy_unknown": 1,
    }
    assert metrics["denial_reasons_by_evidence_quality"] == {
        "explicit_classification": {
            "activation_event_without_denial_reason": 1,
            "duplicate_record_detected": 1,
        },
        "legacy_reason": {"legacy_reason": 1},
        "legacy_policy_failure": {"policy_failure_only": 1},
        "legacy_unknown": {"unknown_denial": 1},
    }
    assert metrics["denial_categories_by_source"] == {
        "app.governor.activation_governor:REVIEW_INIT": {"unknown": 1},
        "signal_agent.operator.runtime:compound_gate_rejected": {"duplicate_protection": 1},
    }


def test_subsystem_candidate_requires_minimum_repetition_threshold(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            _classified_transition_row(index=1),
            _classified_transition_row(index=2),
        ],
    )

    report = build_self_observation_report(tmp_path)

    assert report["subsystem_candidates"] == []


def test_legacy_unknown_denials_alone_do_not_create_subsystem_candidate(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            {
                "event_type": "activation_review_init",
                "status": "rejected",
                "module": "app.governor.activation_governor",
                "operation": "REVIEW_INIT",
                "run_id": f"legacy-{index}",
            }
            for index in range(1, 5)
        ],
    )

    report = build_self_observation_report(tmp_path)

    assert report["metrics"]["policy_denials_by_reason"] == {"unknown_denial": 4}
    assert report["subsystem_candidates"] == []


def test_explicit_classification_rows_create_evidence_backed_candidate(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [_classified_transition_row(index=index) for index in range(1, 4)],
    )

    report = build_self_observation_report(tmp_path)
    candidates = report["subsystem_candidates"]
    duplicate_candidate = next(
        candidate
        for candidate in candidates
        if candidate["repeated_pattern"]["pattern_type"] == "transition_denial"
    )

    assert duplicate_candidate["name_guess"] == "duplicate_record_protection_flow"
    assert duplicate_candidate["repeated_pattern"]["repetition_count"] == 3
    assert duplicate_candidate["confidence"] == 0.75
    assert duplicate_candidate["evidence"]
    assert all(item["line_number"] for item in duplicate_candidate["evidence"])
    assert all(item["line_sha256"] for item in duplicate_candidate["evidence"])
    assert all(
        ref.startswith("transition_events:line=")
        for ref in duplicate_candidate["involved_files_or_events"]
    )
    assert duplicate_candidate["candidate_id"].startswith("transition_denial:")


def test_candidate_ids_are_stable_and_distinct_for_shared_name_guess(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "provider_events.jsonl",
        [
            {
                "event": "provider_unavailable",
                "provider_id": provider_id,
                "model_id": "model",
                "request_id": f"{provider_id}-{index}",
            }
            for provider_id in ("mock", "google")
            for index in range(1, 4)
        ],
    )

    first_report = build_self_observation_report(tmp_path)
    second_report = build_self_observation_report(tmp_path)
    candidates = [
        candidate
        for candidate in first_report["subsystem_candidates"]
        if candidate["name_guess"] == "provider_retry_fallback_flow"
    ]

    assert len(candidates) == 2
    assert len({candidate["candidate_id"] for candidate in candidates}) == 2
    assert first_report["subsystem_candidates"] == second_report["subsystem_candidates"]


def test_no_subsystem_candidate_without_stable_grouping_key(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "rejected",
                "denial_reason": "classified_but_ungrouped",
                "run_id": f"ungrouped-{index}",
            }
            for index in range(1, 5)
        ],
    )

    report = build_self_observation_report(tmp_path)

    assert report["subsystem_candidates"] == []


def test_subsystem_candidate_output_is_deterministic(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / "state"
    _write_jsonl(
        state_dir / "transition_gate_events.jsonl",
        [_classified_transition_row(index=index) for index in range(1, 4)],
    )
    first_report = build_self_observation_report(tmp_path)
    second_report = build_self_observation_report(tmp_path)

    assert first_report["subsystem_candidates"] == second_report["subsystem_candidates"]
    assert render_self_observation_markdown(first_report) == render_self_observation_markdown(second_report)


def test_report_rendering_and_json_output_are_deterministic(tmp_path: Path) -> None:
    workspace = _sample_workspace(tmp_path)
    report = build_self_observation_report(workspace)
    first_json = workspace / "data" / "analytics" / "first.json"
    first_md = workspace / "data" / "analytics" / "first.md"
    second_json = workspace / "data" / "analytics" / "second.json"
    second_md = workspace / "data" / "analytics" / "second.md"

    write_self_observation_report(report, first_json, first_md)
    write_self_observation_report(report, second_json, second_md)

    assert first_json.read_text(encoding="utf-8") == second_json.read_text(encoding="utf-8")
    assert first_md.read_text(encoding="utf-8") == second_md.read_text(encoding="utf-8")
    assert render_self_observation_markdown(report) == first_md.read_text(encoding="utf-8")
    assert "## Subsystem Candidates" in first_md.read_text(encoding="utf-8")


def test_report_writer_rejects_canonical_state_paths(tmp_path: Path) -> None:
    workspace = _sample_workspace(tmp_path)
    report = build_self_observation_report(workspace)

    with pytest.raises(ValueError):
        write_self_observation_report(report, workspace / "data" / "state" / "bad.json")
    with pytest.raises(ValueError):
        write_self_observation_report(report, workspace / "signal_agent" / "bad.json")


def test_static_boundary_has_no_canonical_mutation_imports() -> None:
    forbidden_imports = {
        "append_jsonl_atomic",
        "record_state",
        "emit_event",
        "emit_transition_event",
    }
    violations: list[str] = []
    for py_file in ANALYTICS_PKG.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        violations.append(f"{py_file.name}: {alias.name}")

    assert violations == []


def test_analytics_package_contains_only_stage_1_to_4_files() -> None:
    actual_files = {
        py_file.name
        for py_file in ANALYTICS_PKG.glob("*.py")
    }

    assert actual_files == ALLOWED_ANALYTICS_FILES


def test_static_boundary_only_report_builder_writes_files() -> None:
    violations: list[str] = []
    for py_file in ANALYTICS_PKG.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if py_file.name in ALLOWED_ANALYTICS_WRITER_FILES:
            continue
        if ".write_text(" in content or ".write_bytes(" in content or "open(" in content:
            violations.append(py_file.name)

    assert violations == []


def _classified_transition_row(*, index: int) -> dict:
    return {
        "event_type": "operator_transition_rejected",
        "status": "rejected",
        "run_id": f"transition-{index}",
        "artifact_id": f"artifact-{index}",
        "current_state": "captured",
        "attempted_state": "promoted",
        "state_from": "captured",
        "state_to": "promoted",
        "source_module": "signal_agent.operator.runtime",
        "source_operation": "compound_gate_rejected",
        "module": "signal_agent.operator.runtime",
        "operation": "compound_gate_rejected",
        "denial_reason": "duplicate_record_detected",
        "denial_category": "duplicate_protection",
        "denial_subtype": "duplicate_record_detected",
        "policy_rule_id": None,
        "policy_result": None,
    }
