from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.operational_ingestion import (
    CheckpointConflictError,
    CompletedManifestError,
    ImmutableArtifactConflictError,
    OperationalArtifactError,
    OperationalIngestionKernel,
    commit_checkpoint,
    create_checkpoint_candidate,
    resolve_current_checkpoint,
)
from signal_agent.operational_ingestion.artifacts import write_immutable_json
from signal_agent.operational_ingestion.canonical import seal
from signal_agent.operational_ingestion import canonical_json_bytes
from signal_agent.operational_ingestion.models import thaw_json

from .conftest import (
    FIXED_TIME,
    SECOND_TIME,
    FakeGovernedProcessor,
    attempt,
    fixed_clock,
    make_intent,
    observation,
    page,
    standard_history,
)


def run_success(store: Path, governed: Path, *, changed: bool = False):
    if changed:
        records = (observation("record-1", 2),)
        history = ((attempt(1, 1),), (page(1, records, terminal=True),))
    else:
        history = standard_history()
    return OperationalIngestionKernel(store, clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=history[0],
        pages=history[1],
        processor=FakeGovernedProcessor(),
        governed_run_root=governed,
    )


def test_no_checkpoint_or_candidate_without_completed_manifest(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock)
    with pytest.raises(RuntimeError, match="output_before_manifest"):
        kernel.run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(fail_stage="after_output_before_manifest"),
            governed_run_root=tmp_path / "governed",
        )
    source_roots = list((tmp_path / "store").glob("osi_*"))
    assert len(source_roots) == 1
    source_root = source_roots[0]
    assert resolve_current_checkpoint(source_root) is None
    assert not list((source_root / "checkpoint_candidates").glob("*.json"))
    assert not list((source_root / "checkpoints").rglob("*.json"))
    assert not (tmp_path / "governed/manifest/completed_manifest.json").exists()


def test_invalid_completed_manifest_blocks_candidate_replay(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    manifest_path = result.completed_run.run_root / result.completed_run.manifest_relative_path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["manifest_hash"] = "sha256:" + ("0" * 64)
    manifest_path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(CompletedManifestError, match="hash_invalid"):
        create_checkpoint_candidate(
            result.source_root,
            intent=result.intent,
            boundary=result.boundary,
            bounded_material=result.bounded_material,
            observation_index=result.observation_index,
            completed=result.completed_run,
        )


def test_candidate_exact_replay_loads_verifies_and_returns_existing_bytes(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    before = result.checkpoint_candidate.path.read_bytes()
    replay = create_checkpoint_candidate(
        result.source_root,
        intent=result.intent,
        boundary=result.boundary,
        bounded_material=result.bounded_material,
        observation_index=result.observation_index,
        completed=result.completed_run,
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == before
    assert replay.payload["created_at"] == result.checkpoint_candidate.payload["created_at"]


def test_candidate_replay_rejects_changed_referenced_index_bytes(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    index = json.loads(result.observation_index.path.read_text(encoding="utf-8"))
    index["entry_count"] += 1
    result.observation_index.path.write_bytes(canonical_json_bytes(index))
    with pytest.raises(OperationalArtifactError, match="hash_invalid"):
        create_checkpoint_candidate(
            result.source_root,
            intent=result.intent,
            boundary=result.boundary,
            bounded_material=result.bounded_material,
            observation_index=result.observation_index,
            completed=result.completed_run,
        )


def test_exact_commit_replay_is_idempotent_and_preserves_first_bytes(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    before = result.checkpoint_commit.path.read_bytes()
    replay = commit_checkpoint(
        result.source_root,
        candidate=result.checkpoint_candidate,
        authority=result.completion_authority,
        completed=result.completed_run,
        committed_at=SECOND_TIME,
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == before
    assert replay.payload["committed_at"] == FIXED_TIME


def test_divergent_successor_for_same_predecessor_is_rejected(tmp_path: Path) -> None:
    first = run_success(tmp_path / "store-a", tmp_path / "governed-a")
    divergent = run_success(tmp_path / "store-b", tmp_path / "governed-b", changed=True)
    before = first.checkpoint_commit.path.read_bytes()
    with pytest.raises(CheckpointConflictError, match="divergent"):
        commit_checkpoint(
            first.source_root,
            candidate=divergent.checkpoint_candidate,
            authority=divergent.completion_authority,
            completed=divergent.completed_run,
            committed_at=SECOND_TIME,
        )
    assert first.checkpoint_commit.path.read_bytes() == before
    assert resolve_current_checkpoint(first.source_root).payload["checkpoint_id"] == first.checkpoint_commit.payload["checkpoint_id"]


def test_stable_artifact_id_cannot_name_divergent_immutable_bytes(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    divergent = thaw_json(result.checkpoint_candidate.payload)
    divergent["created_at"] = SECOND_TIME
    divergent = seal(divergent)
    assert divergent["candidate_id"] == result.checkpoint_candidate.payload["candidate_id"]
    with pytest.raises(ImmutableArtifactConflictError, match="immutable_artifact_conflict"):
        write_immutable_json(result.checkpoint_candidate.path, divergent)
    assert result.checkpoint_candidate.path.read_bytes() != (
        json.dumps(divergent, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
