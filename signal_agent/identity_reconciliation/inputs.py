from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_agent.corpus_import.receipts import verify_receipt_hash
from signal_agent.evidence_sources.canonical import sha256_file

from .artifacts import load_json_object, safe_artifact_path, verify_sealed
from .errors import IdentityEvidenceError


RUN_MANIFEST_PATH = "05_receipts/run_manifest.json"
NORMALIZED_PATH = "01_normalized/relationship_records.jsonl"
UNRESOLVED_PATH = "02_analysis/unresolved_matches.json"
RUN_MANIFEST_SCHEMA_VERSION = "signal_agent.relationship_signal_run_manifest.v1"
RELATIONSHIP_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
UNRESOLVED_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"


@dataclass(frozen=True)
class VerifiedSourceRun:
    root: Path
    source_type: str
    source_sha256: str
    source_receipt_id: str
    source_receipt_hash: str
    run_id: str
    manifest_hash: str
    identifier_protection: dict[str, str]
    normalized_sha256: str
    unresolved_sha256: str
    records: tuple[dict[str, Any], ...]
    unresolved_matches: dict[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_sha256": self.source_sha256,
            "source_receipt_id": self.source_receipt_id,
            "source_receipt_hash": self.source_receipt_hash,
            "source_run_id": self.run_id,
            "source_run_manifest": {
                "path": RUN_MANIFEST_PATH,
                "manifest_hash": self.manifest_hash,
            },
            "normalized_artifact": {
                "path": NORMALIZED_PATH,
                "sha256": self.normalized_sha256,
            },
            "unresolved_artifact": {
                "path": UNRESOLVED_PATH,
                "sha256": self.unresolved_sha256,
            },
        }


def _artifact(manifest: dict[str, Any], relative_path: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("artifacts", []) if item.get("path") == relative_path]
    if len(matches) != 1:
        raise IdentityEvidenceError(f"source_run_artifact_reference_invalid:{relative_path}")
    return matches[0]


def _load_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise IdentityEvidenceError("source_run_normalized_artifact_unreadable") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise IdentityEvidenceError(
                f"source_run_normalized_blank_line:line:{line_number}"
            )
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IdentityEvidenceError(
                f"source_run_normalized_json_invalid:line:{line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise IdentityEvidenceError("source_run_normalized_record_object_required")
        if record.get("schema_version") != RELATIONSHIP_SCHEMA_VERSION:
            raise IdentityEvidenceError("source_run_relationship_schema_unsupported")
        records.append(record)
    if not records:
        raise IdentityEvidenceError("source_run_has_no_relationship_records")
    return tuple(records)


def load_verified_source_run(
    run_root: str | Path,
    *,
    expected_source_type: str,
) -> VerifiedSourceRun:
    root = Path(run_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise IdentityEvidenceError("source_run_root_directory_required")
    manifest_path = safe_artifact_path(root, RUN_MANIFEST_PATH)
    manifest = load_json_object(manifest_path, "source_run_manifest")
    if manifest.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise IdentityEvidenceError("source_run_manifest_schema_unsupported")
    if manifest.get("completion_state") != "completed" or not verify_sealed(
        manifest, "manifest_hash"
    ):
        raise IdentityEvidenceError("source_run_manifest_not_valid_completed")
    normalized_ref = _artifact(manifest, NORMALIZED_PATH)
    unresolved_ref = _artifact(manifest, UNRESOLVED_PATH)
    normalized_path = safe_artifact_path(root, NORMALIZED_PATH)
    unresolved_path = safe_artifact_path(root, UNRESOLVED_PATH)
    if normalized_ref.get("sha256") != f"sha256:{sha256_file(normalized_path)}":
        raise IdentityEvidenceError("source_run_normalized_sha256_mismatch")
    if unresolved_ref.get("sha256") != f"sha256:{sha256_file(unresolved_path)}":
        raise IdentityEvidenceError("source_run_unresolved_sha256_mismatch")
    unresolved = load_json_object(unresolved_path, "source_run_unresolved_matches")
    if unresolved.get("schema_version") != UNRESOLVED_SCHEMA_VERSION:
        raise IdentityEvidenceError("source_run_unresolved_schema_unsupported")
    records = _load_jsonl(normalized_path)
    source_types = {record.get("source_provenance", {}).get("source_type") for record in records}
    if source_types != {expected_source_type}:
        raise IdentityEvidenceError("source_run_source_type_mismatch")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise IdentityEvidenceError("source_run_manifest_source_required")
    identifier_protection = manifest.get("identifier_protection")
    if not isinstance(identifier_protection, dict) or any(
        not isinstance(identifier_protection.get(field), str)
        or not identifier_protection[field]
        for field in ("key_id", "algorithm", "version")
    ):
        raise IdentityEvidenceError("source_run_identifier_protection_invalid")
    receipt_path_value = source.get("source_receipt_path")
    if not isinstance(receipt_path_value, str):
        raise IdentityEvidenceError("source_run_receipt_path_required")
    receipt_path = safe_artifact_path(root, receipt_path_value)
    if source.get("source_receipt_file_sha256") != f"sha256:{sha256_file(receipt_path)}":
        raise IdentityEvidenceError("source_run_receipt_file_sha256_mismatch")
    receipt = load_json_object(receipt_path, "source_run_source_receipt")
    if not verify_receipt_hash(receipt):
        raise IdentityEvidenceError("source_run_source_receipt_hash_invalid")
    if (
        receipt.get("receipt_id") != source.get("source_receipt_id")
        or receipt.get("receipt_hash") != source.get("source_receipt_hash")
    ):
        raise IdentityEvidenceError("source_run_source_receipt_identity_mismatch")
    source_sha256 = str(source.get("source_sha256") or "")
    if any(
        record.get("source_provenance", {}).get("source_sha256") != source_sha256
        or record.get("source_provenance", {}).get("source_receipt_id")
        != source.get("source_receipt_id")
        for record in records
    ):
        raise IdentityEvidenceError("source_run_record_provenance_mismatch")
    return VerifiedSourceRun(
        root=root,
        source_type=expected_source_type,
        source_sha256=source_sha256,
        source_receipt_id=str(source["source_receipt_id"]),
        source_receipt_hash=str(source["source_receipt_hash"]),
        run_id=str(manifest["run_id"]),
        manifest_hash=str(manifest["manifest_hash"]),
        identifier_protection={
            field: str(identifier_protection[field])
            for field in ("key_id", "algorithm", "version")
        },
        normalized_sha256=str(normalized_ref["sha256"]),
        unresolved_sha256=str(unresolved_ref["sha256"]),
        records=records,
        unresolved_matches=unresolved,
    )


def verify_identity_reference_against_run(
    identity_reference: dict[str, Any],
    run_root: str | Path,
) -> VerifiedSourceRun:
    source_type = str(identity_reference.get("source_type") or "")
    run = load_verified_source_run(run_root, expected_source_type=source_type)
    expected = {
        "source_sha256": run.source_sha256,
        "source_receipt_id": run.source_receipt_id,
        "source_receipt_hash": run.source_receipt_hash,
        "source_run_id": run.run_id,
    }
    for field, value in expected.items():
        if identity_reference.get(field) != value:
            raise IdentityEvidenceError(f"identity_reference_{field}_mismatch")
    if identity_reference.get("source_run_manifest", {}).get("manifest_hash") != run.manifest_hash:
        raise IdentityEvidenceError("identity_reference_manifest_hash_mismatch")
    if identity_reference.get("normalized_artifact", {}).get("sha256") != run.normalized_sha256:
        raise IdentityEvidenceError("identity_reference_normalized_hash_mismatch")
    indexed = {record["relationship_record_id"]: record for record in run.records}
    record_ids = identity_reference.get("relationship_record_ids")
    evidence_refs = identity_reference.get("evidence_refs")
    if not isinstance(record_ids, list) or not record_ids or any(item not in indexed for item in record_ids):
        raise IdentityEvidenceError("identity_reference_record_missing")
    expected_refs = sorted(indexed[item]["source_provenance"]["evidence_ref"] for item in record_ids)
    if evidence_refs != expected_refs:
        raise IdentityEvidenceError("identity_reference_evidence_refs_mismatch")
    return run


def load_hashed_artifact(
    path: str | Path,
    *,
    schema_version: str,
    hash_field: str,
    label: str,
) -> dict[str, Any]:
    payload = load_json_object(path, label)
    if payload.get("schema_version") != schema_version:
        raise IdentityEvidenceError(f"{label}_schema_unsupported")
    if not verify_sealed(payload, hash_field):
        raise IdentityEvidenceError(f"{label}_hash_invalid")
    return payload
