from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_agent.operational_ingestion import (
    OperationalIngestionKernel,
    resolve_ingestion_state,
)

from .conftest import (
    FIXED_TIME,
    FakeGovernedProcessor,
    fixed_clock,
    make_intent,
    single_page_history,
    standard_history,
    tree,
)


SCHEMAS = {
    "signal_agent.operational_acquisition_intent.v1": "acquisition_intent.v1.schema.json",
    "signal_agent.operational_acquisition_session.v1": "acquisition_session.v1.schema.json",
    "signal_agent.operational_request_attempt_receipt.v1": "request_attempt_receipt.v1.schema.json",
    "signal_agent.operational_page_capture_receipt.v1": "page_capture_receipt.v1.schema.json",
    "signal_agent.operational_acquisition_boundary.v1": "acquisition_boundary.v1.schema.json",
    "signal_agent.operational_bounded_source_material.v1": "bounded_source_material.v1.schema.json",
    "signal_agent.operational_observation_index.v1": "observation_index.v1.schema.json",
    "signal_agent.operational_checkpoint_candidate.v1": "checkpoint_candidate.v1.schema.json",
    "signal_agent.operational_completed_manifest_verifier_authority.v1": "completed_manifest_verifier_authority.v1.schema.json",
    "signal_agent.operational_checkpoint_commit_receipt.v1": "checkpoint_commit_receipt.v1.schema.json",
}


def run_success(store: Path, governed: Path, *, history=standard_history()):
    attempts, pages = history
    return OperationalIngestionKernel(store, clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=governed,
    )


def test_frozen_models_and_nested_mappings_are_immutable() -> None:
    intent = make_intent()
    with pytest.raises(FrozenInstanceError):
        intent.authentication_mode = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        intent.observation_boundary["upper"] = "changed"  # type: ignore[index]


def test_identical_transport_history_is_byte_deterministic(tmp_path: Path) -> None:
    first = run_success(tmp_path / "store-a", tmp_path / "governed-a")
    second = run_success(tmp_path / "store-b", tmp_path / "governed-b")
    assert tree(first.source_root) == tree(second.source_root)
    assert tree(first.completed_run.run_root) == tree(second.completed_run.run_root)
    assert first.boundary.payload["capture_set_hash"] == second.boundary.payload["capture_set_hash"]
    assert first.boundary.payload["observation_set_hash"] == second.boundary.payload["observation_set_hash"]


def test_semantic_evidence_is_stable_across_retry_and_page_history(tmp_path: Path) -> None:
    multi = run_success(tmp_path / "store-multi", tmp_path / "governed-multi")
    single = run_success(
        tmp_path / "store-single",
        tmp_path / "governed-single",
        history=single_page_history(),
    )
    assert multi.boundary.payload["capture_set_hash"] != single.boundary.payload["capture_set_hash"]
    assert multi.boundary.payload["observation_set_hash"] == single.boundary.payload["observation_set_hash"]
    assert multi.bounded_material.path.read_bytes() == single.bounded_material.path.read_bytes()
    assert tree(multi.completed_run.run_root) == tree(single.completed_run.run_root)
    assert tree(multi.source_root) != tree(single.source_root)


def test_bounded_semantic_identity_excludes_transport_metadata(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    bounded = json.loads(result.bounded_material.path.read_text(encoding="utf-8"))
    serialized = result.bounded_material.path.read_text(encoding="utf-8")
    assert "capture_set_hash" not in bounded
    assert "attempt_id" not in serialized
    assert "page_ordinal" not in serialized
    assert "captured_at" not in serialized
    assert bounded["observation_set_hash"] == result.boundary.payload["observation_set_hash"]
    assert bounded["transport_provenance_external"] is True


def test_checkpoint_uses_bounded_observation_index_reference(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    candidate = result.checkpoint_candidate.payload
    commit = result.checkpoint_commit.payload
    index = result.observation_index.payload
    expected = {
        "observation_index_id": index["observation_index_id"],
        "observation_index_hash": index["artifact_hash"],
        "path": result.observation_index.path.relative_to(result.source_root).as_posix(),
    }
    assert dict(candidate["observation_index"]) == expected
    assert dict(commit["observation_index"]) == expected
    assert "entries" not in candidate["observation_index"]
    assert "entries" not in commit["observation_index"]
    assert index["mutable_current_state"] is False
    assert index["compaction_performed"] is False


def test_all_success_artifacts_validate_against_m4a_schemas(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    schema_root = repository_root / "schemas/operational_ingestion"
    seen: set[str] = set()
    for path in result.source_root.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_version = payload.get("schema_version")
        if schema_version not in SCHEMAS:
            continue
        schema = json.loads((schema_root / SCHEMAS[schema_version]).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        seen.add(schema_version)
    assert seen == set(SCHEMAS)


def test_successful_state_resolves_from_immutable_chain(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    state = resolve_ingestion_state(result.source_root, result.session.payload["session_id"])
    assert state.stage == "checkpoint_committed"
    assert state.current_checkpoint_id == result.checkpoint_commit.payload["checkpoint_id"]
    assert state.current_checkpoint_hash == result.checkpoint_commit.payload["artifact_hash"]
