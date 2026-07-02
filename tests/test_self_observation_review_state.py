from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from signal_agent.analytics.review_loop import create_review_artifact, record_review_decision
from signal_agent.analytics.review_state import (
    main,
    render_review_resolution_json,
    render_review_resolution_markdown,
    resolve_review_state,
)


REVIEW_STATE_MODULE = Path(__file__).resolve().parents[1] / "signal_agent" / "analytics" / "review_state.py"


def test_resolves_initial_state_when_no_decisions_log_exists(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)

    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert resolution["schema_version"] == "self_observation_review_resolution.v1"
    assert resolution["initial_review_state"] == "queued_for_review"
    assert resolution["resolved_review_state"] == "queued_for_review"
    assert resolution["matching_decision_event_count"] == 0
    assert resolution["latest_decision_record_id"] is None
    assert resolution["latest_decision_line_number"] is None
    assert resolution["resolution_method"] == "artifact_initial_review_state"


def test_resolves_initial_state_when_decisions_log_has_no_matching_event(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    _write_decisions(
        tmp_path,
        [
            _decision_event(
                review_artifact_id="sora_other",
                candidate_id="transition_denial:other",
                source_report_sha256="c" * 64,
                decision_record_id="sord_other",
                decision_state="rejected",
            )
        ],
    )

    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert resolution["resolved_review_state"] == "queued_for_review"
    assert resolution["matching_decision_event_count"] == 0


def test_resolves_accepted_for_proposal_from_matching_event(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Ready for governed proposal intake only.",
        decided_at="2026-01-01T01:00:00Z",
    )

    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert resolution["resolved_review_state"] == "accepted_for_proposal"
    assert resolution["matching_decision_event_count"] == 1
    assert resolution["latest_decision_record_id"]
    assert resolution["latest_decision_line_number"] == 1
    assert resolution["resolution_method"] == "latest_matching_decision_event"


def test_last_matching_jsonl_row_wins_without_timestamp_reordering(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="deferred",
        decided_by="operator-b",
        decision_reason="Later timestamp but earlier ledger row.",
        decided_at="2026-01-03T00:00:00Z",
    )
    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Earlier timestamp but later ledger row.",
        decided_at="2026-01-01T00:00:00Z",
    )

    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert resolution["resolved_review_state"] == "accepted_for_proposal"
    assert resolution["matching_decision_event_count"] == 2
    assert resolution["latest_decision_line_number"] == 2


def test_ignores_valid_decisions_for_different_artifact(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    _write_decisions(
        tmp_path,
        [
            _decision_event(
                review_artifact_id="sora_other",
                candidate_id=artifact["candidate_id"],
                source_report_sha256=artifact["source_report_sha256"],
                decision_record_id="sord_other",
                decision_state="accepted_for_proposal",
            )
        ],
    )

    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert resolution["resolved_review_state"] == "queued_for_review"
    assert resolution["matching_decision_event_count"] == 0


def test_rejects_malformed_artifact_input(tmp_path: Path) -> None:
    artifact_path = tmp_path / "data" / "analytics" / "review" / "artifacts" / "bad.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_rejects_artifact_schema_mismatch(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    artifact["schema_version"] = "unexpected.v1"
    artifact_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_rejects_artifact_path_outside_approved_directory(tmp_path: Path) -> None:
    bad_path = tmp_path / "data" / "analytics" / "artifact.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="data/analytics/review/artifacts"):
        resolve_review_state(repo_root=tmp_path, artifact_path=bad_path)


def test_rejects_artifact_missing_required_fields(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    del artifact["evidence_references"]
    artifact_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="evidence_references"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_rejects_malformed_decision_jsonl_rather_than_partial_resolution(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    decision_log = tmp_path / "data" / "analytics" / "review" / "decisions.jsonl"
    decision_log.write_text("{bad json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_rejects_duplicate_decision_record_id(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    event = _decision_event(
        review_artifact_id=artifact["review_artifact_id"],
        candidate_id=artifact["candidate_id"],
        source_report_sha256=artifact["source_report_sha256"],
        decision_record_id="sord_duplicate",
        decision_state="deferred",
    )
    _write_decisions(tmp_path, [event, dict(event, decision_state="rejected")])

    with pytest.raises(ValueError, match="duplicate decision_record_id"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_rejects_matching_event_with_report_hash_or_candidate_id_mismatch(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    _write_decisions(
        tmp_path,
        [
            _decision_event(
                review_artifact_id=artifact["review_artifact_id"],
                candidate_id=artifact["candidate_id"],
                source_report_sha256="d" * 64,
                decision_record_id="sord_conflict_hash",
                decision_state="deferred",
            )
        ],
    )

    with pytest.raises(ValueError, match="source_report_sha256"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    _write_decisions(
        tmp_path,
        [
            _decision_event(
                review_artifact_id=artifact["review_artifact_id"],
                candidate_id="transition_denial:other",
                source_report_sha256=artifact["source_report_sha256"],
                decision_record_id="sord_conflict_candidate",
                decision_state="deferred",
            )
        ],
    )

    with pytest.raises(ValueError, match="candidate_id"):
        resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)


def test_json_output_is_deterministic(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    assert render_review_resolution_json(resolution) == render_review_resolution_json(resolution)
    assert json.loads(render_review_resolution_json(resolution)) == resolution


def test_markdown_output_is_deterministic(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)

    first = render_review_resolution_markdown(resolution)
    second = render_review_resolution_markdown(resolution)

    assert first == second
    assert "resolved_review_state: queued_for_review" in first
    assert "Non-Authority Disclaimer" in first


def test_resolver_produces_no_files_and_does_not_modify_inputs(tmp_path: Path, capsys) -> None:
    artifact_path = _create_artifact(tmp_path)
    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Ready for governed proposal intake only.",
        decided_at="2026-01-01T01:00:00Z",
    )
    decision_log = tmp_path / "data" / "analytics" / "review" / "decisions.jsonl"
    artifact_before = artifact_path.read_bytes()
    decisions_before = decision_log.read_bytes()
    files_before = _file_set(tmp_path)

    exit_code = main(
        [
            "resolve",
            "--repo-root",
            str(tmp_path),
            "--artifact",
            str(artifact_path),
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["resolved_review_state"] == "accepted_for_proposal"
    assert _file_set(tmp_path) == files_before
    assert artifact_path.read_bytes() == artifact_before
    assert decision_log.read_bytes() == decisions_before
    assert not (tmp_path / "data" / "state").exists()


def test_static_review_state_has_no_forbidden_mutation_imports() -> None:
    forbidden_names = {
        "append_jsonl_atomic",
        "record_state",
        "emit_event",
        "emit_transition_event",
        "append_transport_ledger",
        "write_policy",
        "write_workflow",
        "execute_proposal",
        "enqueue",
        "schedule",
    }
    tree = ast.parse(REVIEW_STATE_MODULE.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_names:
                    violations.append(alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_names:
                    violations.append(alias.name)

    assert violations == []


def _create_artifact(root: Path, *, initial_review_state: str = "queued_for_review") -> Path:
    report_path = _write_report(root)
    result = create_review_artifact(
        repo_root=root,
        report_path=report_path,
        output_dir="data/analytics/review",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state=initial_review_state,
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )
    return Path(result["artifact_json_path"])


def _write_report(root: Path) -> Path:
    report = {
        "schema_version": "self_observation_report.v1",
        "repo_root": str(root),
        "source_files": {},
        "metrics": {},
        "repeated_patterns": {},
        "subsystem_candidates": [_candidate()],
        "recommendations": [],
        "warnings": [],
    }
    report_path = root / "data" / "analytics" / "self_observation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report_path


def _candidate() -> dict:
    return {
        "candidate_id": "transition_denial:abc123",
        "name_guess": "duplicate_record_protection_flow",
        "evidence": [
            {
                "source": "transition_events",
                "line_number": 7,
                "line_sha256": "a" * 64,
                "denial_category": "duplicate_protection",
                "denial_reason": "duplicate_record_detected",
            }
        ],
        "repeated_pattern": {
            "pattern_type": "transition_denial",
            "key": "duplicate_protection:duplicate_record_detected",
            "repetition_count": 3,
            "weak_legacy_evidence_count": 0,
            "distinct_evidence_surface_count": 1,
        },
        "involved_files_or_events": [
            "transition_events:line=7:sha256=aaaaaaaaaaaaaaaa",
        ],
        "confidence": 0.75,
        "recommended_next_action": "Review the observed candidate evidence; do not mutate state.",
    }


def _decision_event(
    *,
    review_artifact_id: str,
    candidate_id: str,
    source_report_sha256: str,
    decision_record_id: str,
    decision_state: str,
) -> dict:
    return {
        "schema_version": "self_observation_review_event.v1",
        "review_artifact_id": review_artifact_id,
        "source_report_sha256": source_report_sha256,
        "candidate_id": candidate_id,
        "decision_record_id": decision_record_id,
        "decision_state": decision_state,
        "decided_by": "operator-b",
        "decision_reason": "Review decision for resolver test.",
        "decided_at": "2026-01-01T01:00:00Z",
        "non_authority_disclaimer": "Review input only; not implementation authorization.",
    }


def _write_decisions(root: Path, rows: list[dict]) -> Path:
    decision_log = root / "data" / "analytics" / "review" / "decisions.jsonl"
    decision_log.parent.mkdir(parents=True, exist_ok=True)
    decision_log.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return decision_log


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_set(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    }
