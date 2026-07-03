from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from signal_agent.analytics.proposal_intake import (
    build_intake_candidate,
    create_intake_candidate,
    main,
    render_intake_candidate_markdown,
)
from signal_agent.analytics.review_loop import create_review_artifact, record_review_decision
from signal_agent.analytics.review_state import render_review_resolution_json, resolve_review_state


PROPOSAL_INTAKE_MODULE = (
    Path(__file__).resolve().parents[1] / "signal_agent" / "analytics" / "proposal_intake.py"
)


def test_rejects_artifact_schema_mismatch(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    artifact["schema_version"] = "unexpected.v1"
    artifact_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_artifact_path_outside_approved_artifact_directory(tmp_path: Path) -> None:
    bad_path = tmp_path / "data" / "analytics" / "artifact.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="data/analytics/review/artifacts"):
        _build_candidate(tmp_path, bad_path)


def test_rejects_missing_required_artifact_fields(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    del artifact["proposal_type"]
    artifact_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="proposal_type"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_no_decision_log(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)

    with pytest.raises(ValueError, match="decisions.jsonl"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_resolved_state_other_than_accepted_for_proposal(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    record_review_decision(
        repo_root=tmp_path,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="deferred",
        decided_by="operator-b",
        decision_reason="Keep watching before intake.",
        decided_at="2026-01-01T01:00:00Z",
    )

    with pytest.raises(ValueError, match="accepted_for_proposal"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_malformed_decision_jsonl(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    decision_log = tmp_path / "data" / "analytics" / "review" / "decisions.jsonl"
    decision_log.write_text("{bad json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_duplicate_decision_record_id(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    event = _decision_event(
        review_artifact_id=artifact["review_artifact_id"],
        candidate_id=artifact["candidate_id"],
        source_report_sha256=artifact["source_report_sha256"],
        decision_record_id="sord_duplicate",
        decision_state="accepted_for_proposal",
    )
    _write_decisions(tmp_path, [event, dict(event, decision_state="deferred")])

    with pytest.raises(ValueError, match="duplicate decision_record_id"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_latest_matching_decision_with_report_hash_mismatch(tmp_path: Path) -> None:
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
                decision_state="accepted_for_proposal",
            )
        ],
    )

    with pytest.raises(ValueError, match="source_report_sha256"):
        _build_candidate(tmp_path, artifact_path)


def test_rejects_latest_matching_decision_with_candidate_id_mismatch(tmp_path: Path) -> None:
    artifact_path = _create_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    _write_decisions(
        tmp_path,
        [
            _decision_event(
                review_artifact_id=artifact["review_artifact_id"],
                candidate_id="transition_denial:other",
                source_report_sha256=artifact["source_report_sha256"],
                decision_record_id="sord_conflict_candidate",
                decision_state="accepted_for_proposal",
            )
        ],
    )

    with pytest.raises(ValueError, match="candidate_id"):
        _build_candidate(tmp_path, artifact_path)


def test_creates_deterministic_json_and_markdown_output(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)

    first = _build_candidate(tmp_path, artifact_path)
    second = _build_candidate(tmp_path, artifact_path)

    assert first == second
    assert render_intake_candidate_markdown(first) == render_intake_candidate_markdown(second)

    result = _create_intake_output(tmp_path, artifact_path)
    json_path = Path(result["intake_candidate_json_path"])
    markdown_path = Path(result["intake_candidate_markdown_path"])

    assert json.loads(json_path.read_text(encoding="utf-8")) == first
    assert markdown_path.read_text(encoding="utf-8") == render_intake_candidate_markdown(first)


def test_preserves_full_provenance_fields_exactly(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)
    artifact = _read_json(artifact_path)
    resolution = resolve_review_state(repo_root=tmp_path, artifact_path=artifact_path)
    source_resolution_sha256 = hashlib.sha256(
        render_review_resolution_json(resolution).encode("utf-8")
    ).hexdigest()
    latest_event = _latest_decision(tmp_path)

    candidate = _build_candidate(tmp_path, artifact_path)

    assert candidate["schema_version"] == "self_observation_proposal_intake_candidate.v1"
    assert candidate["source_review_artifact_id"] == artifact["review_artifact_id"]
    assert candidate["source_decision_record_id"] == latest_event["decision_record_id"]
    assert candidate["source_resolution_sha256"] == source_resolution_sha256
    assert candidate["source_report_sha256"] == artifact["source_report_sha256"]
    assert candidate["source_report_schema_version"] == artifact["source_report_schema_version"]
    assert candidate["candidate_id"] == artifact["candidate_id"]
    assert candidate["proposal_type"] == artifact["proposal_type"]
    assert candidate["finding_type"] == artifact["finding_type"]
    assert candidate["evidence_references"] == artifact["evidence_references"]
    assert candidate["evidence_quality"] == artifact["evidence_quality"]
    assert candidate["resolved_review_state"] == "accepted_for_proposal"
    assert candidate["human_intake_authorization"] == {
        "authorized_by": "operator-c",
        "authorized_at": "2026-01-01T02:00:00Z",
        "authorization_rationale": "Create intake candidate only; no implementation authority.",
        "authorization_scope": "intake_candidate_only",
    }
    assert candidate["created_by"] == "operator-c"
    assert candidate["created_at"] == "2026-01-01T02:00:00Z"
    assert candidate["non_authority_to_authority_transition_rationale"] == (
        "Create intake candidate only; no implementation authority."
    )
    assert "does not create a governed proposal" in candidate["non_authority_disclaimer"]


def test_requires_explicit_intake_authorization_fields(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)

    with pytest.raises(ValueError, match="authorized_by"):
        _build_candidate(tmp_path, artifact_path, authorized_by="")
    with pytest.raises(ValueError, match="authorized_at"):
        _build_candidate(tmp_path, artifact_path, authorized_at="")
    with pytest.raises(ValueError, match="authorization_rationale"):
        _build_candidate(tmp_path, artifact_path, authorization_rationale="")


def test_rejects_external_or_canonical_output_paths(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)
    forbidden_outputs = [
        tmp_path.parent / "external-intake",
        tmp_path / "data" / "state",
        tmp_path / "config",
        tmp_path / "governance",
        tmp_path / "constraints",
        tmp_path / "formal_governance",
        tmp_path / "signal_agent",
        tmp_path / "app",
    ]

    for output_dir in forbidden_outputs:
        with pytest.raises(ValueError):
            create_intake_candidate(
                repo_root=tmp_path,
                artifact_path=artifact_path,
                output_dir=output_dir,
                authorized_by="operator-c",
                authorized_at="2026-01-01T02:00:00Z",
                authorization_rationale="Create intake candidate only; no implementation authority.",
            )


def test_rejects_duplicate_intake_candidate_id_without_overwriting(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)
    result = _create_intake_output(tmp_path, artifact_path)
    json_path = Path(result["intake_candidate_json_path"])
    markdown_path = Path(result["intake_candidate_markdown_path"])
    json_before = json_path.read_bytes()
    markdown_before = markdown_path.read_bytes()

    with pytest.raises(ValueError, match="already exists"):
        _create_intake_output(tmp_path, artifact_path)

    assert json_path.read_bytes() == json_before
    assert markdown_path.read_bytes() == markdown_before


def test_creates_only_intake_candidate_artifacts_and_no_governed_proposal(tmp_path: Path) -> None:
    artifact_path = _accepted_artifact(tmp_path)
    decision_log = tmp_path / "data" / "analytics" / "review" / "decisions.jsonl"
    artifact_before = artifact_path.read_bytes()
    decisions_before = decision_log.read_bytes()
    before = _file_set(tmp_path)

    result = _create_intake_output(tmp_path, artifact_path)

    after = _file_set(tmp_path)
    added = after - before
    assert added == {
        str(Path(result["intake_candidate_json_path"]).relative_to(tmp_path)),
        str(Path(result["intake_candidate_markdown_path"]).relative_to(tmp_path)),
    }
    assert artifact_path.read_bytes() == artifact_before
    assert decision_log.read_bytes() == decisions_before
    assert not (tmp_path / "data" / "analytics" / "review" / "proposals").exists()
    assert not (tmp_path / "data" / "state").exists()


def test_cli_create_writes_candidate_paths(tmp_path: Path, capsys) -> None:
    artifact_path = _accepted_artifact(tmp_path)

    exit_code = main(
        [
            "create",
            "--repo-root",
            str(tmp_path),
            "--artifact",
            str(artifact_path),
            "--output-dir",
            "data/analytics/review/intake_candidates",
            "--authorized-by",
            "operator-c",
            "--authorized-at",
            "2026-01-01T02:00:00Z",
            "--authorization-rationale",
            "Create intake candidate only; no implementation authority.",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["intake_candidate_json_path"]).exists()
    assert Path(payload["intake_candidate_markdown_path"]).exists()


def test_static_forbidden_imports_are_absent() -> None:
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
        "subprocess",
    }
    tree = ast.parse(PROPOSAL_INTAKE_MODULE.read_text(encoding="utf-8"))
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


def _build_candidate(root: Path, artifact_path: Path, **overrides) -> dict:
    kwargs = {
        "repo_root": root,
        "artifact_path": artifact_path,
        "authorized_by": "operator-c",
        "authorized_at": "2026-01-01T02:00:00Z",
        "authorization_rationale": "Create intake candidate only; no implementation authority.",
    }
    kwargs.update(overrides)
    return build_intake_candidate(**kwargs)


def _create_intake_output(root: Path, artifact_path: Path) -> dict[str, str]:
    return create_intake_candidate(
        repo_root=root,
        artifact_path=artifact_path,
        output_dir="data/analytics/review/intake_candidates",
        authorized_by="operator-c",
        authorized_at="2026-01-01T02:00:00Z",
        authorization_rationale="Create intake candidate only; no implementation authority.",
    )


def _accepted_artifact(root: Path) -> Path:
    artifact_path = _create_artifact(root)
    record_review_decision(
        repo_root=root,
        artifact_path=artifact_path,
        output_dir="data/analytics/review",
        decision_state="accepted_for_proposal",
        decided_by="operator-b",
        decision_reason="Ready for governed proposal intake only.",
        decided_at="2026-01-01T01:00:00Z",
    )
    return artifact_path


def _create_artifact(root: Path) -> Path:
    report_path = _write_report(root)
    result = create_review_artifact(
        repo_root=root,
        report_path=report_path,
        output_dir="data/analytics/review",
        candidate_id="transition_denial:abc123",
        proposal_type="instrumentation_proposal",
        initial_review_state="queued_for_review",
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
        "decision_reason": "Review decision for intake test.",
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


def _latest_decision(root: Path) -> dict:
    decision_log = root / "data" / "analytics" / "review" / "decisions.jsonl"
    rows = [
        json.loads(line)
        for line in decision_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows[-1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_set(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    }
