from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from .canonical import (
    canonical_json_bytes,
    derive_id,
    require_sha256,
    require_text,
    seal,
    sha256_bytes,
    sha256_canonical,
    verify_seal,
)
from .errors import (
    ImmutableArtifactConflictError,
    OperationalArtifactError,
    OperationalValidationError,
)
from .models import (
    AcquisitionIntent,
    CanonicalObservation,
    CapturedPage,
    PersistedArtifact,
    RequestAttempt,
    thaw_json,
)
from .secrets import assert_secret_free, assert_secret_free_bytes


INTENT_SCHEMA = "signal_agent.operational_acquisition_intent.v1"
SESSION_SCHEMA = "signal_agent.operational_acquisition_session.v1"
ATTEMPT_SCHEMA = "signal_agent.operational_request_attempt_receipt.v1"
CAPTURE_SCHEMA = "signal_agent.operational_page_capture_receipt.v1"
BOUNDARY_SCHEMA = "signal_agent.operational_acquisition_boundary.v1"
BOUNDED_MATERIAL_SCHEMA = "signal_agent.operational_bounded_source_material.v1"
OBSERVATION_INDEX_SCHEMA = "signal_agent.operational_observation_index.v1"
FAILURE_SCHEMA = "signal_agent.operational_ingestion_failure_receipt.v1"


def _artifact(payload: dict[str, Any], *, artifact_id: str) -> dict[str, Any]:
    material = dict(payload)
    material["artifact_id"] = artifact_id
    return seal(material)


def _parse_canonical_json(path: Path, *, hash_field: str = "artifact_hash") -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperationalArtifactError(f"operational_artifact_unreadable:{path.name}") from exc
    if not isinstance(value, dict):
        raise OperationalArtifactError(f"operational_artifact_object_required:{path.name}")
    if canonical_json_bytes(value) != raw:
        raise OperationalArtifactError(f"operational_artifact_not_canonical:{path.name}")
    if not verify_seal(value, hash_field):
        raise OperationalArtifactError(f"operational_artifact_hash_invalid:{path.name}")
    assert_secret_free(value, label=f"artifact:{path.name}")
    return value


def load_artifact(path: str | Path, *, hash_field: str = "artifact_hash") -> dict[str, Any]:
    target = Path(path)
    if not target.exists() or not target.is_file():
        raise OperationalArtifactError(f"operational_artifact_regular_file_required:{target.name}")
    return _parse_canonical_json(target, hash_field=hash_field)


def write_immutable_json(path: str | Path, payload: dict[str, Any]) -> PersistedArtifact:
    target = Path(path)
    assert_secret_free(payload, label=f"artifact:{target.name}")
    expected = canonical_json_bytes(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = _parse_canonical_json(target)
        if target.read_bytes() != expected:
            raise ImmutableArtifactConflictError(f"immutable_artifact_conflict:{target.name}")
        return PersistedArtifact(path=target, payload=existing, idempotent_replay=True)
    try:
        with target.open("xb") as handle:
            if handle.write(expected) != len(expected):
                raise OSError("operational_artifact_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        existing = _parse_canonical_json(target)
        if target.read_bytes() != expected:
            raise ImmutableArtifactConflictError(f"immutable_artifact_conflict:{target.name}")
        return PersistedArtifact(path=target, payload=existing, idempotent_replay=True)
    return PersistedArtifact(path=target, payload=payload, idempotent_replay=False)


def write_content_blob(path: str | Path, payload: bytes) -> tuple[Path, bool]:
    target = Path(path)
    assert_secret_free_bytes(payload, label=f"capture_body:{target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != payload:
            raise ImmutableArtifactConflictError(f"immutable_capture_conflict:{target.name}")
        return target, True
    try:
        with target.open("xb") as handle:
            if handle.write(payload) != len(payload):
                raise OSError("operational_capture_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if target.read_bytes() != payload:
            raise ImmutableArtifactConflictError(f"immutable_capture_conflict:{target.name}")
        return target, True
    return target, False


def safe_artifact_path(root: str | Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise OperationalValidationError("operational_artifact_path_invalid")
    resolved_root = Path(root).resolve(strict=True)
    resolved = (resolved_root / Path(*relative.parts)).resolve(strict=True)
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise OperationalValidationError("operational_artifact_path_escaped_root")
    if not resolved.is_file():
        raise OperationalValidationError("operational_artifact_regular_file_required")
    return resolved


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    except ValueError as exc:
        raise OperationalValidationError("operational_artifact_outside_source_root") from exc


def persist_intent(session_root: Path, intent: AcquisitionIntent) -> PersistedArtifact:
    material = intent.to_material_dict()
    intent_id = derive_id("oai", INTENT_SCHEMA, material)
    payload = _artifact(
        {
            "schema_version": INTENT_SCHEMA,
            "intent_id": intent_id,
            "acquisition_cycle_id": intent.cycle_id,
            **material,
        },
        artifact_id=intent_id,
    )
    return write_immutable_json(session_root / "00_intent/acquisition_intent.json", payload)


def persist_session(
    session_root: Path,
    *,
    intent_payload: dict[str, Any],
    started_at: str,
    transport_kind: str,
    mode: str,
) -> PersistedArtifact:
    session_id = derive_id(
        "oas",
        SESSION_SCHEMA,
        intent_payload["acquisition_cycle_id"],
        started_at,
        transport_kind,
        mode,
    )
    payload = _artifact(
        {
            "schema_version": SESSION_SCHEMA,
            "session_id": session_id,
            "acquisition_cycle_id": intent_payload["acquisition_cycle_id"],
            "intent": {
                "intent_id": intent_payload["intent_id"],
                "intent_hash": intent_payload["artifact_hash"],
            },
            "source": intent_payload["source"],
            "started_at": started_at,
            "transport_kind": transport_kind,
            "mode": mode,
            "state_model": "immutable_artifact_chain.v1",
        },
        artifact_id=session_id,
    )
    return write_immutable_json(session_root / "00_intent/session_descriptor.json", payload)


def persist_attempt(
    session_root: Path,
    *,
    session_id: str,
    attempt: RequestAttempt,
) -> PersistedArtifact:
    material = {
        "schema_version": ATTEMPT_SCHEMA,
        "session_id": session_id,
        "page_ordinal": attempt.page_ordinal,
        "attempt_ordinal": attempt.attempt_ordinal,
        "request_fingerprint": attempt.request_fingerprint,
        "continuation_hash": attempt.continuation_hash,
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at,
        "outcome": attempt.outcome,
        "status_code": attempt.status_code,
        "provider_error_code": attempt.provider_error_code,
        "requested_delay_ms": attempt.requested_delay_ms,
        "applied_delay_ms": attempt.applied_delay_ms,
        "response_metadata": thaw_json(attempt.response_metadata),
        "detail_omitted": attempt.outcome != "success",
        "secret_material_persisted": False,
    }
    attempt_id = derive_id("oat", ATTEMPT_SCHEMA, material)
    payload = _artifact({**material, "attempt_id": attempt_id}, artifact_id=attempt_id)
    return write_immutable_json(
        session_root / f"01_attempts/{attempt_id}.attempt.json",
        payload,
    )


def persist_capture(
    session_root: Path,
    *,
    session_id: str,
    page: CapturedPage,
    successful_attempt: PersistedArtifact,
    previous_capture: PersistedArtifact | None,
) -> PersistedArtifact:
    attempt = thaw_json(successful_attempt.payload)
    if attempt["outcome"] != "success":
        raise OperationalValidationError("capture_successful_attempt_required")
    if attempt["page_ordinal"] != page.page_ordinal:
        raise OperationalValidationError("capture_attempt_page_mismatch")
    if attempt["attempt_ordinal"] != page.successful_attempt_ordinal:
        raise OperationalValidationError("capture_attempt_ordinal_mismatch")
    if attempt["request_fingerprint"] != page.request_fingerprint:
        raise OperationalValidationError("capture_request_fingerprint_mismatch")
    body_sha256 = sha256_bytes(page.response_body)
    body_id = derive_id("ocb", body_sha256)
    body_path, _body_replay = write_content_blob(
        session_root / f"02_captures/{body_id}.body",
        page.response_body,
    )
    observation_refs = [
        {
            "observation_id": item.observation_id,
            "protected_source_record_id": item.protected_source_record_id,
            "content_hash": item.content_hash,
            "record_type": item.record_type,
        }
        for item in sorted(page.observations, key=lambda value: value.observation_id)
    ]
    material = {
        "schema_version": CAPTURE_SCHEMA,
        "session_id": session_id,
        "attempt": {
            "attempt_id": attempt["attempt_id"],
            "attempt_hash": attempt["artifact_hash"],
            "path": successful_attempt.path.relative_to(session_root).as_posix(),
        },
        "previous_capture": (
            None
            if previous_capture is None
            else {
                "capture_id": previous_capture.payload["capture_id"],
                "capture_hash": previous_capture.payload["artifact_hash"],
                "page_ordinal": previous_capture.payload["page_ordinal"],
            }
        ),
        "page_ordinal": page.page_ordinal,
        "request_fingerprint": page.request_fingerprint,
        "continuation_hash": page.continuation_hash,
        "captured_at": page.captured_at,
        "response_schema": page.response_schema,
        "media_type": page.media_type,
        "response_body": {
            "body_id": body_id,
            "body_sha256": body_sha256,
            "byte_size": len(page.response_body),
            "path": body_path.relative_to(session_root).as_posix(),
        },
        "response_metadata": thaw_json(page.response_metadata),
        "terminal": page.terminal,
        "next_continuation": thaw_json(page.next_continuation),
        "observations": observation_refs,
        "secret_material_persisted": False,
    }
    capture_id = derive_id("opc", CAPTURE_SCHEMA, material)
    payload = _artifact({**material, "capture_id": capture_id}, artifact_id=capture_id)
    return write_immutable_json(
        session_root / f"02_captures/{capture_id}.capture.json",
        payload,
    )


def canonical_observations(pages: Sequence[CapturedPage]) -> tuple[dict[str, Any], ...]:
    observations: dict[str, dict[str, Any]] = {}
    for page in pages:
        for item in page.observations:
            semantic = item.semantic_dict()
            existing = observations.get(item.observation_id)
            if existing is not None and existing != semantic:
                raise OperationalValidationError("observation_identity_collision")
            observations[item.observation_id] = semantic
    return tuple(observations[key] for key in sorted(observations))


def observation_set_hash(observations: Sequence[dict[str, Any]]) -> str:
    return sha256_canonical(list(observations))


def semantic_observation_counts(observations: Sequence[dict[str, Any]]) -> dict[str, int]:
    source_record_ids = {str(item["protected_source_record_id"]) for item in observations}
    return {
        "source_record_identity_count": len(source_record_ids),
        "canonical_observation_count": len(observations),
        "observation_version_count": len(observations),
        "changed_observation_count": max(0, len(observations) - len(source_record_ids)),
        "tombstone_observation_count": sum(
            1 for item in observations if item.get("observation_state") == "tombstone"
        ),
    }


def capture_set_hash(captures: Sequence[PersistedArtifact]) -> str:
    exact_history = [
        {
            "capture_id": item.payload["capture_id"],
            "capture_hash": item.payload["artifact_hash"],
            "page_ordinal": item.payload["page_ordinal"],
            "attempt_id": item.payload["attempt"]["attempt_id"],
            "body_sha256": item.payload["response_body"]["body_sha256"],
        }
        for item in sorted(captures, key=lambda value: int(value.payload["page_ordinal"]))
    ]
    return sha256_canonical(exact_history)


def persist_bounded_material(
    session_root: Path,
    *,
    intent_payload: dict[str, Any],
    observations: Sequence[dict[str, Any]],
) -> PersistedArtifact:
    semantic_hash = observation_set_hash(observations)
    semantic_counts = semantic_observation_counts(observations)
    material_id = derive_id(
        "obm",
        BOUNDED_MATERIAL_SCHEMA,
        intent_payload["source"],
        intent_payload["adapter"],
        intent_payload["assembly_policy"],
        intent_payload["observation_boundary"],
        semantic_hash,
        semantic_counts,
    )
    payload = _artifact(
        {
            "schema_version": BOUNDED_MATERIAL_SCHEMA,
            "bounded_material_id": material_id,
            "source": intent_payload["source"],
            "adapter": intent_payload["adapter"],
            "assembly_policy": intent_payload["assembly_policy"],
            "observation_boundary": intent_payload["observation_boundary"],
            "observation_set_hash": semantic_hash,
            "observations": list(observations),
            "observation_count": len(observations),
            "semantic_counts": semantic_counts,
            "semantic_identity_excludes": [
                "acquisition_time",
                "attempt_receipts",
                "capture_set_hash",
                "page_boundaries",
                "retry_history",
            ],
            "transport_provenance_external": True,
        },
        artifact_id=material_id,
    )
    return write_immutable_json(
        session_root / f"04_batch/{material_id}.source.json",
        payload,
    )


def persist_boundary(
    source_root: Path,
    session_root: Path,
    *,
    intent_payload: dict[str, Any],
    session_payload: dict[str, Any],
    captures: Sequence[PersistedArtifact],
    bounded_material: PersistedArtifact,
    created_at: str,
) -> PersistedArtifact:
    exact_hash = capture_set_hash(captures)
    semantic_hash = bounded_material.payload["observation_set_hash"]
    bounded_bytes = bounded_material.path.read_bytes()
    provenance: dict[str, list[dict[str, Any]]] = {}
    capture_refs: list[dict[str, Any]] = []
    for capture in sorted(captures, key=lambda value: int(value.payload["page_ordinal"])):
        data = thaw_json(capture.payload)
        capture_refs.append(
            {
                "capture_id": data["capture_id"],
                "capture_hash": data["artifact_hash"],
                "path": _relative(source_root, capture.path),
                "page_ordinal": data["page_ordinal"],
            }
        )
        for locator, observation in enumerate(data["observations"], start=1):
            provenance.setdefault(observation["observation_id"], []).append(
                {
                    "capture_id": data["capture_id"],
                    "page_ordinal": data["page_ordinal"],
                    "record_locator": locator,
                }
            )
    last_capture = thaw_json(captures[-1].payload)
    captured_record_count = sum(len(capture.payload["observations"]) for capture in captures)
    semantic_counts = thaw_json(bounded_material.payload["semantic_counts"])
    counts = {
        "captured_record_count": captured_record_count,
        **semantic_counts,
        "duplicate_observation_count": (
            captured_record_count - int(semantic_counts["canonical_observation_count"])
        ),
    }
    material = {
        "schema_version": BOUNDARY_SCHEMA,
        "source": intent_payload["source"],
        "adapter": intent_payload["adapter"],
        "acquisition_cycle_id": intent_payload["acquisition_cycle_id"],
        "session_id": session_payload["session_id"],
        "prior_checkpoint": intent_payload["prior_checkpoint"],
        "observation_boundary": intent_payload["observation_boundary"],
        "coverage": {
            "kind": intent_payload["observation_boundary"]["kind"],
            "lower_observation_boundary": intent_payload["observation_boundary"]["lower"],
            "upper_observation_boundary": intent_payload["observation_boundary"]["upper"],
        },
        "assembly_policy": intent_payload["assembly_policy"],
        "created_at": created_at,
        "capture_set_hash": exact_hash,
        "observation_set_hash": semantic_hash,
        "captures": capture_refs,
        "observation_capture_provenance": {
            key: sorted(value, key=lambda item: (item["page_ordinal"], item["record_locator"]))
            for key, value in sorted(provenance.items())
        },
        "bounded_material": {
            "bounded_material_id": bounded_material.payload["bounded_material_id"],
            "bounded_material_hash": bounded_material.payload["artifact_hash"],
            "file_sha256": sha256_bytes(bounded_bytes),
            "path": _relative(source_root, bounded_material.path),
        },
        "counts": counts,
        "terminal": bool(last_capture["terminal"]),
        "terminal_continuation": last_capture["next_continuation"],
        "terminal_evidence": {
            "capture_id": last_capture["capture_id"],
            "capture_hash": last_capture["artifact_hash"],
            "page_ordinal": last_capture["page_ordinal"],
            "terminal": bool(last_capture["terminal"]),
            "continuation_hash": sha256_canonical(last_capture["next_continuation"]),
        },
        "checkpoint_status": "uncommitted_acquisition_boundary",
    }
    boundary_id = derive_id("oab", BOUNDARY_SCHEMA, material)
    payload = _artifact({**material, "boundary_id": boundary_id}, artifact_id=boundary_id)
    return write_immutable_json(session_root / "03_boundary/acquisition_boundary.json", payload)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OperationalArtifactError(f"{label}_object_required")
    return value


def _require_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields.difference(value))
    if missing:
        raise OperationalArtifactError(f"{label}_required_field_missing:{missing[0]}")


def _verify_policy(value: Any, label: str) -> dict[str, Any]:
    policy = _require_mapping(value, label)
    _require_fields(policy, {"policy_id", "version", "file_sha256"}, label)
    require_text(str(policy["policy_id"]), f"{label}_id")
    require_text(str(policy["version"]), f"{label}_version")
    require_sha256(str(policy["file_sha256"]), f"{label}_file")
    return policy


def _verify_derived_artifact_identity(
    payload: dict[str, Any], *, schema: str, id_field: str, prefix: str
) -> None:
    if payload.get("schema_version") != schema:
        raise OperationalArtifactError(f"{id_field}_schema_invalid")
    if payload.get("artifact_id") != payload.get(id_field):
        raise OperationalArtifactError(f"{id_field}_artifact_identity_mismatch")
    material = dict(payload)
    material.pop("artifact_hash", None)
    material.pop("artifact_id", None)
    actual_id = material.pop(id_field, None)
    expected_id = derive_id(prefix, schema, material)
    if actual_id != expected_id:
        raise OperationalArtifactError(f"{id_field}_derivation_mismatch")


def verify_assembly_evidence(
    source_root: Path,
    *,
    boundary: PersistedArtifact,
    bounded_material: PersistedArtifact,
) -> dict[str, Any]:
    """Reopen and transitively verify exact capture provenance and semantic assembly."""

    boundary_data = load_artifact(boundary.path)
    bounded_data = load_artifact(bounded_material.path)
    if boundary_data != thaw_json(boundary.payload):
        raise OperationalArtifactError("acquisition_boundary_reference_mismatch")
    if bounded_data != thaw_json(bounded_material.payload):
        raise OperationalArtifactError("bounded_material_reference_mismatch")
    _require_fields(
        boundary_data,
        {
            "source",
            "adapter",
            "acquisition_cycle_id",
            "prior_checkpoint",
            "observation_boundary",
            "coverage",
            "assembly_policy",
            "capture_set_hash",
            "observation_set_hash",
            "captures",
            "observation_capture_provenance",
            "bounded_material",
            "counts",
            "terminal",
            "terminal_continuation",
            "terminal_evidence",
        },
        "acquisition_boundary",
    )
    _require_fields(
        bounded_data,
        {
            "source",
            "adapter",
            "assembly_policy",
            "observation_boundary",
            "observation_set_hash",
            "observations",
            "observation_count",
            "semantic_counts",
        },
        "bounded_material",
    )
    if bounded_data.get("schema_version") != BOUNDED_MATERIAL_SCHEMA:
        raise OperationalArtifactError("bounded_material_schema_invalid")
    if bounded_data.get("artifact_id") != bounded_data.get("bounded_material_id"):
        raise OperationalArtifactError("bounded_material_artifact_identity_mismatch")
    expected_bounded_id = derive_id(
        "obm",
        BOUNDED_MATERIAL_SCHEMA,
        bounded_data["source"],
        bounded_data["adapter"],
        bounded_data["assembly_policy"],
        bounded_data["observation_boundary"],
        bounded_data["observation_set_hash"],
        bounded_data["semantic_counts"],
    )
    if bounded_data.get("bounded_material_id") != expected_bounded_id:
        raise OperationalArtifactError("bounded_material_id_derivation_mismatch")
    if boundary_data["source"] != bounded_data["source"]:
        raise OperationalArtifactError("assembly_source_identity_mismatch")
    if boundary_data["adapter"] != bounded_data["adapter"]:
        raise OperationalArtifactError("assembly_adapter_identity_mismatch")
    boundary_policy = _verify_policy(boundary_data["assembly_policy"], "assembly_policy")
    bounded_policy = _verify_policy(bounded_data["assembly_policy"], "bounded_assembly_policy")
    if boundary_policy != bounded_policy:
        raise OperationalArtifactError("assembly_policy_mismatch")
    observation_boundary = _require_mapping(
        boundary_data["observation_boundary"], "observation_boundary"
    )
    if set(observation_boundary) != {"kind", "lower", "upper"}:
        raise OperationalArtifactError("observation_boundary_contract_invalid")
    if observation_boundary != bounded_data["observation_boundary"]:
        raise OperationalArtifactError("observation_boundary_mismatch")
    coverage = _require_mapping(boundary_data["coverage"], "coverage")
    expected_coverage = {
        "kind": observation_boundary["kind"],
        "lower_observation_boundary": observation_boundary["lower"],
        "upper_observation_boundary": observation_boundary["upper"],
    }
    if coverage != expected_coverage:
        raise OperationalArtifactError("observation_coverage_mismatch")

    observations = bounded_data["observations"]
    if not isinstance(observations, list):
        raise OperationalArtifactError("bounded_observations_array_required")
    semantic_hash = observation_set_hash(observations)
    if semantic_hash != bounded_data["observation_set_hash"]:
        raise OperationalArtifactError("bounded_observation_set_hash_mismatch")
    if semantic_hash != boundary_data["observation_set_hash"]:
        raise OperationalArtifactError("boundary_observation_set_hash_mismatch")
    expected_semantic_counts = semantic_observation_counts(observations)
    if bounded_data["semantic_counts"] != expected_semantic_counts:
        raise OperationalArtifactError("bounded_semantic_counts_mismatch")
    if bounded_data["observation_count"] != len(observations):
        raise OperationalArtifactError("bounded_observation_count_mismatch")

    bounded_ref = _require_mapping(boundary_data["bounded_material"], "bounded_material_ref")
    _require_fields(
        bounded_ref,
        {"bounded_material_id", "bounded_material_hash", "file_sha256", "path"},
        "bounded_material_ref",
    )
    expected_bounded_path = safe_artifact_path(source_root, str(bounded_ref["path"]))
    if expected_bounded_path != bounded_material.path.resolve(strict=True):
        raise OperationalArtifactError("bounded_material_path_mismatch")
    bounded_file_sha256 = sha256_bytes(expected_bounded_path.read_bytes())
    if bounded_ref != {
        "bounded_material_id": bounded_data["bounded_material_id"],
        "bounded_material_hash": bounded_data["artifact_hash"],
        "file_sha256": bounded_file_sha256,
        "path": str(bounded_ref["path"]),
    }:
        raise OperationalArtifactError("bounded_material_descriptor_mismatch")

    capture_refs = boundary_data["captures"]
    if not isinstance(capture_refs, list) or not capture_refs:
        raise OperationalArtifactError("boundary_capture_references_required")
    captures: list[PersistedArtifact] = []
    previous: dict[str, Any] | None = None
    captured_observations: dict[str, list[dict[str, Any]]] = {}
    expected_provenance: dict[str, list[dict[str, Any]]] = {}
    for expected_ordinal, reference_value in enumerate(capture_refs, start=1):
        reference = _require_mapping(reference_value, "capture_reference")
        _require_fields(
            reference,
            {"capture_id", "capture_hash", "path", "page_ordinal"},
            "capture_reference",
        )
        if reference["page_ordinal"] != expected_ordinal:
            raise OperationalArtifactError("capture_reference_order_invalid")
        capture_path = safe_artifact_path(source_root, str(reference["path"]))
        capture_data = load_artifact(capture_path)
        _verify_derived_artifact_identity(
            capture_data,
            schema=CAPTURE_SCHEMA,
            id_field="capture_id",
            prefix="opc",
        )
        if reference != {
            "capture_id": capture_data["capture_id"],
            "capture_hash": capture_data["artifact_hash"],
            "path": str(reference["path"]),
            "page_ordinal": capture_data["page_ordinal"],
        }:
            raise OperationalArtifactError("capture_reference_mismatch")
        if capture_data.get("session_id") != boundary_data.get("session_id"):
            raise OperationalArtifactError("capture_session_mismatch")
        if capture_data.get("previous_capture") != previous:
            raise OperationalArtifactError("capture_chain_link_mismatch")
        require_text(str(capture_data.get("response_schema") or ""), "capture_response_schema")
        require_sha256(str(capture_data.get("request_fingerprint") or ""), "capture_request")
        require_sha256(str(capture_data.get("continuation_hash") or ""), "capture_continuation")
        attempt_ref = _require_mapping(capture_data.get("attempt"), "capture_attempt")
        _require_fields(attempt_ref, {"attempt_id", "attempt_hash", "path"}, "capture_attempt")
        session_root = capture_path.parent.parent
        attempt_path = safe_artifact_path(session_root, str(attempt_ref["path"]))
        attempt_data = load_artifact(attempt_path)
        if attempt_ref["attempt_id"] != attempt_data.get("attempt_id"):
            raise OperationalArtifactError("capture_attempt_id_mismatch")
        if attempt_ref["attempt_hash"] != attempt_data.get("artifact_hash"):
            raise OperationalArtifactError("capture_attempt_hash_mismatch")
        if attempt_data.get("outcome") != "success":
            raise OperationalArtifactError("capture_attempt_success_required")
        if attempt_data.get("request_fingerprint") != capture_data["request_fingerprint"]:
            raise OperationalArtifactError("capture_attempt_request_mismatch")
        if attempt_data.get("continuation_hash") != capture_data["continuation_hash"]:
            raise OperationalArtifactError("capture_attempt_continuation_mismatch")
        body_ref = _require_mapping(capture_data.get("response_body"), "capture_body")
        _require_fields(body_ref, {"body_id", "body_sha256", "byte_size", "path"}, "capture_body")
        body_path = safe_artifact_path(session_root, str(body_ref["path"]))
        body_bytes = body_path.read_bytes()
        body_sha256 = sha256_bytes(body_bytes)
        if body_ref["body_sha256"] != body_sha256:
            raise OperationalArtifactError("capture_body_hash_mismatch")
        if body_ref["byte_size"] != len(body_bytes):
            raise OperationalArtifactError("capture_body_size_mismatch")
        if body_ref["body_id"] != derive_id("ocb", body_sha256):
            raise OperationalArtifactError("capture_body_identity_mismatch")
        for locator, observation_ref in enumerate(capture_data.get("observations", []), start=1):
            reference_observation = _require_mapping(observation_ref, "capture_observation")
            observation_id = str(reference_observation.get("observation_id"))
            captured_observations.setdefault(observation_id, []).append(reference_observation)
            expected_provenance.setdefault(observation_id, []).append(
                {
                    "capture_id": capture_data["capture_id"],
                    "page_ordinal": capture_data["page_ordinal"],
                    "record_locator": locator,
                }
            )
        capture_artifact = PersistedArtifact(
            path=capture_path, payload=capture_data, idempotent_replay=True
        )
        captures.append(capture_artifact)
        previous = {
            "capture_id": capture_data["capture_id"],
            "capture_hash": capture_data["artifact_hash"],
            "page_ordinal": capture_data["page_ordinal"],
        }

    exact_hash = capture_set_hash(captures)
    if exact_hash != boundary_data["capture_set_hash"]:
        raise OperationalArtifactError("boundary_capture_set_hash_mismatch")
    final_capture = thaw_json(captures[-1].payload)
    if boundary_data["terminal"] is not True or final_capture.get("terminal") is not True:
        raise OperationalArtifactError("boundary_terminal_evidence_required")
    if any(capture.payload["terminal"] for capture in captures[:-1]):
        raise OperationalArtifactError("boundary_terminal_capture_order_invalid")
    terminal_evidence = {
        "capture_id": final_capture["capture_id"],
        "capture_hash": final_capture["artifact_hash"],
        "page_ordinal": final_capture["page_ordinal"],
        "terminal": True,
        "continuation_hash": sha256_canonical(final_capture["next_continuation"]),
    }
    if boundary_data["terminal_evidence"] != terminal_evidence:
        raise OperationalArtifactError("boundary_terminal_evidence_mismatch")
    if boundary_data["terminal_continuation"] != final_capture["next_continuation"]:
        raise OperationalArtifactError("boundary_terminal_continuation_mismatch")

    bounded_by_id = {str(item["observation_id"]): item for item in observations}
    if set(captured_observations) != set(bounded_by_id):
        raise OperationalArtifactError("capture_observation_membership_mismatch")
    provenance = _require_mapping(
        boundary_data["observation_capture_provenance"], "observation_capture_provenance"
    )
    if set(provenance) != set(bounded_by_id):
        raise OperationalArtifactError("observation_capture_provenance_incomplete")
    if provenance != {
        key: sorted(value, key=lambda item: (item["page_ordinal"], item["record_locator"]))
        for key, value in sorted(expected_provenance.items())
    }:
        raise OperationalArtifactError("observation_capture_provenance_mismatch")
    for observation_id, observation in bounded_by_id.items():
        for reference_observation in captured_observations[observation_id]:
            expected_reference = {
                "observation_id": observation_id,
                "protected_source_record_id": observation["protected_source_record_id"],
                "content_hash": observation["content_hash"],
                "record_type": observation["record_type"],
            }
            if reference_observation != expected_reference:
                raise OperationalArtifactError("capture_observation_reference_mismatch")

    captured_record_count = sum(len(capture.payload["observations"]) for capture in captures)
    expected_counts = {
        "captured_record_count": captured_record_count,
        **expected_semantic_counts,
        "duplicate_observation_count": captured_record_count - len(observations),
    }
    if boundary_data["counts"] != expected_counts:
        raise OperationalArtifactError("acquisition_boundary_counts_mismatch")

    _verify_derived_artifact_identity(
        boundary_data,
        schema=BOUNDARY_SCHEMA,
        id_field="boundary_id",
        prefix="oab",
    )
    return {
        "boundary": boundary_data,
        "bounded_material": bounded_data,
        "bounded_material_file_sha256": bounded_file_sha256,
        "captures": tuple(captures),
        "counts": expected_counts,
    }


def persist_observation_index(
    source_root: Path,
    *,
    source: dict[str, Any],
    bounded_material: PersistedArtifact,
    boundary: PersistedArtifact,
    prior_index_ref: dict[str, Any] | None,
) -> PersistedArtifact:
    provenance = boundary.payload["observation_capture_provenance"]
    entries = []
    for observation in bounded_material.payload["observations"]:
        entries.append(
            {
                "observation_id": observation["observation_id"],
                "protected_source_record_id": observation["protected_source_record_id"],
                "content_hash": observation["content_hash"],
                "record_type": observation["record_type"],
                "capture_provenance": thaw_json(provenance[observation["observation_id"]]),
            }
        )
    material = {
        "schema_version": OBSERVATION_INDEX_SCHEMA,
        "source": source,
        "observation_set_hash": bounded_material.payload["observation_set_hash"],
        "bounded_material": {
            "bounded_material_id": bounded_material.payload["bounded_material_id"],
            "bounded_material_hash": bounded_material.payload["artifact_hash"],
        },
        "capture_set_hash": boundary.payload["capture_set_hash"],
        "prior_observation_index": prior_index_ref,
        "entries": entries,
        "entry_count": len(entries),
        "mutable_current_state": False,
        "compaction_performed": False,
    }
    index_id = derive_id("oix", OBSERVATION_INDEX_SCHEMA, material)
    payload = _artifact({**material, "observation_index_id": index_id}, artifact_id=index_id)
    return write_immutable_json(
        source_root / f"observation_indexes/{index_id}.observation-index.json",
        payload,
    )


def persist_failure(
    session_root: Path,
    *,
    session_id: str,
    failed_stage: str,
    failed_at: str,
    error_class: str,
    error_code: str,
    last_valid_artifacts: Iterable[PersistedArtifact],
) -> PersistedArtifact:
    material = {
        "schema_version": FAILURE_SCHEMA,
        "session_id": session_id,
        "failed_stage": failed_stage,
        "failed_at": failed_at,
        "error_class": error_class,
        "error_code": error_code,
        "error_detail_persisted": False,
        "secret_material_persisted": False,
        "retry_disposition": "resolve_from_last_committed_checkpoint",
        "last_valid_artifacts": [
            {
                "artifact_id": item.payload["artifact_id"],
                "artifact_hash": item.payload["artifact_hash"],
                "path": item.path.relative_to(session_root).as_posix()
                if session_root in item.path.parents
                else item.path.name,
            }
            for item in last_valid_artifacts
        ],
    }
    failure_id = derive_id("ofr", FAILURE_SCHEMA, material)
    payload = _artifact({**material, "failure_id": failure_id}, artifact_id=failure_id)
    return write_immutable_json(
        session_root / f"05_failures/{failure_id}.failure.json",
        payload,
    )
