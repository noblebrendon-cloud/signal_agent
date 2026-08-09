from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from signal_agent.operational_ingestion import (
    CheckpointConflictError,
    CompletedManifestError,
    CompletedRunReference,
    InjectedOperationalFailure,
    OperationalArtifactError,
    OperationalIngestionKernel,
    PersistedArtifact,
    canonical_json_bytes,
    capture_set_hash,
    commit_checkpoint,
    create_checkpoint_candidate,
    resolve_current_checkpoint,
    sha256_bytes,
)
from signal_agent.operational_ingestion.artifacts import (
    BOUNDARY_SCHEMA,
    CAPTURE_SCHEMA,
    write_immutable_json,
)
from signal_agent.operational_ingestion.canonical import derive_id, seal
from signal_agent.operational_ingestion.checkpoints import COMPLETION_AUTHORITY_SCHEMA

from .conftest import (
    FIXED_TIME,
    SECOND_TIME,
    FakeGovernedProcessor,
    fixed_clock,
    make_intent,
    single_page_history,
    standard_history,
    tree,
)


THIRD_TIME = "2026-08-09T12:02:00Z"


def run_success(
    store: Path,
    governed: Path,
    *,
    prior=None,
    started_at: str = FIXED_TIME,
    history=None,
):
    attempts, pages = history or standard_history()
    return OperationalIngestionKernel(store, clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(prior=prior),
        session_started_at=started_at,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=governed,
    )


def candidate_replay(result, *, boundary=None, bounded_material=None, completed=None):
    return create_checkpoint_candidate(
        result.source_root,
        intent=result.intent,
        boundary=boundary or result.boundary,
        bounded_material=bounded_material or result.bounded_material,
        observation_index=result.observation_index,
        completed=completed or result.completed_run,
    )


def boundary_variant(result, label: str, mutate: Callable[[dict], None]) -> PersistedArtifact:
    payload = json.loads(result.boundary.path.read_text(encoding="utf-8"))
    mutate(payload)
    payload = seal(payload)
    return write_immutable_json(
        result.source_root / f"audit-variants/{label}.boundary.json", payload
    )


def authority_variant(result, label: str, mutate: Callable[[dict], None]) -> PersistedArtifact:
    current = json.loads(result.completion_authority.path.read_text(encoding="utf-8"))
    material = {
        key: value
        for key, value in current.items()
        if key not in {"artifact_hash", "artifact_id", "authority_id"}
    }
    mutate(material)
    authority_id = derive_id("ocma", COMPLETION_AUTHORITY_SCHEMA, material)
    payload = seal(
        {
            **material,
            "authority_id": authority_id,
            "artifact_id": authority_id,
        }
    )
    return write_immutable_json(
        result.source_root / f"completion_authorities/audit-{label}-{authority_id}.json",
        payload,
    )


def rewrite_sealed(path: Path, payload: dict, hash_field: str = "artifact_hash") -> dict:
    rewritten = seal(payload, hash_field)
    path.write_bytes(canonical_json_bytes(rewritten))
    return rewritten


def rederive_artifact(
    payload: dict, *, schema: str, id_field: str, prefix: str
) -> dict:
    material = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_hash", "artifact_id", id_field}
    }
    artifact_id = derive_id(prefix, schema, material)
    return seal({**material, id_field: artifact_id, "artifact_id": artifact_id})


def rebound_single_capture_variant(
    result, label: str, mutate: Callable[[dict], None]
) -> tuple[PersistedArtifact, PersistedArtifact]:
    capture_ref = result.boundary.payload["captures"][0]
    capture_path = result.source_root / capture_ref["path"]
    capture_payload = json.loads(capture_path.read_text(encoding="utf-8"))
    mutate(capture_payload)
    capture_payload = rederive_artifact(
        capture_payload,
        schema=CAPTURE_SCHEMA,
        id_field="capture_id",
        prefix="opc",
    )
    capture_path.write_bytes(canonical_json_bytes(capture_payload))
    capture = PersistedArtifact(capture_path, capture_payload, True)

    boundary_payload = json.loads(result.boundary.path.read_text(encoding="utf-8"))
    boundary_payload["captures"] = [
        {
            "capture_id": capture_payload["capture_id"],
            "capture_hash": capture_payload["artifact_hash"],
            "path": str(capture_ref["path"]),
            "page_ordinal": capture_payload["page_ordinal"],
        }
    ]
    for references in boundary_payload["observation_capture_provenance"].values():
        for reference in references:
            reference["capture_id"] = capture_payload["capture_id"]
    boundary_payload["capture_set_hash"] = capture_set_hash((capture,))
    boundary_payload["terminal_evidence"].update(
        {
            "capture_id": capture_payload["capture_id"],
            "capture_hash": capture_payload["artifact_hash"],
            "page_ordinal": capture_payload["page_ordinal"],
        }
    )
    boundary_payload = rederive_artifact(
        boundary_payload,
        schema=BOUNDARY_SCHEMA,
        id_field="boundary_id",
        prefix="oab",
    )
    boundary = write_immutable_json(
        result.source_root / f"audit-variants/{label}.rebound-boundary.json",
        boundary_payload,
    )
    return capture, boundary


def prepare_uncommitted_successor(
    store: Path,
    governed: Path,
    *,
    prior,
    started_at: str,
) -> tuple[Path, PersistedArtifact, PersistedArtifact, CompletedRunReference]:
    source_root = prior.source_root
    before_candidates = set(source_root.glob("checkpoint_candidates/*.json"))
    before_authorities = set(source_root.glob("completion_authorities/*.json"))

    def stop_before_commit(stage: str) -> None:
        if stage == "before_checkpoint_commit":
            raise InjectedOperationalFailure(stage)

    attempts, pages = standard_history()
    with pytest.raises(InjectedOperationalFailure, match="before_checkpoint_commit"):
        OperationalIngestionKernel(
            store, clock=fixed_clock, failure_injector=stop_before_commit
        ).run_from_captured_pages(
            intent=make_intent(prior=prior.checkpoint_commit),
            session_started_at=started_at,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(),
            governed_run_root=governed,
        )
    candidate_path = (set(source_root.glob("checkpoint_candidates/*.json")) - before_candidates).pop()
    authority_path = (set(source_root.glob("completion_authorities/*.json")) - before_authorities).pop()
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    authority_payload = json.loads(authority_path.read_text(encoding="utf-8"))
    manifest = json.loads((governed / "manifest/completed_manifest.json").read_text(encoding="utf-8"))
    return (
        source_root,
        PersistedArtifact(candidate_path, candidate_payload, True),
        PersistedArtifact(authority_path, authority_payload, True),
        CompletedRunReference(
            run_id=manifest["run_id"],
            run_root=governed,
            run_root_ref="fake-governed-run",
            manifest_relative_path="manifest/completed_manifest.json",
            preservation_receipt_relative_path="source/preservation_receipt.json",
        ),
    )


def test_boundary_and_bounded_material_jointly_seal_complete_assembly_contract(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    boundary = result.boundary.payload
    bounded = result.bounded_material.payload
    assert boundary["source"] == bounded["source"]
    assert boundary["adapter"] == bounded["adapter"]
    assert boundary["assembly_policy"] == bounded["assembly_policy"]
    assert boundary["observation_boundary"] == bounded["observation_boundary"]
    assert boundary["coverage"] == {
        "kind": bounded["observation_boundary"]["kind"],
        "lower_observation_boundary": bounded["observation_boundary"]["lower"],
        "upper_observation_boundary": bounded["observation_boundary"]["upper"],
    }
    assert boundary["terminal"] is True
    assert boundary["terminal_evidence"]["terminal"] is True
    assert boundary["counts"]["captured_record_count"] == 3
    assert boundary["counts"]["canonical_observation_count"] == 2
    assert boundary["counts"]["duplicate_observation_count"] == 1
    assert boundary["bounded_material"]["file_sha256"] == sha256_bytes(
        result.bounded_material.path.read_bytes()
    )
    assert set(boundary["observation_capture_provenance"]) == {
        item["observation_id"] for item in bounded["observations"]
    }


@pytest.mark.parametrize(
    "field",
    [
        "observation_boundary",
        "coverage",
        "assembly_policy",
        "capture_set_hash",
        "observation_set_hash",
        "counts",
        "terminal_evidence",
    ],
)
def test_missing_required_assembly_fact_blocks_candidate(
    tmp_path: Path, field: str
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    variant = boundary_variant(result, f"missing-{field}", lambda payload: payload.pop(field))
    with pytest.raises(OperationalArtifactError, match="required_field_missing"):
        candidate_replay(result, boundary=variant)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("coverage", lambda value: value["coverage"].update({"upper_observation_boundary": "wrong"})),
        ("policy", lambda value: value["assembly_policy"].update({"version": "9.9.9"})),
        ("capture-set", lambda value: value.update({"capture_set_hash": "sha256:" + "0" * 64})),
        ("observation-set", lambda value: value.update({"observation_set_hash": "sha256:" + "0" * 64})),
        ("counts", lambda value: value["counts"].update({"canonical_observation_count": 999})),
        ("terminal", lambda value: value.update({"terminal": False})),
        ("terminal-evidence", lambda value: value["terminal_evidence"].update({"page_ordinal": 999})),
    ],
)
def test_inconsistent_assembly_fact_blocks_candidate(
    tmp_path: Path, label: str, mutate: Callable[[dict], None]
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    variant = boundary_variant(result, f"inconsistent-{label}", mutate)
    with pytest.raises(OperationalArtifactError):
        candidate_replay(result, boundary=variant)


def test_missing_or_altered_bounded_assembly_facts_block_candidate(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    payload = json.loads(result.bounded_material.path.read_text(encoding="utf-8"))
    payload.pop("observation_boundary")
    payload = seal(payload)
    result.bounded_material.path.write_bytes(canonical_json_bytes(payload))
    altered = PersistedArtifact(result.bounded_material.path, payload, True)
    with pytest.raises(OperationalArtifactError, match="required_field_missing"):
        candidate_replay(result, bounded_material=altered)


def test_capture_body_mutation_with_untouched_boundary_blocks_candidate(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    capture_ref = result.boundary.payload["captures"][0]
    capture = json.loads((result.source_root / capture_ref["path"]).read_text(encoding="utf-8"))
    session_root = (result.source_root / capture_ref["path"]).parent.parent
    body_path = session_root / capture["response_body"]["path"]
    original = body_path.read_bytes()
    body_path.write_bytes(b"X" + original[1:])
    with pytest.raises(OperationalArtifactError, match="capture_body_hash_mismatch"):
        candidate_replay(result)


def test_missing_referenced_capture_blocks_candidate(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    capture_path = result.source_root / result.boundary.payload["captures"][0]["path"]
    capture_path.unlink()
    with pytest.raises((OperationalArtifactError, FileNotFoundError)):
        candidate_replay(result)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("wrong-size", lambda value: value["response_body"].update({"byte_size": 999})),
        ("wrong-body-hash", lambda value: value["response_body"].update({"body_sha256": "sha256:" + "0" * 64})),
        ("altered-chain", lambda value: value.update({"previous_capture": None})),
        ("wrong-request", lambda value: value.update({"request_fingerprint": "sha256:" + "0" * 64})),
        ("wrong-continuation", lambda value: value.update({"continuation_hash": "sha256:" + "0" * 64})),
        ("not-member", lambda value: value.update({"observations": []})),
    ],
)
def test_altered_capture_receipt_with_untouched_boundary_blocks_candidate(
    tmp_path: Path, label: str, mutate: Callable[[dict], None]
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    capture_ref = result.boundary.payload["captures"][1]
    capture_path = result.source_root / capture_ref["path"]
    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    mutate(payload)
    capture_path.write_bytes(canonical_json_bytes(seal(payload)))
    with pytest.raises(OperationalArtifactError):
        candidate_replay(result)


def test_invalid_capture_receipt_hash_with_untouched_boundary_blocks_candidate(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    capture_path = result.source_root / result.boundary.payload["captures"][0]["path"]
    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    payload["artifact_hash"] = "sha256:" + "0" * 64
    capture_path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(OperationalArtifactError, match="hash_invalid"):
        candidate_replay(result)


@pytest.mark.parametrize(
    ("label", "mutate", "match"),
    [
        ("body-size", lambda value: value["response_body"].update({"byte_size": 999}), "capture_body_size_mismatch"),
        ("body-hash", lambda value: value["response_body"].update({"body_sha256": "sha256:" + "0" * 64}), "capture_body_hash_mismatch"),
        ("chain", lambda value: value.update({"previous_capture": {"capture_id": "opc_" + "0" * 20, "capture_hash": "sha256:" + "0" * 64, "page_ordinal": 0}}), "capture_chain_link_mismatch"),
        ("session", lambda value: value.update({"session_id": "oas_" + "0" * 20}), "capture_session_mismatch"),
        ("request", lambda value: value.update({"request_fingerprint": "sha256:" + "0" * 64}), "capture_attempt_request_mismatch"),
        ("continuation", lambda value: value.update({"continuation_hash": "sha256:" + "0" * 64}), "capture_attempt_continuation_mismatch"),
        ("membership", lambda value: value.update({"observations": []}), "capture_observation_membership_mismatch"),
    ],
)
def test_rebound_boundary_still_rejects_invalid_transitive_capture_fact(
    tmp_path: Path,
    label: str,
    mutate: Callable[[dict], None],
    match: str,
) -> None:
    result = run_success(
        tmp_path / "store",
        tmp_path / "governed",
        history=single_page_history(),
    )
    _capture, boundary = rebound_single_capture_variant(result, label, mutate)
    with pytest.raises(OperationalArtifactError, match=match):
        candidate_replay(result, boundary=boundary)


def test_preservation_receipt_is_bound_to_exact_bounded_and_preserved_bytes(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    source_sha256 = sha256_bytes(result.bounded_material.path.read_bytes())
    assert result.boundary.payload["bounded_material"]["file_sha256"] == source_sha256
    assert result.checkpoint_candidate.payload["preservation_receipt"]["source_sha256"] == source_sha256
    assert candidate_replay(result).idempotent_replay is True


def test_bounded_material_altered_after_boundary_blocks_candidate(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    payload = json.loads(result.bounded_material.path.read_text(encoding="utf-8"))
    payload["observation_count"] += 1
    result.bounded_material.path.write_bytes(canonical_json_bytes(seal(payload)))
    with pytest.raises(OperationalArtifactError):
        candidate_replay(result)


def test_wrong_receipt_source_sha_with_correct_input_reference_blocks_candidate(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    receipt_path = result.completed_run.run_root / "source/preservation_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source_sha256"] = "sha256:" + "0" * 64
    receipt = rewrite_sealed(receipt_path, receipt, "receipt_hash")
    manifest_path = result.completed_run.run_root / "manifest/completed_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["preservation_receipt"].update(
        {
            "receipt_hash": receipt["receipt_hash"],
            "file_sha256": sha256_bytes(receipt_path.read_bytes()),
        }
    )
    rewrite_sealed(manifest_path, manifest, "manifest_hash")
    with pytest.raises(CompletedManifestError, match="source_sha256_mismatch"):
        candidate_replay(result)


def test_correct_source_sha_but_wrong_bounded_descriptor_blocks_candidate(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    variant = boundary_variant(
        result,
        "wrong-bounded-file-sha",
        lambda value: value["bounded_material"].update({"file_sha256": "sha256:" + "0" * 64}),
    )
    with pytest.raises(OperationalArtifactError, match="bounded_material_descriptor_mismatch"):
        candidate_replay(result, boundary=variant)


def test_preserved_source_bytes_different_from_declared_hashes_block_candidate(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    preserved_path = result.completed_run.run_root / "source/bounded_source_material.json"
    preserved_path.write_bytes(b"different-preserved-source\n")
    with pytest.raises(CompletedManifestError, match="preserved_source_bytes_mismatch"):
        candidate_replay(result)


def test_valid_root_successor_and_exact_replay_use_candidate_bound_authority(
    tmp_path: Path,
) -> None:
    root = run_success(tmp_path / "store", tmp_path / "governed-root")
    successor = run_success(
        tmp_path / "store",
        tmp_path / "governed-successor",
        prior=root.checkpoint_commit,
        started_at=SECOND_TIME,
    )
    assert successor.checkpoint_commit.payload["prior_checkpoint_id"] == root.checkpoint_commit.payload["checkpoint_id"]
    assert successor.completion_authority.payload["candidate"] == {
        "candidate_id": successor.checkpoint_candidate.payload["candidate_id"],
        "candidate_hash": successor.checkpoint_candidate.payload["artifact_hash"],
    }
    replay = commit_checkpoint(
        successor.source_root,
        candidate=successor.checkpoint_candidate,
        authority=successor.completion_authority,
        completed=successor.completed_run,
        committed_at=THIRD_TIME,
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == successor.checkpoint_commit.path.read_bytes()


@pytest.mark.parametrize(
    ("label", "mutate", "match"),
    [
        ("type", lambda value: value.update({"authority_type": "human_attestation"}), "type_unsupported"),
        ("version", lambda value: value.update({"verifier_version": "2.0.0"}), "version_unsupported"),
        ("candidate", lambda value: value["candidate"].update({"candidate_hash": "sha256:" + "0" * 64}), "candidate_binding"),
        ("policy", lambda value: value["completion_policy"].update({"version": "2.0.0"}), "policy_mismatch"),
        ("assertion", lambda value: value["assertions"].update({"capture_bodies_verified": False}), "assertions_invalid"),
        ("external", lambda value: value.update({"upstream_write_authorized": True}), "forbidden"),
    ],
)
def test_invalid_verifier_authority_blocks_commit(
    tmp_path: Path,
    label: str,
    mutate: Callable[[dict], None],
    match: str,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    authority = authority_variant(result, label, mutate)
    before = result.checkpoint_commit.path.read_bytes()
    with pytest.raises(CheckpointConflictError, match=match):
        commit_checkpoint(
            result.source_root,
            candidate=result.checkpoint_candidate,
            authority=authority,
            completed=result.completed_run,
            committed_at=SECOND_TIME,
        )
    assert result.checkpoint_commit.path.read_bytes() == before


def test_missing_verifier_authority_blocks_commit(tmp_path: Path) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
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


@pytest.mark.parametrize(
    ("label", "mutate", "match"),
    [
        ("schema", lambda value: value.update({"schema_version": "unsupported.candidate.v9"}), "schema_invalid"),
        ("status", lambda value: value.update({"status": "committed"}), "status_invalid"),
        ("identity", lambda value: value.update({"artifact_id": "ockc_" + "0" * 20}), "identity_mismatch"),
    ],
)
def test_invalid_candidate_contract_blocks_commit_before_transition(
    tmp_path: Path,
    label: str,
    mutate: Callable[[dict], None],
    match: str,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    payload = json.loads(result.checkpoint_candidate.path.read_text(encoding="utf-8"))
    mutate(payload)
    payload = seal(payload)
    candidate = write_immutable_json(
        result.source_root / f"checkpoint_candidates/audit-{label}.json", payload
    )
    with pytest.raises(CheckpointConflictError, match=match):
        commit_checkpoint(
            result.source_root,
            candidate=candidate,
            authority=result.completion_authority,
            completed=result.completed_run,
            committed_at=SECOND_TIME,
        )


def test_candidate_with_noncurrent_predecessor_and_empty_slot_is_rejected(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path / "store", tmp_path / "governed")
    fake_prior = {
        "checkpoint_id": "ock_" + "0" * 20,
        "checkpoint_hash": "sha256:" + "0" * 64,
    }
    boundary_payload = json.loads(result.boundary.path.read_text(encoding="utf-8"))
    boundary_payload["prior_checkpoint"] = fake_prior
    boundary_payload = rederive_artifact(
        boundary_payload,
        schema=BOUNDARY_SCHEMA,
        id_field="boundary_id",
        prefix="oab",
    )
    boundary = write_immutable_json(
        result.source_root / "audit-variants/noncurrent-predecessor.boundary.json",
        boundary_payload,
    )

    candidate_payload = json.loads(
        result.checkpoint_candidate.path.read_text(encoding="utf-8")
    )
    candidate_payload["prior_checkpoint"] = fake_prior
    candidate_payload["acquisition_boundary"] = {
        "boundary_id": boundary_payload["boundary_id"],
        "boundary_hash": boundary_payload["artifact_hash"],
        "path": boundary.path.relative_to(result.source_root).as_posix(),
    }
    candidate_material = {
        key: value
        for key, value in candidate_payload.items()
        if key not in {"artifact_hash", "artifact_id", "candidate_id"}
    }
    identity_material = {
        key: value
        for key, value in candidate_material.items()
        if key not in {"created_at", "status"}
    }
    candidate_id = derive_id(
        "ockc", "signal_agent.operational_checkpoint_candidate.v1", identity_material
    )
    candidate_payload = seal(
        {
            **candidate_material,
            "candidate_id": candidate_id,
            "artifact_id": candidate_id,
        }
    )
    candidate = write_immutable_json(
        result.source_root / f"checkpoint_candidates/{candidate_id}.audit-stale.json",
        candidate_payload,
    )

    authority_payload = json.loads(
        result.completion_authority.path.read_text(encoding="utf-8")
    )
    authority_material = {
        key: value
        for key, value in authority_payload.items()
        if key not in {"artifact_hash", "artifact_id", "authority_id"}
    }
    authority_material["candidate"] = {
        "candidate_id": candidate_id,
        "candidate_hash": candidate_payload["artifact_hash"],
    }
    authority_material["completed_run"]["acquisition_boundary"] = candidate_payload[
        "acquisition_boundary"
    ]
    authority_id = derive_id("ocma", COMPLETION_AUTHORITY_SCHEMA, authority_material)
    authority_payload = seal(
        {
            **authority_material,
            "authority_id": authority_id,
            "artifact_id": authority_id,
        }
    )
    authority = write_immutable_json(
        result.source_root / f"completion_authorities/{authority_id}.audit-stale.json",
        authority_payload,
    )
    before = tree(result.source_root / "checkpoints")
    with pytest.raises(CheckpointConflictError, match="predecessor_not_current"):
        commit_checkpoint(
            result.source_root,
            candidate=candidate,
            authority=authority,
            completed=result.completed_run,
            committed_at=SECOND_TIME,
        )
    assert tree(result.source_root / "checkpoints") == before


def test_stale_candidate_and_divergent_successor_leave_history_unchanged(tmp_path: Path) -> None:
    seed = run_success(tmp_path / "store", tmp_path / "governed-seed")
    source_root, first_candidate, first_authority, first_completed = prepare_uncommitted_successor(
        tmp_path / "store",
        tmp_path / "governed-first",
        prior=seed,
        started_at=SECOND_TIME,
    )
    _, stale_candidate, stale_authority, stale_completed = prepare_uncommitted_successor(
        tmp_path / "store",
        tmp_path / "governed-stale",
        prior=seed,
        started_at=THIRD_TIME,
    )
    winner = commit_checkpoint(
        source_root,
        candidate=first_candidate,
        authority=first_authority,
        completed=first_completed,
        committed_at=SECOND_TIME,
    )
    committed_before = tree(source_root / "checkpoints")
    with pytest.raises(CheckpointConflictError, match="divergent_checkpoint_successor"):
        commit_checkpoint(
            source_root,
            candidate=stale_candidate,
            authority=stale_authority,
            completed=stale_completed,
            committed_at=THIRD_TIME,
        )
    assert tree(source_root / "checkpoints") == committed_before
    assert resolve_current_checkpoint(source_root).payload["checkpoint_id"] == winner.payload["checkpoint_id"]


def test_divergent_bootstrap_candidate_is_rejected_after_root_commit(tmp_path: Path) -> None:
    committed = run_success(tmp_path / "store-a", tmp_path / "governed-a")
    other = run_success(tmp_path / "store-b", tmp_path / "governed-b", started_at=SECOND_TIME)
    before = tree(committed.source_root / "checkpoints")
    with pytest.raises(CheckpointConflictError, match="divergent_checkpoint_successor"):
        commit_checkpoint(
            committed.source_root,
            candidate=other.checkpoint_candidate,
            authority=other.completion_authority,
            completed=other.completed_run,
            committed_at=THIRD_TIME,
        )
    assert tree(committed.source_root / "checkpoints") == before
