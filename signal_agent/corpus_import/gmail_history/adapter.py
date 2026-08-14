from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from signal_agent.corpus_import.preservation import prepare_run_root, preserve_source_file
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
    canonical_json_bytes,
    derive_id,
    seal,
    sha256_bytes,
)
from signal_agent.operational_ingestion.models import PersistedArtifact
from signal_agent.operational_ingestion.secrets import assert_secret_free

from .models import (
    GMAIL_HISTORY_SOURCE_TYPE,
    GMAIL_SOURCE_RECEIPT_SCHEMA,
    GmailHistoryContractError,
    GmailHistoryPolicy,
    GmailProjectionResult,
    thaw,
)
from .projection import build_target_label_projection


RELATIONSHIP_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
MATCH_REPORT_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"
PRESERVED_FILENAME = "gmail_history_bounded_source.json"
HASH_RECORD_FILENAME = "gmail_history_bounded_source.sha256.txt"
PRESERVED_RELATIVE_PATH = f"00_original/{PRESERVED_FILENAME}"
SOURCE_RECEIPT_RELATIVE_PATH = "05_receipts/gmail_history_source_receipt.json"
PROJECTION_RELATIVE_PATH = "05_receipts/gmail_target_label_projection.json"


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise GmailHistoryContractError("gmail_projection_artifact_conflict")
        return
    try:
        with path.open("xb") as handle:
            if handle.write(payload) != len(payload):
                raise OSError("gmail_projection_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != payload:
            raise GmailHistoryContractError("gmail_projection_artifact_conflict")


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_source_root(source_path: Path) -> tuple[Path, Path]:
    try:
        session_root = source_path.parents[1]
        source_root = source_path.parents[3]
    except IndexError as exc:
        raise GmailHistoryContractError("gmail_bounded_source_layout_invalid") from exc
    boundary = session_root / "03_boundary/acquisition_boundary.json"
    if not boundary.is_file():
        raise GmailHistoryContractError("gmail_acquisition_boundary_missing")
    return source_root, boundary


def _operational_input(bounded: dict[str, Any]) -> dict[str, str]:
    return {
        "bounded_material_id": str(bounded["bounded_material_id"]),
        "bounded_material_hash": str(bounded["artifact_hash"]),
        "observation_set_hash": str(bounded["observation_set_hash"]),
    }


def _record(
    *,
    transition: dict[str, Any],
    source_sha256: str,
    receipt_id: str,
    record_number: int,
    policy: GmailHistoryPolicy,
) -> dict[str, Any]:
    transition_id = str(transition["transition_id"])
    transition_hash = str(transition["transition_hash"])
    provider = transition["provider_observation"]
    occurred_at = str(transition.get("occurred_at") or "")
    relationship_kind = str(transition["transition_kind"])
    evidence_ref = (
        f"gmail-history-source:sha256:{source_sha256}:"
        f"transition:{transition_id}"
    )
    identifiers = [
        {
            "kind": "gmail_message_id_hmac",
            "value": transition["message_id_hmac"],
            "key_id": policy.protection_key_id,
            "algorithm": "HMAC-SHA-256",
            "version": str(policy.payload["protection"]["version"]),
            "personal_data": True,
            "export_policy": "restricted_local_only",
        }
    ]
    if transition.get("sender_identity_hmac"):
        identifiers.append(
            {
                "kind": "gmail_from_header_hmac",
                "value": transition["sender_identity_hmac"],
                "key_id": policy.protection_key_id,
                "algorithm": "HMAC-SHA-256",
                "version": str(policy.payload["protection"]["version"]),
                "personal_data": True,
                "export_policy": "restricted_local_only",
            }
        )
    if transition.get("thread_id_hmac"):
        identifiers.append(
            {
                "kind": "gmail_thread_id_hmac",
                "value": transition["thread_id_hmac"],
                "key_id": policy.protection_key_id,
                "algorithm": "HMAC-SHA-256",
                "version": str(policy.payload["protection"]["version"]),
                "personal_data": True,
                "export_policy": "restricted_local_only",
            }
        )
    return {
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_record_id": derive_id(
            "rel",
            GMAIL_HISTORY_SOURCE_TYPE,
            source_sha256,
            transition_id,
            transition_hash,
        ),
        "source_provenance": {
            "source_type": GMAIL_HISTORY_SOURCE_TYPE,
            "source_sha256": f"sha256:{source_sha256}",
            "source_receipt_id": receipt_id,
            "record_number": record_number,
            "line_start": record_number,
            "line_end": record_number,
            "raw_row_sha256": transition_hash,
            "raw_line_sha256": transition_hash,
            "evidence_ref": evidence_ref,
            "provider_observation_id": provider["observation_id"],
            "provider_event_id": provider["provider_event_id"],
            "projection_transition_id": transition_id,
            "capture_provenance_resolution": "source_receipt_observation_map",
        },
        "person": {
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            "display_name": "",
        },
        "professional_context": {"company": "", "position": ""},
        "relationship": {
            "platform": "gmail_history_offline",
            "kind": relationship_kind,
            "prior_projection_state": transition["prior_state"],
            "resulting_projection_state": transition["resulting_state"],
            "occurred_at_raw": occurred_at,
            "occurred_at_utc": occurred_at,
            "occurred_at_state": "parsed" if occurred_at else "missing",
            "mailbox_deletion": relationship_kind
            == "mailbox_deleted_while_in_target_scope",
            "target_label_departure": relationship_kind == "left_target_label",
            "absence_inference_used": False,
        },
        "identifiers": identifiers,
        "deterministic_classification": {
            "source_platform": "gmail_history_offline",
            "source_format": GMAIL_HISTORY_SOURCE_TYPE,
            "relationship_kind": relationship_kind,
            "field_presence": {
                "display_name": False,
                "company": False,
                "position": False,
                "sender_identity_hmac": bool(transition.get("sender_identity_hmac")),
                "source_event_time": bool(occurred_at),
            },
            "timestamp_state": "parsed" if occurred_at else "missing",
            "capture_provenance_state": "receipt_resolved",
            "projection_policy": policy.projection_policy,
        },
        "data_quality_issues": [
            "clear_display_name_not_emitted",
            "professional_context_not_available",
            *(("source_event_time_missing",) if not occurred_at else ()),
        ],
        "privacy": {
            "contains_personal_data": True,
            "clear_email_retained": False,
            "clear_message_id_retained": False,
            "clear_thread_id_retained": False,
            "message_body_retained": False,
            "snippet_retained": False,
            "attachment_retained": False,
            "public_export_allowed": False,
            "synthetic_fixture_data": True,
        },
    }


def _unresolved_matches(
    *,
    records: tuple[dict[str, Any], ...],
    source_sha256: str,
    projection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": MATCH_REPORT_SCHEMA_VERSION,
        "state": "review_required",
        "source_sha256": f"sha256:{source_sha256}",
        "relationship_record_count": len(records),
        "source_parse_summary": {
            "provider_observation_count": len(
                projection.get("final_states", [])
            ),
            "projection_transition_count": len(projection["transitions"]),
            "unresolved_target_relevance_count": len(
                projection["unresolved_relevance"]
            ),
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
            "label_removal_as_mailbox_deletion",
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
    policy: GmailHistoryPolicy,
    projection: dict[str, Any],
) -> dict[str, Any]:
    receipt_id = derive_id(
        "ghsr",
        GMAIL_SOURCE_RECEIPT_SCHEMA,
        source_sha256,
        boundary["boundary_id"],
        projection["projection_hash"],
        created_at,
    )
    payload = {
        "schema_version": GMAIL_SOURCE_RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "created_at": created_at,
        "preservation_timestamp": created_at,
        "status": "completed",
        "operation": "preserve_gmail_history_bounded_source",
        "operational_input": _operational_input(bounded),
        "source_sha256": f"sha256:{source_sha256}",
        "source_byte_size": source_size,
        "preserved_source": {
            "path": PRESERVED_RELATIVE_PATH,
            "source_sha256": f"sha256:{source_sha256}",
            "byte_size": source_size,
        },
        "provider_observation_set_hash": bounded["observation_set_hash"],
        "target_label_projection": {
            "path": PROJECTION_RELATIVE_PATH,
            "projection_id": projection["projection_id"],
            "projection_hash": projection["projection_hash"],
            "target_label_projection_set_hash": projection[
                "target_label_projection_set_hash"
            ],
            "projection_policy": policy.projection_policy,
            "coverage_classification": projection["coverage_classification"],
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
        "identifier_protection": policy.protection,
        "source_records_mutated": False,
        "overwrite_policy": "refuse",
        "authorizations": {
            "authentication_allowed": False,
            "contact_allowed": False,
            "external_action_allowed": False,
            "gmail_write_allowed": False,
            "live_mailbox_access_allowed": False,
            "message_allowed": False,
            "network_allowed": False,
            "oauth_allowed": False,
            "publication_allowed": False,
            "routing_allowed": False,
            "upstream_write_allowed": False,
        },
    }
    assert_secret_free(payload, label="gmail_history_source_receipt")
    return seal(payload, "receipt_hash")


@dataclass(frozen=True)
class GmailHistoryPreparedEvidence:
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
    projection: dict[str, Any] = field(repr=False)
    records: tuple[dict[str, Any], ...] = field(repr=False)
    unresolved_matches: dict[str, Any] = field(repr=False)
    prior_projection_path: Path | None = field(repr=False)
    prior_projection_sha256: str | None = field(repr=False)


@dataclass(frozen=True)
class GmailHistoryEvidenceAdapter:
    policy: GmailHistoryPolicy
    prior_projection_path: Path | None = None
    source_type: str = GMAIL_HISTORY_SOURCE_TYPE

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> GmailHistoryPreparedEvidence:
        try:
            source_path = Path(source).resolve(strict=True)
        except OSError as exc:
            raise GmailHistoryContractError("gmail_bounded_source_unreadable") from exc
        if not source_path.is_file():
            raise GmailHistoryContractError("gmail_bounded_source_not_regular_file")
        repository = Path(repository_root).resolve(strict=True)
        source_root, boundary_path = _find_source_root(source_path)
        bounded = load_artifact(source_path)
        boundary = load_artifact(boundary_path)
        verify_assembly_evidence(
            source_root,
            boundary=PersistedArtifact(
                path=boundary_path, payload=boundary, idempotent_replay=True
            ),
            bounded_material=PersistedArtifact(
                path=source_path, payload=bounded, idempotent_replay=True
            ),
        )
        if bounded.get("source", {}).get("source_type") != self.source_type:
            raise GmailHistoryContractError("gmail_bounded_source_type_mismatch")
        observations = bounded.get("observations")
        if not isinstance(observations, list):
            raise GmailHistoryContractError("gmail_bounded_observations_invalid")
        if observation_set_hash(observations) != bounded.get("observation_set_hash"):
            raise GmailHistoryContractError("gmail_observation_set_hash_mismatch")
        prior_path = (
            None
            if self.prior_projection_path is None
            else Path(self.prior_projection_path).resolve(strict=True)
        )
        prior_sha = None if prior_path is None else sha256_bytes(prior_path.read_bytes())
        projection_result: GmailProjectionResult = build_target_label_projection(
            bounded_material=bounded,
            policy=self.policy,
            prior_projection_path=prior_path,
        )
        projection = thaw(projection_result.artifact)
        source_sha = _source_sha256(source_path)
        created_at = clock()
        receipt = _source_receipt(
            bounded=bounded,
            boundary=boundary,
            source_sha256=source_sha,
            source_size=source_path.stat().st_size,
            created_at=created_at,
            policy=self.policy,
            projection=projection,
        )
        records = tuple(
            _record(
                transition=dict(transition),
                source_sha256=source_sha,
                receipt_id=receipt["receipt_id"],
                record_number=index,
                policy=self.policy,
            )
            for index, transition in enumerate(projection_result.records, start=1)
        )
        for transition in projection_result.records:
            observation_id = transition["provider_observation"]["observation_id"]
            if observation_id not in boundary["observation_capture_provenance"]:
                raise GmailHistoryContractError(
                    "gmail_transition_capture_provenance_missing"
                )
        return GmailHistoryPreparedEvidence(
            source_path=source_path,
            source_stat=source_path.stat(),
            source_sha256=source_sha,
            source_size_bytes=source_path.stat().st_size,
            bounded_payload=bounded,
            boundary_payload=boundary,
            boundary_path=boundary_path,
            source_root=source_root,
            repository_root=repository,
            created_at=created_at,
            source_receipt=receipt,
            projection=projection,
            records=records,
            unresolved_matches=_unresolved_matches(
                records=records,
                source_sha256=source_sha,
                projection=projection,
            ),
            prior_projection_path=prior_path,
            prior_projection_sha256=prior_sha,
        )

    def validate(
        self,
        prepared: GmailHistoryPreparedEvidence,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> None:
        del clock
        if Path(repository_root).resolve(strict=True) != prepared.repository_root:
            raise GmailHistoryContractError("gmail_prepared_repository_mismatch")
        observed = prepared.source_path.stat()
        if (
            observed.st_size != prepared.source_stat.st_size
            or observed.st_mtime_ns != prepared.source_stat.st_mtime_ns
        ):
            raise GmailHistoryContractError("gmail_bounded_source_changed")
        if _source_sha256(prepared.source_path) != prepared.source_sha256:
            raise GmailHistoryContractError("gmail_bounded_source_hash_changed")
        if load_artifact(prepared.boundary_path) != prepared.boundary_payload:
            raise GmailHistoryContractError("gmail_acquisition_boundary_changed")
        if prepared.prior_projection_path is not None:
            if sha256_bytes(prepared.prior_projection_path.read_bytes()) != prepared.prior_projection_sha256:
                raise GmailHistoryContractError("gmail_prior_projection_changed")

    def preserve(
        self,
        prepared: GmailHistoryPreparedEvidence,
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
            raise GmailHistoryContractError("gmail_preserved_hash_mismatch")
        _write_exact(
            output_root / PROJECTION_RELATIVE_PATH,
            canonical_json_bytes(prepared.projection),
        )
        write_receipt_exclusive(
            output_root / SOURCE_RECEIPT_RELATIVE_PATH,
            prepared.source_receipt,
        )
        descriptor = SourceReceiptDescriptor(
            receipt_id=prepared.source_receipt["receipt_id"],
            receipt_hash=prepared.source_receipt["receipt_hash"],
            source_sha256=prepared.source_sha256,
            persisted_relative_path=SOURCE_RECEIPT_RELATIVE_PATH,
            schema_version=prepared.source_receipt["schema_version"],
            protection_metadata=(
                ("algorithm", self.policy.protection["algorithm"]),
                ("key_id", self.policy.protection["key_id"]),
                ("version", self.policy.protection["version"]),
            ),
        )
        return PreservedEvidence(
            source_sha256=prepared.source_sha256,
            preserved_relative_path=PRESERVED_RELATIVE_PATH,
            source_receipt=descriptor,
            provenance_metadata=(
                ("acquisition_boundary_id", prepared.boundary_payload["boundary_id"]),
                ("capture_set_hash", prepared.boundary_payload["capture_set_hash"]),
                ("observation_set_hash", prepared.bounded_payload["observation_set_hash"]),
                ("source_size_bytes", prepared.source_size_bytes),
                ("source_type", GMAIL_HISTORY_SOURCE_TYPE),
                (
                    "target_label_projection_set_hash",
                    prepared.projection["target_label_projection_set_hash"],
                ),
            ),
        )

    def normalize(
        self,
        prepared: GmailHistoryPreparedEvidence,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        if preserved.source_sha256 != prepared.source_sha256:
            raise GmailHistoryContractError("gmail_preserved_source_identity_mismatch")
        if preserved.source_receipt.receipt_id != prepared.source_receipt["receipt_id"]:
            raise GmailHistoryContractError("gmail_preserved_receipt_identity_mismatch")
        return NormalizedRelationshipBatch(
            preserved=preserved,
            records=prepared.records,
            unresolved_matches=prepared.unresolved_matches,
        )
