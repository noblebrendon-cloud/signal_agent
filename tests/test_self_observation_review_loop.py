from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from signal_agent.analytics.review_loop import (
    NON_AUTHORITY_DISCLAIMER,
    build_review_artifact,
    create_review_artifact,
    main,
    record_review_decision,
    render_review_artifact_markdown,
)


REVIEW_LOOP_MODULE = Path(__file__).resolve().parents[1] / "signal_agent" / "analytics" / "review_loop.py"


def test_rejects_report_schema_mismatch(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path, schema_version="unexpected.v1")

    with pytest.raises(ValueError, match="schema_version"):
        build_review_artifact(
            repo_root=tmp_path,
            report_path=report_path,
            candidate_id="transition_denial:abc123",
            proposal_type="instrumentation_proposal",
            initial_review_state="queued_for_review",
            created_by="operator-a",
            created_at="2026-01-01T00:00:00Z",
        )


def test_rejects_missing_candidate_id(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)

    with pytest.raises(ValueError, match="candidate_id not found"):
        build_review_artifact(
            repo_root=tmp_path,
            report_path=report_path,
            candidate_id="transition_denial:missing",
            proposal_type="instrumentation_proposal",
            initial_review_state="queued_for_review",
            created_by="operator-a",
            created_at="2026-01-01T00:00:00Z",
        )


def test_rejects_candidate_without_exact_evidence_references(tmp_path: Path) -> None:
    candidate = _candidate(
        evidence=[],
        involved_files_or_events=[],
    )
    report_path = _write_report(tmp_path, candidates=[candidate])

    with pytest.raises(ValueError, match="exact evidence references"):
        build_review_artifact(
            repo_root=tmp_path,
            report_path=report_path,
            candidate_id=candidate["candidate_id"],
            proposal_type="instrumentation_proposal",
            initial_review_state="queued_for_review",
            created_by="operator-a",
            created_at="2026-01-01T00:00:00Z",
        )


def test_requires_explicit_creation_actor_and_timestamp(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)

    with pytest.raises(ValueError, match="created_by"):
        build_review_artifact(
            repo_root=tmp_path,
            report_path=report_path,
            candidate_id="transition_denial:abc123",
            proposal_type="instrumentation_proposal",
            initial_review_state="queued_for_review",
            created_by="",
            created_at="2026-01-01T00:00:00Z",
        )
    with pytest.raises(ValueError, match="created_at"):
        build_review_artifact(
            repo_root=tmp_path,
            report_path=report_path,
            candidate_id="transition_denial:abc123",
            proposal_type="instrumentation_proposal",
            initial_review_state="queued_for_review",
            created_by="operator-a",
            created_at="",
        )


def test_creates_deterministic_json_and_markdown_artifact_output(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    first = build_review_artifact(
        repo_root=tmp_path,
        report_path="data/analytics/self_observation_report.json",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )
    second = build_review_artifact(
        repo_root=tmp_path,
        report_path="data/analytics/self_observation_report.json",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )

    assert first == second
    assert render_review_artifact_markdown(first) == render_review_artifact_markdown(second)

    result = create_review_artifact(
        repo_root=tmp_path,
        report_path=report_path,
        output_dir="data/analytics/review",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )
    artifact_json = Path(result["artifact_json_path"])
    artifact_md = Path(result["artifact_markdown_path"])

    assert json.loads(artifact_json.read_text(encoding="utf-8")) == first
    assert artifact_md.read_text(encoding="utf-8") == render_review_artifact_markdown(first)


def test_artifact_preserves_report_hash_candidate_evidence_quality_and_disclaimer(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()

    artifact = build_review_artifact(
        repo_root=tmp_path,
        report_path=report_path,
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )

    assert artifact["source_report_sha256"] == report_sha256
    assert artifact["source_report_schema_version"] == "self_observation_report.v1"
    assert artifact["candidate_id"] == "transition_denial:abc123"
    assert artifact["evidence_references"] == {
        "candidate_evidence": _candidate()["evidence"],
        "involved_files_or_events": _candidate()["involved_files_or_events"],
    }
    assert artifact["evidence_quality"] == {
        "status": "unavailable",
        "reason": "candidate_evidence_quality_not_present_in_report",
    }
    assert artifact["non_authority_disclaimer"] == NON_AUTHORITY_DISCLAIMER


def test_preserves_candidate_evidence_quality_when_present(tmp_path: Path) -> None:
    candidate = _candidate(evidence_quality={"explicit_classification": 3})
    report_path = _write_report(tmp_path, candidates=[candidate])

    artifact = build_review_artifact(
        repo_root=tmp_path,
        report_path=report_path,
        candidate_id=candidate["candidate_id"],
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )

    assert artifact["evidence_quality"] == {"explicit_classification": 3}


def test_appends_exactly_one_decision_event(tmp_path: Path) -> None:
    result = _create_artifact_output(tmp_path)
    event_result = record_review_decision(
        repo_root=tmp_path,
        artifact_path=result["artifact_json_path"],
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Evidence is specific enough for governed proposal intake.",
        decided_at="2026-01-01T01:00:00Z",
    )

    decision_log = Path(event_result["decision_log_path"])
    rows = [
        json.loads(line)
        for line in decision_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    assert rows[0]["schema_version"] == "self_observation_review_event.v1"
    assert rows[0]["decision_state"] == "accepted_for_proposal"
    assert rows[0]["decided_by"] == "operator-b"
    assert rows[0]["candidate_id"] == "transition_denial:abc123"
    assert rows[0]["non_authority_disclaimer"] == NON_AUTHORITY_DISCLAIMER


def test_rejects_duplicate_decision_record_id_without_appending(tmp_path: Path) -> None:
    result = _create_artifact_output(tmp_path)
    kwargs = {
        "repo_root": tmp_path,
        "artifact_path": result["artifact_json_path"],
        "output_dir": "data/analytics/review",
        "decision_state": "accepted_for_proposal",
        "decided_by": "operator-b",
        "decision_reason": "Evidence is specific enough for governed proposal intake.",
        "decided_at": "2026-01-01T01:00:00Z",
    }

    record_review_decision(**kwargs)
    decision_log = tmp_path / "data" / "analytics" / "review" / "decisions.jsonl"
    before = decision_log.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        record_review_decision(**kwargs)

    assert decision_log.read_text(encoding="utf-8") == before
    assert len(before.splitlines()) == 1


def test_rejects_canonical_and_external_output_paths(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    forbidden_outputs = [
        tmp_path / "data" / "state",
        tmp_path / "config",
        tmp_path / "governance",
        tmp_path / "constraints",
        tmp_path / "formal_governance",
        tmp_path / "signal_agent",
        tmp_path / "app",
        tmp_path.parent / "external-review",
    ]

    for output_dir in forbidden_outputs:
        with pytest.raises(ValueError):
            create_review_artifact(
                repo_root=tmp_path,
                report_path=report_path,
                output_dir=output_dir,
                candidate_id="transition_denial:abc123",
                proposal_type="instrumentation_proposal",
                initial_review_state="queued_for_review",
                created_by="operator-a",
                created_at="2026-01-01T00:00:00Z",
            )


def test_accepted_for_proposal_creates_only_review_event(tmp_path: Path) -> None:
    result = _create_artifact_output(tmp_path)
    artifact_path = Path(result["artifact_json_path"])
    artifact_before = artifact_path.read_bytes()

    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Queue for later governed proposal drafting only.",
        decided_at="2026-01-01T01:00:00Z",
    )

    assert artifact_path.read_bytes() == artifact_before
    assert (tmp_path / "data" / "analytics" / "review" / "decisions.jsonl").exists()
    assert not (tmp_path / "data" / "state").exists()
    assert not (tmp_path / "data" / "analytics" / "review" / "proposals").exists()


def test_cli_create_and_decide_write_only_review_paths(tmp_path: Path, capsys) -> None:
    _write_report(tmp_path)
    create_exit = main(
        [
            "create",
            "--repo-root",
            str(tmp_path),
            "--report",
            "data/analytics/self_observation_report.json",
            "--output-dir",
            "data/analytics/review",
            "--candidate-id",
            "transition_denial:abc123",
            "--proposal-type",
            "instrumentation_proposal",
            "--initial-review-state",
            "queued_for_review",
            "--created-by",
            "operator-a",
            "--created-at",
            "2026-01-01T00:00:00Z",
        ]
    )
    assert create_exit == 0
    create_payload = json.loads(capsys.readouterr().out)

    decide_exit = main(
        [
            "decide",
            "--repo-root",
            str(tmp_path),
            "--artifact",
            create_payload["artifact_json_path"],
            "--output-dir",
            "data/analytics/review",
            "--decision-state",
            "accepted_for_proposal",
            "--decided-by",
            "operator-b",
            "--decision-reason",
            "Evidence is ready for human-governed proposal intake.",
            "--decided-at",
            "2026-01-01T01:00:00Z",
        ]
    )

    assert decide_exit == 0
    assert Path(create_payload["artifact_json_path"]).is_file()
    assert (tmp_path / "data" / "analytics" / "review" / "decisions.jsonl").is_file()
    assert not (tmp_path / "data" / "state").exists()


def test_static_review_loop_has_no_forbidden_mutation_imports() -> None:
    forbidden_names = {
        "append_jsonl_atomic",
        "record_state",
        "emit_event",
        "emit_transition_event",
        "append_transport_ledger",
        "write_policy",
        "write_workflow",
        "execute_proposal",
    }
    tree = ast.parse(REVIEW_LOOP_MODULE.read_text(encoding="utf-8"))
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


def _create_artifact_output(tmp_path: Path) -> dict[str, str]:
    report_path = _write_report(tmp_path)
    return create_review_artifact(
        repo_root=tmp_path,
        report_path=report_path,
        output_dir="data/analytics/review",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
        created_by="operator-a",
        created_at="2026-01-01T00:00:00Z",
    )


def _write_report(
    root: Path,
    *,
    schema_version: str = "self_observation_report.v1",
    candidates: list[dict] | None = None,
) -> Path:
    report = {
        "schema_version": schema_version,
        "repo_root": str(root),
        "source_files": {},
        "metrics": {},
        "repeated_patterns": {},
        "subsystem_candidates": candidates if candidates is not None else [_candidate()],
        "recommendations": [],
        "warnings": [],
    }
    report_path = root / "data" / "analytics" / "self_observation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report_path


def _candidate(**overrides) -> dict:
    candidate = {
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
    candidate.update(overrides)
    return candidate
