from __future__ import annotations

import json

import pytest

from signal_agent.operational_ingestion import (
    CompletedManifestError,
    OperationalArtifactError,
    PersistedArtifact,
    commit_checkpoint,
    create_checkpoint_candidate,
)
from signal_agent.operational_ingestion.canonical import canonical_json_bytes
from signal_agent.operational_ingestion.errors import AcquisitionStateError

from .gmail_test_support import SECOND_TIME, projection_path, run_case


def _seed(case_root):
    governed = case_root / "governed"
    result = run_case(
        case_root,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    return result.result.execution, governed


def _candidate_replay(result):
    return create_checkpoint_candidate(
        result.source_root,
        intent=result.intent,
        boundary=result.boundary,
        bounded_material=result.bounded_material,
        observation_index=result.observation_index,
        completed=result.completed_run,
    )


def _capture_payloads(result):
    for reference in result.boundary.payload["captures"]:
        path = result.source_root / str(reference["path"])
        yield path, json.loads(path.read_text(encoding="utf-8"))


def test_exact_checkpoint_commit_replay_returns_existing_immutable_bytes(tmp_path):
    result, _governed = _seed(tmp_path)
    before = result.checkpoint_commit.path.read_bytes()
    replay = commit_checkpoint(
        result.source_root,
        candidate=result.checkpoint_candidate,
        authority=result.completion_authority,
        completed=result.completed_run,
        committed_at="2026-08-10T16:00:00Z",
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == before


def test_capture_body_corruption_blocks_candidate_verification(tmp_path):
    result, _governed = _seed(tmp_path)
    capture_path, capture = next(_capture_payloads(result))
    body_path = capture_path.parents[1] / str(capture["response_body"]["path"])
    raw = body_path.read_bytes()
    body_path.write_bytes(b"X" + raw[1:])
    with pytest.raises(OperationalArtifactError, match="capture_body_hash_mismatch"):
        _candidate_replay(result)


def test_metadata_capture_body_corruption_blocks_candidate_verification(tmp_path):
    result, _governed = _seed(tmp_path)
    selected = next(
        (path, payload)
        for path, payload in _capture_payloads(result)
        if payload["response_schema"]
        == "gmail.users.messages.get.metadata.response.v1"
    )
    capture_path, capture = selected
    body_path = capture_path.parents[1] / str(capture["response_body"]["path"])
    body_path.write_bytes(body_path.read_bytes() + b"corrupt")
    with pytest.raises(OperationalArtifactError, match="capture_body_hash_mismatch"):
        _candidate_replay(result)


def test_capture_receipt_corruption_blocks_candidate_verification(tmp_path):
    result, _governed = _seed(tmp_path)
    capture_path, capture = next(_capture_payloads(result))
    capture["artifact_hash"] = "sha256:" + "0" * 64
    capture_path.write_bytes(canonical_json_bytes(capture))
    with pytest.raises(OperationalArtifactError, match="hash_invalid"):
        _candidate_replay(result)


def test_bounded_material_corruption_blocks_candidate_verification(tmp_path):
    result, _governed = _seed(tmp_path)
    payload = json.loads(result.bounded_material.path.read_text(encoding="utf-8"))
    payload["observation_count"] += 1
    result.bounded_material.path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(OperationalArtifactError):
        _candidate_replay(result)


def test_preserved_source_corruption_blocks_completed_manifest_verification(tmp_path):
    result, governed = _seed(tmp_path)
    preserved = governed / "00_original/gmail_history_bounded_source.json"
    preserved.write_bytes(preserved.read_bytes() + b"corrupt")
    with pytest.raises(CompletedManifestError, match="preserved_source_bytes_mismatch"):
        _candidate_replay(result)


def test_missing_verifier_authority_cannot_commit(tmp_path):
    result, _governed = _seed(tmp_path)
    missing = PersistedArtifact(
        path=result.source_root / "completion_authorities/missing.json",
        payload=result.completion_authority.payload,
        idempotent_replay=True,
    )
    with pytest.raises(OperationalArtifactError, match="regular_file_required"):
        commit_checkpoint(
            result.source_root,
            candidate=result.checkpoint_candidate,
            authority=missing,
            completed=result.completed_run,
            committed_at=SECOND_TIME,
        )


def test_stale_predecessor_is_rejected_without_new_checkpoint(tmp_path):
    bootstrap, bootstrap_governed = _seed(tmp_path)
    first = run_case(
        tmp_path,
        script_name="gmail_incremental_partition_a.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=tmp_path / "incremental-a",
    )
    with pytest.raises(AcquisitionStateError, match="prior_checkpoint_not_current"):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_b.json",
            start="2026-08-10T14:00:00Z",
            session_started_at="2026-08-10T14:00:00Z",
            prior_checkpoint=bootstrap.checkpoint_commit,
            prior_projection_path=projection_path(bootstrap_governed),
            governed_run_root=tmp_path / "incremental-stale",
        )
    current = first.result.execution.checkpoint_commit
    assert current.path.is_file()
