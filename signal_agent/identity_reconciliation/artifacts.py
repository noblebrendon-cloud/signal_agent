from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from signal_agent.evidence_sources.canonical import canonical_json, canonical_json_bytes, sha256_bytes
from signal_agent.transport.schemas import derive_id

from .errors import IdentityArtifactCollisionError, IdentityEvidenceError


RECONCILIATION_MANIFEST_SCHEMA_VERSION = "signal_agent.identity_reconciliation_manifest.v1"


def sealed_hash(payload: dict[str, Any], field: str) -> str:
    material = deepcopy(payload)
    material.pop(field, None)
    return "sha256:" + hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def seal(payload: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = deepcopy(payload)
    sealed[field] = sealed_hash(sealed, field)
    return sealed


def verify_sealed(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    return isinstance(value, str) and value == sealed_hash(payload, field)


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityEvidenceError(f"{label}_unreadable") from exc
    if not isinstance(value, dict):
        raise IdentityEvidenceError(f"{label}_object_required")
    return value


def safe_artifact_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise IdentityEvidenceError("identity_artifact_path_invalid")
    resolved_root = Path(root).expanduser().resolve(strict=True)
    resolved = (resolved_root / Path(*relative.parts)).resolve(strict=True)
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise IdentityEvidenceError("identity_artifact_path_escaped_root")
    if not resolved.is_file():
        raise IdentityEvidenceError("identity_artifact_regular_file_required")
    return resolved


def prepare_empty_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve(strict=False)
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise IdentityArtifactCollisionError("identity_generation_root_must_be_empty")
    else:
        root.mkdir(parents=True, exist_ok=False)
    return root


def write_exclusive_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise OSError("identity_artifact_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise IdentityArtifactCollisionError(f"identity_artifact_exists:{path.name}") from exc
    return path


def write_exclusive_json(path: Path, payload: dict[str, Any]) -> Path:
    return write_exclusive_bytes(path, canonical_json_bytes(payload))


def promote_artifacts(root: Path, artifacts: Iterable[tuple[str, bytes]]) -> None:
    staged = list(artifacts)
    staging = root / ".staging"
    for relative_path, payload in staged:
        write_exclusive_bytes(staging / relative_path, payload)
    for relative_path, _payload in staged:
        source = staging / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    destination_handle.write(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        except FileExistsError as exc:
            raise IdentityArtifactCollisionError(
                f"identity_artifact_destination_exists:{relative_path}"
            ) from exc
        source.unlink()
    for directory in sorted(
        (item for item in staging.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        directory.rmdir()
    staging.rmdir()


def artifact_descriptor(
    relative_path: str,
    payload: bytes,
    *,
    schema_version: str,
    record_count: int = 1,
) -> dict[str, Any]:
    return {
        "path": relative_path,
        "sha256": f"sha256:{sha256_bytes(payload)}",
        "media_type": "application/json",
        "schema_version": schema_version,
        "record_count": record_count,
    }


def build_reconciliation_manifest(
    *,
    operation: str,
    created_at: str,
    identity_parts: tuple[object, ...],
    inputs: dict[str, Any],
    artifacts: list[dict[str, Any]],
    counts: dict[str, int],
) -> dict[str, Any]:
    manifest = {
        "schema_version": RECONCILIATION_MANIFEST_SCHEMA_VERSION,
        "manifest_id": derive_id(
            "irm",
            RECONCILIATION_MANIFEST_SCHEMA_VERSION,
            operation,
            *identity_parts,
            length=20,
        ),
        "operation": operation,
        "created_at": created_at,
        "completion_state": "completed",
        "inputs": inputs,
        "artifacts": artifacts,
        "counts": counts,
        "safety_flags": {
            "automatic_identity_merge_performed": False,
            "authentication_performed": False,
            "clear_identifiers_read": False,
            "external_action_authorized": False,
            "network_authorized": False,
            "source_records_mutated": False,
        },
        "canonicalization": {
            "encoding": "UTF-8",
            "ensure_ascii": False,
            "object_keys": "sorted",
            "json_separators": [",", ":"],
            "json_final_newline_count": 1,
            "artifact_hash_boundary": "exact_persisted_bytes_including_final_newline",
            "manifest_hash_boundary": "canonical_manifest_content_excluding_only_manifest_hash_without_final_newline",
        },
    }
    return seal(manifest, "manifest_hash")
