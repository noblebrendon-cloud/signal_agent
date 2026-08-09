from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import (
    BOUNDED_MATERIAL_SCHEMA,
    BOUNDARY_SCHEMA,
    load_artifact,
    safe_artifact_path,
    verify_assembly_evidence,
    write_immutable_json,
)
from .canonical import (
    canonical_json_bytes,
    derive_id,
    seal,
    sha256_bytes,
    sha256_canonical,
    verify_seal,
)
from .errors import (
    CheckpointConflictError,
    CompletedManifestError,
    ImmutableArtifactConflictError,
    OperationalArtifactError,
)
from .models import (
    CompletedManifestVerifierAuthority,
    CompletedRunReference,
    ObservationIndexReference,
    PersistedArtifact,
    PolicyIdentity,
    ResolvedIngestionState,
    thaw_json,
)
from .secrets import assert_secret_free


CHECKPOINT_CANDIDATE_SCHEMA = "signal_agent.operational_checkpoint_candidate.v1"
CHECKPOINT_COMMIT_SCHEMA = "signal_agent.operational_checkpoint_commit_receipt.v1"
COMPLETION_AUTHORITY_SCHEMA = (
    "signal_agent.operational_completed_manifest_verifier_authority.v1"
)
SUPPORTED_VERIFIER_VERSION = "1.0.0"
COMPLETION_POLICY = {
    "policy_id": "operational_completed_manifest_binding",
    "version": "1.0.0",
    "file_sha256": sha256_canonical(
        {
            "completion_state": "completed",
            "manifest_written_last": True,
            "source_mutation_permitted": False,
            "network_authorized": False,
        }
    ),
}


def _reverify_persisted(artifact: PersistedArtifact) -> dict[str, Any]:
    loaded = load_artifact(artifact.path)
    if loaded != thaw_json(artifact.payload):
        raise OperationalArtifactError(f"persisted_artifact_reference_mismatch:{artifact.path.name}")
    return loaded


def _load_sealed_document(path: Path, hash_field: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompletedManifestError(f"completed_document_unreadable:{path.name}") from exc
    if not isinstance(payload, dict):
        raise CompletedManifestError(f"completed_document_object_required:{path.name}")
    if canonical_json_bytes(payload) != raw:
        raise CompletedManifestError(f"completed_document_not_canonical:{path.name}")
    if not verify_seal(payload, hash_field):
        raise CompletedManifestError(f"completed_document_hash_invalid:{path.name}")
    assert_secret_free(payload, label=f"completed_document:{path.name}")
    return payload


def _relative_file(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise CompletedManifestError("completed_artifact_path_invalid")
    target = (root / Path(*relative.parts)).resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if resolved_root != target and resolved_root not in target.parents:
        raise CompletedManifestError("completed_artifact_path_escaped_root")
    if not target.is_file():
        raise CompletedManifestError("completed_artifact_regular_file_required")
    return target


def verify_completed_run(
    completed: CompletedRunReference,
    bounded_material: PersistedArtifact,
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    bounded_verified = _reverify_persisted(bounded_material)
    run_root = completed.run_root.resolve(strict=True)
    manifest_path = _relative_file(run_root, completed.manifest_relative_path)
    receipt_path = _relative_file(run_root, completed.preservation_receipt_relative_path)
    manifest = _load_sealed_document(manifest_path, "manifest_hash")
    receipt = _load_sealed_document(receipt_path, "receipt_hash")
    bounded_bytes = bounded_material.path.read_bytes()
    bounded_source_sha256 = sha256_bytes(bounded_bytes)
    if bounded_source_sha256 != expected_source_sha256:
        raise CompletedManifestError("bounded_material_file_sha256_mismatch")
    if manifest.get("completion_state") != "completed":
        raise CompletedManifestError("completed_manifest_state_required")
    if manifest.get("run_id") != completed.run_id:
        raise CompletedManifestError("completed_manifest_run_id_mismatch")
    bounded = bounded_verified
    expected_input = {
        "bounded_material_id": bounded["bounded_material_id"],
        "bounded_material_hash": bounded["artifact_hash"],
        "observation_set_hash": bounded["observation_set_hash"],
    }
    if manifest.get("operational_input") != expected_input:
        raise CompletedManifestError("completed_manifest_input_mismatch")
    receipt_ref = manifest.get("preservation_receipt")
    expected_receipt_ref = {
        "path": completed.preservation_receipt_relative_path,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_hash": receipt.get("receipt_hash"),
        "file_sha256": sha256_bytes(receipt_path.read_bytes()),
    }
    if receipt_ref != expected_receipt_ref:
        raise CompletedManifestError("completed_manifest_receipt_reference_mismatch")
    if receipt.get("operational_input") != expected_input:
        raise CompletedManifestError("preservation_receipt_input_mismatch")
    if receipt.get("source_sha256") != bounded_source_sha256:
        raise CompletedManifestError("preservation_receipt_source_sha256_mismatch")
    if receipt.get("source_byte_size") != len(bounded_bytes):
        raise CompletedManifestError("preservation_receipt_source_size_mismatch")
    preserved_source_ref = receipt.get("preserved_source")
    if not isinstance(preserved_source_ref, dict):
        raise CompletedManifestError("preserved_source_reference_required")
    preserved_path = _relative_file(run_root, str(preserved_source_ref.get("path") or ""))
    preserved_bytes = preserved_path.read_bytes()
    expected_preserved_ref = {
        "path": str(preserved_source_ref.get("path") or ""),
        "source_sha256": bounded_source_sha256,
        "byte_size": len(bounded_bytes),
    }
    if preserved_source_ref != expected_preserved_ref:
        raise CompletedManifestError("preserved_source_reference_mismatch")
    if preserved_bytes != bounded_bytes:
        raise CompletedManifestError("preserved_source_bytes_mismatch")
    manifest_preserved_source = manifest.get("preserved_source")
    expected_manifest_source = {
        **expected_preserved_ref,
        "file_sha256": sha256_bytes(preserved_bytes),
    }
    if manifest_preserved_source != expected_manifest_source:
        raise CompletedManifestError("completed_manifest_preserved_source_mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise CompletedManifestError("completed_manifest_artifacts_required")
    for descriptor in artifacts:
        if not isinstance(descriptor, dict):
            raise CompletedManifestError("completed_manifest_artifact_descriptor_invalid")
        artifact_path = _relative_file(run_root, str(descriptor.get("path") or ""))
        if descriptor.get("sha256") != sha256_bytes(artifact_path.read_bytes()):
            raise CompletedManifestError("completed_manifest_artifact_hash_mismatch")
    safety = manifest.get("safety_flags")
    if not isinstance(safety, dict):
        raise CompletedManifestError("completed_manifest_safety_flags_required")
    if safety.get("network_authorized") is not False:
        raise CompletedManifestError("completed_manifest_network_authority_forbidden")
    if safety.get("source_records_mutated") is not False:
        raise CompletedManifestError("completed_manifest_source_mutation_forbidden")
    created_at = str(manifest.get("created_at") or "")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_file_sha256": sha256_bytes(manifest_path.read_bytes()),
        "receipt": receipt,
        "receipt_path": receipt_path,
        "receipt_file_sha256": sha256_bytes(receipt_path.read_bytes()),
        "bounded_source_sha256": bounded_source_sha256,
        "preserved_source_path": preserved_path,
        "preserved_source_file_sha256": sha256_bytes(preserved_bytes),
        "verified_at": created_at,
    }


def create_checkpoint_candidate(
    source_root: Path,
    *,
    intent: PersistedArtifact,
    boundary: PersistedArtifact,
    bounded_material: PersistedArtifact,
    observation_index: PersistedArtifact,
    completed: CompletedRunReference,
) -> PersistedArtifact:
    intent_data = _reverify_persisted(intent)
    index_data = _reverify_persisted(observation_index)
    assembly = verify_assembly_evidence(
        source_root,
        boundary=boundary,
        bounded_material=bounded_material,
    )
    boundary_data = assembly["boundary"]
    bounded_data = assembly["bounded_material"]
    if boundary_data["source"] != intent_data["source"]:
        raise CompletedManifestError("candidate_source_identity_mismatch")
    if boundary_data["adapter"] != intent_data["adapter"]:
        raise CompletedManifestError("candidate_adapter_identity_mismatch")
    if boundary_data["acquisition_cycle_id"] != intent_data["acquisition_cycle_id"]:
        raise CompletedManifestError("candidate_acquisition_cycle_mismatch")
    if boundary_data["prior_checkpoint"] != intent_data["prior_checkpoint"]:
        raise CompletedManifestError("candidate_prior_checkpoint_mismatch")
    if boundary_data["observation_boundary"] != intent_data["observation_boundary"]:
        raise CompletedManifestError("candidate_observation_boundary_mismatch")
    if boundary_data["assembly_policy"] != intent_data["assembly_policy"]:
        raise CompletedManifestError("candidate_assembly_policy_mismatch")
    if boundary_data["capture_set_hash"] != index_data["capture_set_hash"]:
        raise CompletedManifestError("candidate_capture_set_mismatch")
    if index_data["observation_set_hash"] != bounded_data["observation_set_hash"]:
        raise CompletedManifestError("candidate_observation_index_mismatch")
    if index_data.get("bounded_material") != {
        "bounded_material_id": bounded_data["bounded_material_id"],
        "bounded_material_hash": bounded_data["artifact_hash"],
    }:
        raise CompletedManifestError("candidate_observation_index_material_mismatch")
    verified = verify_completed_run(
        completed,
        bounded_material,
        expected_source_sha256=assembly["bounded_material_file_sha256"],
    )
    manifest = verified["manifest"]
    material = {
        "schema_version": CHECKPOINT_CANDIDATE_SCHEMA,
        "source": intent_data["source"],
        "adapter": intent_data["adapter"],
        "acquisition_cycle_id": intent_data["acquisition_cycle_id"],
        "prior_checkpoint": intent_data["prior_checkpoint"],
        "acquisition_boundary": {
            "boundary_id": boundary_data["boundary_id"],
            "boundary_hash": boundary_data["artifact_hash"],
            "path": boundary.path.relative_to(source_root).as_posix(),
        },
        "capture_set_hash": boundary_data["capture_set_hash"],
        "observation_set_hash": boundary_data["observation_set_hash"],
        "bounded_material": {
            "bounded_material_id": bounded_data["bounded_material_id"],
            "bounded_material_hash": bounded_data["artifact_hash"],
            "file_sha256": assembly["bounded_material_file_sha256"],
            "path": bounded_material.path.relative_to(source_root).as_posix(),
        },
        "observation_index": ObservationIndexReference(
            observation_index_id=index_data["observation_index_id"],
            observation_index_hash=index_data["artifact_hash"],
            path=observation_index.path.relative_to(source_root).as_posix(),
        ).to_dict(),
        "preservation_receipt": {
            "receipt_id": verified["receipt"]["receipt_id"],
            "receipt_hash": verified["receipt"]["receipt_hash"],
            "file_sha256": verified["receipt_file_sha256"],
            "path": completed.preservation_receipt_relative_path,
            "source_sha256": verified["bounded_source_sha256"],
            "preserved_source_path": verified["receipt"]["preserved_source"]["path"],
            "preserved_source_file_sha256": verified["preserved_source_file_sha256"],
        },
        "completed_run": {
            "run_id": completed.run_id,
            "run_root_ref": completed.run_root_ref,
            "manifest_id": manifest["manifest_id"],
            "manifest_hash": manifest["manifest_hash"],
            "manifest_file_sha256": verified["manifest_file_sha256"],
            "manifest_path": completed.manifest_relative_path,
        },
        "completion_policy": dict(COMPLETION_POLICY),
        "created_at": manifest["created_at"],
        "status": "eligible_uncommitted",
    }
    identity_material = {
        key: value for key, value in material.items() if key not in {"created_at", "status"}
    }
    candidate_id = derive_id("ockc", CHECKPOINT_CANDIDATE_SCHEMA, identity_material)
    payload = seal({**material, "candidate_id": candidate_id, "artifact_id": candidate_id})
    return write_immutable_json(
        source_root / f"checkpoint_candidates/{candidate_id}.checkpoint-candidate.json",
        payload,
    )


def _verify_candidate_identity(candidate_data: dict[str, Any]) -> None:
    if candidate_data.get("schema_version") != CHECKPOINT_CANDIDATE_SCHEMA:
        raise CheckpointConflictError("checkpoint_candidate_schema_invalid")
    if candidate_data.get("status") != "eligible_uncommitted":
        raise CheckpointConflictError("checkpoint_candidate_status_invalid")
    if candidate_data.get("candidate_id") != candidate_data.get("artifact_id"):
        raise CheckpointConflictError("checkpoint_candidate_identity_mismatch")
    material = {
        key: value
        for key, value in candidate_data.items()
        if key not in {"artifact_hash", "artifact_id", "candidate_id", "created_at", "status"}
    }
    expected_id = derive_id("ockc", CHECKPOINT_CANDIDATE_SCHEMA, material)
    if candidate_data.get("candidate_id") != expected_id:
        raise CheckpointConflictError("checkpoint_candidate_derivation_mismatch")
    if candidate_data.get("completion_policy") != COMPLETION_POLICY:
        raise CheckpointConflictError("checkpoint_candidate_completion_policy_mismatch")


def create_completed_manifest_verifier_authority(
    source_root: Path,
    *,
    candidate: PersistedArtifact,
    intent: PersistedArtifact,
    boundary: PersistedArtifact,
    bounded_material: PersistedArtifact,
    observation_index: PersistedArtifact,
    completed: CompletedRunReference,
) -> PersistedArtifact:
    verified_candidate = create_checkpoint_candidate(
        source_root,
        intent=intent,
        boundary=boundary,
        bounded_material=bounded_material,
        observation_index=observation_index,
        completed=completed,
    )
    candidate_data = _reverify_persisted(candidate)
    if candidate_data != thaw_json(verified_candidate.payload):
        raise CheckpointConflictError("completion_authority_candidate_mismatch")
    _verify_candidate_identity(candidate_data)
    authority = CompletedManifestVerifierAuthority(
        candidate_id=str(candidate_data["candidate_id"]),
        candidate_hash=str(candidate_data["artifact_hash"]),
        verifier_version=SUPPORTED_VERIFIER_VERSION,
        completion_policy=PolicyIdentity(
            policy_id=COMPLETION_POLICY["policy_id"],
            version=COMPLETION_POLICY["version"],
            file_sha256=COMPLETION_POLICY["file_sha256"],
        ),
        verified_at=str(candidate_data["created_at"]),
        completed_run={
            **candidate_data["completed_run"],
            "preservation_receipt": candidate_data["preservation_receipt"],
            "bounded_material": candidate_data["bounded_material"],
            "acquisition_boundary": candidate_data["acquisition_boundary"],
        },
        assertions={
            "acquisition_boundary_verified": True,
            "capture_receipts_verified": True,
            "capture_bodies_verified": True,
            "bounded_material_verified": True,
            "preservation_receipt_verified": True,
            "preserved_source_bytes_verified": True,
            "completed_manifest_verified": True,
            "manifest_artifacts_verified": True,
            "source_records_mutated": False,
        },
    ).to_dict()
    authority_material = {
        "schema_version": COMPLETION_AUTHORITY_SCHEMA,
        **authority,
    }
    authority_id = derive_id("ocma", COMPLETION_AUTHORITY_SCHEMA, authority_material)
    payload = seal(
        {
            **authority_material,
            "authority_id": authority_id,
            "artifact_id": authority_id,
        }
    )
    return write_immutable_json(
        source_root / f"completion_authorities/{authority_id}.authority.json",
        payload,
    )


def _validate_existing_commit(
    payload: dict[str, Any],
    *,
    candidate: PersistedArtifact,
    prior_id: str,
) -> None:
    candidate_data = thaw_json(candidate.payload)
    if payload.get("prior_checkpoint_id") != prior_id:
        raise CheckpointConflictError("checkpoint_prior_mismatch")
    reference = payload.get("checkpoint_candidate")
    if reference != {
        "candidate_id": candidate_data["candidate_id"],
        "candidate_hash": candidate_data["artifact_hash"],
        "path": candidate.path.relative_to(candidate.path.parents[1]).as_posix(),
    }:
        raise CheckpointConflictError("divergent_checkpoint_successor")


def _load_candidate_local_chain(
    source_root: Path, candidate: PersistedArtifact
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_data = _reverify_persisted(candidate)
    _verify_candidate_identity(candidate_data)
    source = candidate_data.get("source")
    if not isinstance(source, dict):
        raise CheckpointConflictError("checkpoint_candidate_source_invalid")
    expected_source_root = derive_id(
        "osi", source.get("source_type"), source.get("source_instance_id")
    )
    if source_root.name != expected_source_root:
        raise CheckpointConflictError("checkpoint_candidate_source_root_mismatch")

    boundary_ref = candidate_data.get("acquisition_boundary")
    bounded_ref = candidate_data.get("bounded_material")
    index_ref = candidate_data.get("observation_index")
    if not isinstance(boundary_ref, dict) or not isinstance(bounded_ref, dict):
        raise CheckpointConflictError("checkpoint_candidate_assembly_reference_invalid")
    if not isinstance(index_ref, dict):
        raise CheckpointConflictError("checkpoint_candidate_index_reference_invalid")
    boundary_path = safe_artifact_path(source_root, str(boundary_ref.get("path") or ""))
    bounded_path = safe_artifact_path(source_root, str(bounded_ref.get("path") or ""))
    index_path = safe_artifact_path(source_root, str(index_ref.get("path") or ""))
    boundary_data = load_artifact(boundary_path)
    bounded_data = load_artifact(bounded_path)
    index_data = load_artifact(index_path)
    if boundary_ref != {
        "boundary_id": boundary_data.get("boundary_id"),
        "boundary_hash": boundary_data.get("artifact_hash"),
        "path": str(boundary_ref.get("path")),
    }:
        raise CheckpointConflictError("checkpoint_candidate_boundary_reference_mismatch")
    actual_bounded_file_sha256 = sha256_bytes(bounded_path.read_bytes())
    if bounded_ref != {
        "bounded_material_id": bounded_data.get("bounded_material_id"),
        "bounded_material_hash": bounded_data.get("artifact_hash"),
        "file_sha256": actual_bounded_file_sha256,
        "path": str(bounded_ref.get("path")),
    }:
        raise CheckpointConflictError("checkpoint_candidate_bounded_reference_mismatch")
    if index_ref != {
        "observation_index_id": index_data.get("observation_index_id"),
        "observation_index_hash": index_data.get("artifact_hash"),
        "path": str(index_ref.get("path")),
    }:
        raise CheckpointConflictError("checkpoint_candidate_index_reference_mismatch")
    assembly = verify_assembly_evidence(
        source_root,
        boundary=PersistedArtifact(
            path=boundary_path, payload=boundary_data, idempotent_replay=True
        ),
        bounded_material=PersistedArtifact(
            path=bounded_path, payload=bounded_data, idempotent_replay=True
        ),
    )
    if candidate_data["source"] != boundary_data["source"]:
        raise CheckpointConflictError("checkpoint_candidate_source_binding_mismatch")
    if candidate_data["adapter"] != boundary_data["adapter"]:
        raise CheckpointConflictError("checkpoint_candidate_adapter_binding_mismatch")
    if candidate_data["acquisition_cycle_id"] != boundary_data["acquisition_cycle_id"]:
        raise CheckpointConflictError("checkpoint_candidate_cycle_binding_mismatch")
    if candidate_data["prior_checkpoint"] != boundary_data["prior_checkpoint"]:
        raise CheckpointConflictError("checkpoint_candidate_prior_binding_mismatch")
    if candidate_data["capture_set_hash"] != boundary_data["capture_set_hash"]:
        raise CheckpointConflictError("checkpoint_candidate_capture_set_binding_mismatch")
    if candidate_data["observation_set_hash"] != boundary_data["observation_set_hash"]:
        raise CheckpointConflictError("checkpoint_candidate_observation_set_binding_mismatch")
    if candidate_data["bounded_material"] != boundary_data["bounded_material"]:
        raise CheckpointConflictError("checkpoint_candidate_bounded_boundary_mismatch")
    if index_data.get("capture_set_hash") != boundary_data["capture_set_hash"]:
        raise CheckpointConflictError("checkpoint_candidate_index_capture_mismatch")
    if index_data.get("observation_set_hash") != boundary_data["observation_set_hash"]:
        raise CheckpointConflictError("checkpoint_candidate_index_observation_mismatch")
    return candidate_data, assembly


def _expected_authority_completed_run(candidate_data: dict[str, Any]) -> dict[str, Any]:
    return {
        **candidate_data["completed_run"],
        "preservation_receipt": candidate_data["preservation_receipt"],
        "bounded_material": candidate_data["bounded_material"],
        "acquisition_boundary": candidate_data["acquisition_boundary"],
    }


def _reverify_candidate_completed_run(
    source_root: Path,
    candidate_data: dict[str, Any],
    assembly: dict[str, Any],
    completed: CompletedRunReference,
) -> dict[str, Any]:
    bounded_ref = candidate_data["bounded_material"]
    bounded_path = safe_artifact_path(source_root, str(bounded_ref["path"]))
    bounded_data = load_artifact(bounded_path)
    bounded = PersistedArtifact(
        path=bounded_path, payload=bounded_data, idempotent_replay=True
    )
    verified = verify_completed_run(
        completed,
        bounded,
        expected_source_sha256=assembly["bounded_material_file_sha256"],
    )
    manifest = verified["manifest"]
    expected_preservation = {
        "receipt_id": verified["receipt"]["receipt_id"],
        "receipt_hash": verified["receipt"]["receipt_hash"],
        "file_sha256": verified["receipt_file_sha256"],
        "path": completed.preservation_receipt_relative_path,
        "source_sha256": verified["bounded_source_sha256"],
        "preserved_source_path": verified["receipt"]["preserved_source"]["path"],
        "preserved_source_file_sha256": verified["preserved_source_file_sha256"],
    }
    if candidate_data.get("preservation_receipt") != expected_preservation:
        raise CheckpointConflictError("checkpoint_candidate_preservation_binding_mismatch")
    expected_completed = {
        "run_id": completed.run_id,
        "run_root_ref": completed.run_root_ref,
        "manifest_id": manifest["manifest_id"],
        "manifest_hash": manifest["manifest_hash"],
        "manifest_file_sha256": verified["manifest_file_sha256"],
        "manifest_path": completed.manifest_relative_path,
    }
    if candidate_data.get("completed_run") != expected_completed:
        raise CheckpointConflictError("checkpoint_candidate_completed_run_binding_mismatch")
    return verified


def _verify_completion_authority(
    source_root: Path,
    authority: PersistedArtifact,
    candidate_data: dict[str, Any],
) -> dict[str, Any]:
    authority_data = _reverify_persisted(authority)
    if authority_data.get("schema_version") != COMPLETION_AUTHORITY_SCHEMA:
        raise CheckpointConflictError("completion_authority_schema_invalid")
    if authority_data.get("authority_id") != authority_data.get("artifact_id"):
        raise CheckpointConflictError("completion_authority_identity_mismatch")
    authority_material = {
        key: value
        for key, value in authority_data.items()
        if key not in {"artifact_hash", "artifact_id", "authority_id"}
    }
    expected_authority_id = derive_id(
        "ocma", COMPLETION_AUTHORITY_SCHEMA, authority_material
    )
    if authority_data.get("authority_id") != expected_authority_id:
        raise CheckpointConflictError("completion_authority_derivation_mismatch")
    if authority_data.get("authority_type") != "completed_manifest_verifier":
        raise CheckpointConflictError("completion_authority_type_unsupported")
    if authority_data.get("verifier_version") != SUPPORTED_VERIFIER_VERSION:
        raise CheckpointConflictError("completion_authority_version_unsupported")
    if authority_data.get("candidate") != {
        "candidate_id": candidate_data["candidate_id"],
        "candidate_hash": candidate_data["artifact_hash"],
    }:
        raise CheckpointConflictError("completion_authority_candidate_binding_mismatch")
    if authority_data.get("completion_policy") != COMPLETION_POLICY:
        raise CheckpointConflictError("completion_authority_policy_mismatch")
    if authority_data.get("completed_run") != _expected_authority_completed_run(candidate_data):
        raise CheckpointConflictError("completion_authority_completed_run_mismatch")
    required_assertions = {
        "acquisition_boundary_verified": True,
        "capture_receipts_verified": True,
        "capture_bodies_verified": True,
        "bounded_material_verified": True,
        "preservation_receipt_verified": True,
        "preserved_source_bytes_verified": True,
        "completed_manifest_verified": True,
        "manifest_artifacts_verified": True,
        "source_records_mutated": False,
    }
    if authority_data.get("assertions") != required_assertions:
        raise CheckpointConflictError("completion_authority_assertions_invalid")
    for flag in (
        "external_action_authorized",
        "network_authorized",
        "upstream_write_authorized",
    ):
        if authority_data.get(flag) is not False:
            raise CheckpointConflictError(f"completion_authority_{flag}_forbidden")
    authority_path = authority.path.resolve(strict=True)
    if source_root.resolve(strict=True) not in authority_path.parents:
        raise CheckpointConflictError("completion_authority_outside_source_root")
    return authority_data


def commit_checkpoint(
    source_root: Path,
    *,
    candidate: PersistedArtifact,
    authority: PersistedArtifact,
    completed: CompletedRunReference,
    committed_at: str,
) -> PersistedArtifact:
    candidate_data = _reverify_persisted(candidate)
    _verify_candidate_identity(candidate_data)
    prior = candidate_data["prior_checkpoint"]
    prior_id = "root" if prior is None else str(prior["checkpoint_id"])
    slot = source_root / f"checkpoints/from-{prior_id}/checkpoint-commit.json"
    if slot.exists():
        existing = load_artifact(slot)
        _validate_existing_commit(existing, candidate=candidate, prior_id=prior_id)
        candidate_data, assembly = _load_candidate_local_chain(source_root, candidate)
        _reverify_candidate_completed_run(source_root, candidate_data, assembly, completed)
        _verify_completion_authority(source_root, authority, candidate_data)
        _verify_commit_receipt(source_root, existing)
        return PersistedArtifact(path=slot, payload=existing, idempotent_replay=True)
    candidate_data, assembly = _load_candidate_local_chain(source_root, candidate)
    _reverify_candidate_completed_run(source_root, candidate_data, assembly, completed)
    authority_data = _verify_completion_authority(source_root, authority, candidate_data)
    current = resolve_current_checkpoint(source_root)
    if current is None:
        if prior is not None:
            raise CheckpointConflictError("checkpoint_predecessor_not_current")
    elif prior != {
        "checkpoint_id": current.payload["checkpoint_id"],
        "checkpoint_hash": current.payload["artifact_hash"],
    }:
        raise CheckpointConflictError("checkpoint_predecessor_not_current")
    material = {
        "schema_version": CHECKPOINT_COMMIT_SCHEMA,
        "source": candidate_data["source"],
        "adapter": candidate_data["adapter"],
        "prior_checkpoint_id": prior_id,
        "prior_checkpoint_hash": None if prior is None else prior["checkpoint_hash"],
        "checkpoint_candidate": {
            "candidate_id": candidate_data["candidate_id"],
            "candidate_hash": candidate_data["artifact_hash"],
            "path": candidate.path.relative_to(source_root).as_posix(),
        },
        "acquisition_boundary": candidate_data["acquisition_boundary"],
        "capture_set_hash": candidate_data["capture_set_hash"],
        "observation_set_hash": candidate_data["observation_set_hash"],
        "bounded_material": candidate_data["bounded_material"],
        "observation_index": candidate_data["observation_index"],
        "preservation_receipt": candidate_data["preservation_receipt"],
        "completed_run": candidate_data["completed_run"],
        "completion_authority": {
            "authority_id": authority_data["authority_id"],
            "authority_hash": authority_data["artifact_hash"],
            "path": authority.path.relative_to(source_root).as_posix(),
        },
        "committed_at": committed_at,
        "status": "committed",
        "upstream_write_authorized": False,
    }
    commit_id = derive_id("ock", CHECKPOINT_COMMIT_SCHEMA, material)
    payload = seal({**material, "checkpoint_id": commit_id, "artifact_id": commit_id})
    try:
        return write_immutable_json(slot, payload)
    except ImmutableArtifactConflictError:
        existing = load_artifact(slot)
        _verify_commit_receipt(source_root, existing)
        _validate_existing_commit(existing, candidate=candidate, prior_id=prior_id)
        return PersistedArtifact(path=slot, payload=existing, idempotent_replay=True)


def _verify_commit_receipt(source_root: Path, payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != CHECKPOINT_COMMIT_SCHEMA:
        raise OperationalArtifactError("checkpoint_commit_schema_invalid")
    if payload.get("checkpoint_id") != payload.get("artifact_id"):
        raise OperationalArtifactError("checkpoint_commit_identity_mismatch")
    if payload.get("status") != "committed":
        raise OperationalArtifactError("checkpoint_commit_state_invalid")
    if payload.get("upstream_write_authorized") is not False:
        raise OperationalArtifactError("checkpoint_commit_upstream_authority_forbidden")
    candidate_ref = payload.get("checkpoint_candidate")
    authority_ref = payload.get("completion_authority")
    if not isinstance(candidate_ref, dict) or not isinstance(authority_ref, dict):
        raise OperationalArtifactError("checkpoint_commit_verification_references_required")
    candidate_path = safe_artifact_path(source_root, str(candidate_ref.get("path") or ""))
    authority_path = safe_artifact_path(source_root, str(authority_ref.get("path") or ""))
    candidate_data = load_artifact(candidate_path)
    candidate = PersistedArtifact(
        path=candidate_path, payload=candidate_data, idempotent_replay=True
    )
    candidate_data, _assembly = _load_candidate_local_chain(source_root, candidate)
    if candidate_ref != {
        "candidate_id": candidate_data["candidate_id"],
        "candidate_hash": candidate_data["artifact_hash"],
        "path": str(candidate_ref.get("path")),
    }:
        raise OperationalArtifactError("checkpoint_commit_candidate_reference_mismatch")
    authority_data = load_artifact(authority_path)
    authority = PersistedArtifact(
        path=authority_path, payload=authority_data, idempotent_replay=True
    )
    _verify_completion_authority(source_root, authority, candidate_data)
    if authority_ref != {
        "authority_id": authority_data["authority_id"],
        "authority_hash": authority_data["artifact_hash"],
        "path": str(authority_ref.get("path")),
    }:
        raise OperationalArtifactError("checkpoint_commit_authority_reference_mismatch")
    for field in (
        "source",
        "adapter",
        "acquisition_boundary",
        "capture_set_hash",
        "observation_set_hash",
        "bounded_material",
        "observation_index",
        "preservation_receipt",
        "completed_run",
    ):
        if payload.get(field) != candidate_data.get(field):
            raise OperationalArtifactError(f"checkpoint_commit_{field}_mismatch")
    material = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_hash", "artifact_id", "checkpoint_id"}
    }
    expected_id = derive_id("ock", CHECKPOINT_COMMIT_SCHEMA, material)
    if payload.get("checkpoint_id") != expected_id:
        raise OperationalArtifactError("checkpoint_commit_derivation_mismatch")


def resolve_current_checkpoint(source_root: Path) -> PersistedArtifact | None:
    prior_id = "root"
    prior_hash: str | None = None
    current: PersistedArtifact | None = None
    seen: set[str] = set()
    while True:
        if prior_id in seen:
            raise OperationalArtifactError("checkpoint_chain_cycle")
        seen.add(prior_id)
        slot = source_root / f"checkpoints/from-{prior_id}/checkpoint-commit.json"
        if not slot.exists():
            return current
        payload = load_artifact(slot)
        _verify_commit_receipt(source_root, payload)
        if payload.get("prior_checkpoint_id") != prior_id:
            raise OperationalArtifactError("checkpoint_chain_prior_id_mismatch")
        if payload.get("prior_checkpoint_hash") != prior_hash:
            raise OperationalArtifactError("checkpoint_chain_prior_hash_mismatch")
        if payload.get("status") != "committed":
            raise OperationalArtifactError("checkpoint_chain_commit_state_invalid")
        current = PersistedArtifact(path=slot, payload=payload, idempotent_replay=True)
        prior_id = str(payload["checkpoint_id"])
        prior_hash = str(payload["artifact_hash"])


def resolve_ingestion_state(source_root: Path, session_id: str | None = None) -> ResolvedIngestionState:
    current = resolve_current_checkpoint(source_root)
    stage = "not_started"
    selected_session: str | None = session_id
    if session_id is not None:
        session_root = source_root / f"sessions/{session_id}"
        if (session_root / "00_intent/session_descriptor.json").exists():
            stage = "opened"
        if (session_root / "03_boundary/acquisition_boundary.json").exists():
            stage = "capture_sealed"
        for candidate_path in (source_root / "checkpoint_candidates").glob(
            "*.checkpoint-candidate.json"
        ) if (source_root / "checkpoint_candidates").exists() else ():
            candidate = load_artifact(candidate_path)
            boundary = candidate.get("acquisition_boundary") or {}
            session_boundary = session_root / "03_boundary/acquisition_boundary.json"
            if session_boundary.exists():
                boundary_payload = load_artifact(session_boundary)
                if boundary.get("boundary_id") == boundary_payload.get("boundary_id"):
                    stage = "governed_completed"
                    if current and current.payload["checkpoint_candidate"]["candidate_id"] == candidate["candidate_id"]:
                        stage = "checkpoint_committed"
                    break
    return ResolvedIngestionState(
        stage=stage,
        source_instance_id=source_root.name,
        session_id=selected_session,
        current_checkpoint_id=(None if current is None else str(current.payload["checkpoint_id"])),
        current_checkpoint_hash=(None if current is None else str(current.payload["artifact_hash"])),
    )
