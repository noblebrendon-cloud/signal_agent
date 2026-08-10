from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from signal_agent.corpus_import.preservation import (
    prepare_run_root,
    preserve_source_file,
)
from signal_agent.corpus_import.receipts import write_receipt_exclusive
from signal_agent.evidence_sources.contracts import Clock
from signal_agent.evidence_sources.models import (
    NormalizedRelationshipBatch,
    PreservedEvidence,
    SourceReceiptDescriptor,
)
from signal_agent.operational_ingestion.artifacts import (
    load_artifact,
    observation_set_hash,
    verify_assembly_evidence,
)
from signal_agent.operational_ingestion.canonical import (
    derive_id,
    seal,
    sha256_bytes,
)
from signal_agent.operational_ingestion.models import PersistedArtifact
from signal_agent.operational_ingestion.secrets import assert_secret_free


SIMULATED_OPERATIONAL_SOURCE_TYPE = "simulated_operational_relationship.v1"
RELATIONSHIP_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
MATCH_REPORT_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"
SOURCE_RECEIPT_SCHEMA_VERSION = "signal_agent.simulated_operational_source_receipt.v1"
PRESERVED_FILENAME = "simulated_operational_bounded_source.json"
HASH_RECORD_FILENAME = "simulated_operational_bounded_source.sha256.txt"
PRESERVED_RELATIVE_PATH = f"00_original/{PRESERVED_FILENAME}"
SOURCE_RECEIPT_RELATIVE_PATH = "05_receipts/simulated_operational_source_receipt.json"


class SimulatedOperationalImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class SimulatedOperationalPreparedEvidence:
    source_path: Path
    source_stat: os.stat_result = field(repr=False)
    source_sha256: str
    source_size_bytes: int
    bounded_payload: dict[str, Any] = field(repr=False)
    boundary_payload: dict[str, Any] = field(repr=False)
    boundary_path: Path
    source_root: Path
    repository_root: Path
    created_at: str
    source_receipt: dict[str, Any] = field(repr=False)
    records: tuple[dict[str, Any], ...] = field(repr=False)
    unresolved_matches: dict[str, Any] = field(repr=False)


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _operational_input(bounded: dict[str, Any]) -> dict[str, str]:
    return {
        "bounded_material_id": str(bounded["bounded_material_id"]),
        "bounded_material_hash": str(bounded["artifact_hash"]),
        "observation_set_hash": str(bounded["observation_set_hash"]),
    }


def _find_source_root(source_path: Path) -> tuple[Path, Path]:
    try:
        session_root = source_path.parents[1]
        source_root = source_path.parents[3]
    except IndexError as exc:
        raise SimulatedOperationalImportError(
            "simulated_operational_source_layout_invalid"
        ) from exc
    boundary = session_root / "03_boundary/acquisition_boundary.json"
    if not boundary.is_file():
        raise SimulatedOperationalImportError(
            "simulated_operational_boundary_missing"
        )
    return source_root, boundary


def _validate_protection(observations: list[dict[str, Any]]) -> dict[str, str]:
    descriptors = {
        (
            str(item.get("protection", {}).get("algorithm") or ""),
            str(item.get("protection", {}).get("key_id") or ""),
            str(item.get("protection", {}).get("version") or ""),
        )
        for item in observations
    }
    if len(descriptors) != 1:
        raise SimulatedOperationalImportError(
            "simulated_operational_protection_domain_incoherent"
        )
    algorithm, key_id, version = next(iter(descriptors))
    if not algorithm or not key_id or not version:
        raise SimulatedOperationalImportError(
            "simulated_operational_protection_descriptor_incomplete"
        )
    return {"algorithm": algorithm, "key_id": key_id, "version": version}


def _record(
    *,
    observation: dict[str, Any],
    source_sha256: str,
    receipt_id: str,
    record_number: int,
) -> dict[str, Any]:
    semantic = observation.get("semantic_payload")
    if not isinstance(semantic, dict):
        raise SimulatedOperationalImportError(
            "simulated_operational_semantic_payload_invalid"
        )
    observation_id = str(observation["observation_id"])
    protected_id = str(observation["protected_source_record_id"])
    state = str(observation.get("observation_state") or "")
    if state not in {"active", "tombstone"}:
        raise SimulatedOperationalImportError(
            "simulated_operational_observation_state_invalid"
        )
    protection = observation["protection"]
    content_hash = str(observation["content_hash"])
    record_id = derive_id(
        "rel",
        SIMULATED_OPERATIONAL_SOURCE_TYPE,
        source_sha256,
        observation_id,
        content_hash,
    )
    evidence_ref = (
        f"simulated-operational-source:sha256:{source_sha256}:"
        f"observation:{observation_id}"
    )
    display_name = str(semantic.get("display_name") or "")
    company = str(semantic.get("company") or "")
    position = str(semantic.get("position") or "")
    source_event_time = str(observation.get("source_event_time") or "")
    remote_modified_at = str(observation.get("remote_modified_at") or "")
    issues = []
    if not display_name:
        issues.append("display_name_missing")
    if not company:
        issues.append("company_missing")
    if not position:
        issues.append("position_missing")
    if state == "tombstone":
        issues.append("explicit_source_tombstone")
    if observation.get("ordering_state") == "ambiguous":
        issues.append("source_version_order_ambiguous")
    return {
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_record_id": record_id,
        "source_provenance": {
            "source_type": SIMULATED_OPERATIONAL_SOURCE_TYPE,
            "source_sha256": f"sha256:{source_sha256}",
            "source_receipt_id": receipt_id,
            "record_number": record_number,
            "line_start": record_number,
            "line_end": record_number,
            "raw_row_sha256": content_hash,
            "raw_line_sha256": content_hash,
            "evidence_ref": evidence_ref,
            "observation_id": observation_id,
            "capture_provenance_resolution": "source_receipt_observation_map",
        },
        "person": {
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            "display_name": display_name,
        },
        "professional_context": {
            "company": company,
            "position": position,
        },
        "relationship": {
            "platform": "simulated_operational_source",
            "kind": (
                "simulated_explicit_tombstone"
                if state == "tombstone"
                else "simulated_relationship_observation"
            ),
            "observation_state": state,
            "source_record_version": int(semantic["source_record_version"]),
            "occurred_at_raw": source_event_time,
            "occurred_at_utc": source_event_time,
            "occurred_at_state": "parsed",
            "remote_modified_at_raw": remote_modified_at,
            "remote_modified_at_utc": remote_modified_at,
            "remote_modified_at_state": "parsed",
            "supersedes_observation_id": observation.get(
                "supersedes_observation_id"
            ),
            "predecessor_content_hash": observation.get(
                "predecessor_content_hash"
            ),
            "ordering_state": observation.get("ordering_state"),
            "deletion_evidence_class": (
                "explicit_simulator_tombstone" if state == "tombstone" else None
            ),
        },
        "identifiers": [
            {
                "kind": "simulated_source_record_hmac",
                "value": protected_id,
                "key_id": str(protection["key_id"]),
                "algorithm": str(protection["algorithm"]),
                "version": str(protection["version"]),
                "personal_data": False,
                "export_policy": "restricted_local_only",
            },
            {
                "kind": "simulated_observation_id_sha256",
                "value": "sha256:"
                + hashlib.sha256(observation_id.encode("utf-8")).hexdigest(),
                "personal_data": False,
                "export_policy": "restricted_local_only",
            },
        ],
        "deterministic_classification": {
            "source_platform": "simulated_operational_source",
            "source_format": SIMULATED_OPERATIONAL_SOURCE_TYPE,
            "relationship_kind": (
                "explicit_tombstone"
                if state == "tombstone"
                else "relationship_observation"
            ),
            "observation_state": state,
            "field_presence": {
                "display_name": bool(display_name),
                "company": bool(company),
                "position": bool(position),
                "source_event_time": bool(source_event_time),
                "remote_modified_at": bool(remote_modified_at),
            },
            "timestamp_state": "parsed",
            "capture_provenance_state": "receipt_resolved",
        },
        "data_quality_issues": sorted(issues),
        "privacy": {
            "contains_personal_data": False,
            "clear_source_record_id_retained": False,
            "clear_fixture_label_retained": False,
            "public_export_allowed": False,
            "synthetic_fixture_data": True,
        },
    }


def _unresolved_matches(
    *, records: tuple[dict[str, Any], ...], source_sha256: str
) -> dict[str, Any]:
    return {
        "schema_version": MATCH_REPORT_SCHEMA_VERSION,
        "state": "review_required",
        "source_sha256": f"sha256:{source_sha256}",
        "relationship_record_count": len(records),
        "source_parse_summary": {
            "canonical_observation_count": len(records),
            "duplicate_normalized_effect_count": 0,
        },
        "candidate_group_count": 0,
        "records_in_candidate_groups": [],
        "unresolved_record_ids": sorted(
            item["relationship_record_id"] for item in records
        ),
        "candidate_groups": [],
        "excluded_match_methods": [
            "absence_as_deletion",
            "automatic_identity_reconciliation",
            "cross_source_matching",
            "transport_topology_identity",
        ],
        "automatic_merge_performed": False,
        "canonical_identity_selected": False,
    }


def _source_receipt(
    *,
    bounded: dict[str, Any],
    boundary: dict[str, Any],
    source_sha256: str,
    source_size: int,
    created_at: str,
    protection: dict[str, str],
) -> dict[str, Any]:
    receipt_id = derive_id(
        "sosr",
        SOURCE_RECEIPT_SCHEMA_VERSION,
        source_sha256,
        boundary["boundary_id"],
    )
    payload = {
        "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "created_at": created_at,
        "preservation_timestamp": created_at,
        "status": "completed",
        "operation": "preserve_simulated_operational_bounded_source",
        "operational_input": _operational_input(bounded),
        "source_sha256": f"sha256:{source_sha256}",
        "source_byte_size": source_size,
        "preserved_source": {
            "path": PRESERVED_RELATIVE_PATH,
            "source_sha256": f"sha256:{source_sha256}",
            "byte_size": source_size,
        },
        "source": {
            "source_type": SIMULATED_OPERATIONAL_SOURCE_TYPE,
            "source_version": "1.0.0",
            "sha256": f"sha256:{source_sha256}",
            "size_bytes": source_size,
            "observation_set_hash": bounded["observation_set_hash"],
            "observation_count": bounded["observation_count"],
            "capture_set_hash": boundary["capture_set_hash"],
            "acquisition_boundary_id": boundary["boundary_id"],
            "acquisition_boundary_hash": boundary["artifact_hash"],
            "preserved_path": PRESERVED_RELATIVE_PATH,
            "preserved_sha256": f"sha256:{source_sha256}",
            "original_preserved": True,
            "hash_verified": True,
            "byte_for_byte_equal": True,
        },
        "acquisition_provenance": {
            "boundary_id": boundary["boundary_id"],
            "boundary_hash": boundary["artifact_hash"],
            "capture_set_hash": boundary["capture_set_hash"],
            "observation_set_hash": boundary["observation_set_hash"],
            "observation_capture_provenance": boundary[
                "observation_capture_provenance"
            ],
        },
        "identifier_protection": protection,
        "source_records_mutated": False,
        "overwrite_policy": "refuse",
        "authorizations": {
            "authorization_scope": "none",
            "contact_allowed": False,
            "external_action_allowed": False,
            "message_allowed": False,
            "network_allowed": False,
            "publication_allowed": False,
            "routing_allowed": False,
            "upstream_write_allowed": False,
        },
    }
    assert_secret_free(payload, label="simulated_operational_source_receipt")
    return seal(payload, "receipt_hash")


@dataclass(frozen=True)
class SimulatedOperationalEvidenceAdapter:
    source_type: str = SIMULATED_OPERATIONAL_SOURCE_TYPE

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> SimulatedOperationalPreparedEvidence:
        try:
            source_path = Path(source).expanduser().resolve(strict=True)
        except OSError as exc:
            raise SimulatedOperationalImportError(
                "simulated_operational_source_unreadable"
            ) from exc
        if not source_path.is_file():
            raise SimulatedOperationalImportError(
                "simulated_operational_source_not_regular_file"
            )
        repository = Path(repository_root).expanduser().resolve(strict=True)
        source_root, boundary_path = _find_source_root(source_path)
        bounded = load_artifact(source_path)
        boundary = load_artifact(boundary_path)
        bounded_artifact = PersistedArtifact(
            path=source_path, payload=bounded, idempotent_replay=True
        )
        boundary_artifact = PersistedArtifact(
            path=boundary_path, payload=boundary, idempotent_replay=True
        )
        verify_assembly_evidence(
            source_root,
            boundary=boundary_artifact,
            bounded_material=bounded_artifact,
        )
        if bounded.get("source", {}).get("source_type") != self.source_type:
            raise SimulatedOperationalImportError(
                "simulated_operational_source_type_mismatch"
            )
        observations = bounded.get("observations")
        if not isinstance(observations, list) or not observations:
            raise SimulatedOperationalImportError(
                "simulated_operational_observations_required"
            )
        if observation_set_hash(observations) != bounded.get("observation_set_hash"):
            raise SimulatedOperationalImportError(
                "simulated_operational_observation_set_mismatch"
            )
        protection = _validate_protection(observations)
        source_sha256 = _source_sha256(source_path)
        created_at = clock()
        receipt = _source_receipt(
            bounded=bounded,
            boundary=boundary,
            source_sha256=source_sha256,
            source_size=source_path.stat().st_size,
            created_at=created_at,
            protection=protection,
        )
        records = tuple(
            _record(
                observation=item,
                source_sha256=source_sha256,
                receipt_id=receipt["receipt_id"],
                record_number=index,
            )
            for index, item in enumerate(observations, start=1)
        )
        for record in records:
            observation_id = record["source_provenance"]["observation_id"]
            if observation_id not in boundary["observation_capture_provenance"]:
                raise SimulatedOperationalImportError(
                    "simulated_operational_record_capture_provenance_missing"
                )
        return SimulatedOperationalPreparedEvidence(
            source_path=source_path,
            source_stat=source_path.stat(),
            source_sha256=source_sha256,
            source_size_bytes=source_path.stat().st_size,
            bounded_payload=bounded,
            boundary_payload=boundary,
            boundary_path=boundary_path,
            source_root=source_root,
            repository_root=repository,
            created_at=created_at,
            source_receipt=receipt,
            records=records,
            unresolved_matches=_unresolved_matches(
                records=records, source_sha256=source_sha256
            ),
        )

    def validate(
        self,
        prepared: SimulatedOperationalPreparedEvidence,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> None:
        del clock
        repository = Path(repository_root).expanduser().resolve(strict=True)
        if repository != prepared.repository_root:
            raise SimulatedOperationalImportError(
                "simulated_operational_prepared_repository_mismatch"
            )
        observed = prepared.source_path.stat()
        if (
            observed.st_size != prepared.source_stat.st_size
            or observed.st_mtime_ns != prepared.source_stat.st_mtime_ns
        ):
            raise SimulatedOperationalImportError(
                "simulated_operational_source_changed"
            )
        if _source_sha256(prepared.source_path) != prepared.source_sha256:
            raise SimulatedOperationalImportError(
                "simulated_operational_source_hash_changed"
            )
        boundary = load_artifact(prepared.boundary_path)
        if boundary != prepared.boundary_payload:
            raise SimulatedOperationalImportError(
                "simulated_operational_boundary_changed"
            )

    def preserve(
        self,
        prepared: SimulatedOperationalPreparedEvidence,
        run_root: Path,
    ) -> PreservedEvidence:
        output_root = prepare_run_root(Path(run_root))
        result = preserve_source_file(
            prepared.source_path,
            output_root,
            expected_sha256=prepared.source_sha256,
            expected_stat=prepared.source_stat,
            preserved_filename=PRESERVED_FILENAME,
            hash_record_filename=HASH_RECORD_FILENAME,
        )
        if result.preserved_sha256 != prepared.source_sha256:
            raise SimulatedOperationalImportError(
                "simulated_operational_preserved_hash_mismatch"
            )
        write_receipt_exclusive(
            output_root / SOURCE_RECEIPT_RELATIVE_PATH,
            prepared.source_receipt,
        )
        protection = prepared.source_receipt["identifier_protection"]
        descriptor = SourceReceiptDescriptor(
            receipt_id=prepared.source_receipt["receipt_id"],
            receipt_hash=prepared.source_receipt["receipt_hash"],
            source_sha256=prepared.source_sha256,
            persisted_relative_path=SOURCE_RECEIPT_RELATIVE_PATH,
            schema_version=prepared.source_receipt["schema_version"],
            protection_metadata=(
                ("algorithm", protection["algorithm"]),
                ("key_id", protection["key_id"]),
                ("version", protection["version"]),
            ),
        )
        return PreservedEvidence(
            source_sha256=prepared.source_sha256,
            preserved_relative_path=PRESERVED_RELATIVE_PATH,
            source_receipt=descriptor,
            provenance_metadata=(
                (
                    "acquisition_boundary_id",
                    prepared.boundary_payload["boundary_id"],
                ),
                ("capture_set_hash", prepared.boundary_payload["capture_set_hash"]),
                (
                    "observation_count",
                    int(prepared.bounded_payload["observation_count"]),
                ),
                (
                    "observation_set_hash",
                    prepared.bounded_payload["observation_set_hash"],
                ),
                ("source_size_bytes", prepared.source_size_bytes),
                ("source_type", SIMULATED_OPERATIONAL_SOURCE_TYPE),
            ),
        )

    def normalize(
        self,
        prepared: SimulatedOperationalPreparedEvidence,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        if preserved.source_sha256 != prepared.source_sha256:
            raise SimulatedOperationalImportError(
                "simulated_operational_preserved_source_identity_mismatch"
            )
        if (
            preserved.source_receipt.receipt_id
            != prepared.source_receipt["receipt_id"]
        ):
            raise SimulatedOperationalImportError(
                "simulated_operational_preserved_receipt_identity_mismatch"
            )
        return NormalizedRelationshipBatch(
            preserved=preserved,
            records=prepared.records,
            unresolved_matches=prepared.unresolved_matches,
        )
