from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from signal_agent.evidence_sources.canonical import canonical_json_bytes
from signal_agent.transport.schemas import derive_id

from .artifacts import (
    artifact_descriptor,
    build_reconciliation_manifest,
    seal,
    write_exclusive_bytes,
    write_exclusive_json,
)
from .candidates import CANDIDATE_SCHEMA_VERSION, EVIDENCE_BUNDLE_SCHEMA_VERSION
from .decisions import DECISION_SCHEMA_VERSION
from .errors import IdentityArtifactCollisionError, IdentityProjectionError
from .inputs import load_hashed_artifact, verify_identity_reference_against_run
from .models import Clock, ProjectionResult, ProjectionStatusResult


PROJECTION_SCHEMA_VERSION = "signal_agent.reconciled_identity_projection.v1"
PROJECTION_STATUS_SCHEMA_VERSION = "signal_agent.projection_status_receipt.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise IdentityProjectionError("identity_projection_timestamp_offset_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IdentityProjectionError(
            "identity_projection_timestamp_offset_required"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentityProjectionError("identity_projection_timestamp_offset_required")
    return value


def _load_candidate_bundle_decision(
    candidate_path: str | Path,
    evidence_bundle_path: str | Path,
    decision_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidate = load_hashed_artifact(
        candidate_path,
        schema_version=CANDIDATE_SCHEMA_VERSION,
        hash_field="candidate_hash",
        label="identity_candidate",
    )
    bundle = load_hashed_artifact(
        evidence_bundle_path,
        schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
        hash_field="bundle_hash",
        label="identity_evidence_bundle",
    )
    decision = load_hashed_artifact(
        decision_path,
        schema_version=DECISION_SCHEMA_VERSION,
        hash_field="receipt_hash",
        label="identity_decision_receipt",
    )
    if (
        candidate.get("evidence_bundle", {}).get("evidence_bundle_id")
        != bundle.get("evidence_bundle_id")
        or candidate.get("evidence_bundle", {}).get("bundle_hash")
        != bundle.get("bundle_hash")
        or decision.get("candidate", {}).get("candidate_id")
        != candidate.get("candidate_id")
        or decision.get("candidate", {}).get("candidate_hash")
        != candidate.get("candidate_hash")
        or decision.get("evidence_bundle", {}).get("evidence_bundle_id")
        != bundle.get("evidence_bundle_id")
        or decision.get("evidence_bundle", {}).get("bundle_hash")
        != bundle.get("bundle_hash")
        or candidate.get("left_identity_reference")
        != bundle.get("left_identity_reference")
        or candidate.get("right_identity_reference")
        != bundle.get("right_identity_reference")
    ):
        raise IdentityProjectionError("identity_projection_artifact_chain_mismatch")
    return candidate, bundle, decision


def _revalidate_sources(
    candidate: dict[str, Any],
    source_run_roots: Mapping[str, str | Path] | None,
) -> None:
    if source_run_roots is None:
        raise IdentityProjectionError("identity_projection_source_revalidation_required")
    for side in ("left_identity_reference", "right_identity_reference"):
        reference = candidate[side]
        source_type = reference["source_type"]
        if source_type not in source_run_roots:
            raise IdentityProjectionError(
                f"identity_projection_source_run_root_missing:{source_type}"
            )
        verify_identity_reference_against_run(reference, source_run_roots[source_type])


def _ensure_current_decision(decision_path: str | Path, decision: dict[str, Any]) -> None:
    successor = Path(decision_path).parent / f"from-{decision['decision_id']}.decision.json"
    if successor.exists():
        raise IdentityProjectionError("identity_projection_decision_superseded")


def _verify_prior_projection_inactive(
    prior_projection: dict[str, Any],
    reapproval_decision: dict[str, Any],
    projection_root: str | Path,
) -> None:
    predecessor = reapproval_decision.get("prior_decision_receipt") or {}
    if not predecessor:
        raise IdentityProjectionError(
            "identity_projection_reapproval_predecessor_required"
        )
    status_root = (
        Path(projection_root).expanduser().resolve(strict=False)
        / "04_projections"
        / prior_projection["projection_lineage_id"]
        / "status"
    )
    matches: list[dict[str, Any]] = []
    if status_root.is_dir():
        for path in sorted(status_root.glob("*.json")):
            receipt = load_hashed_artifact(
                path,
                schema_version=PROJECTION_STATUS_SCHEMA_VERSION,
                hash_field="receipt_hash",
                label="projection_status_receipt",
            )
            if (
                receipt.get("projection", {}).get("projection_id")
                == prior_projection.get("projection_id")
                and receipt.get("projection", {}).get("projection_hash")
                == prior_projection.get("projection_hash")
                and receipt.get("superseding_decision_receipt") == predecessor
            ):
                matches.append(receipt)
    if len(matches) != 1 or matches[0].get("effective_status") not in {
        "withdrawn",
        "review_required",
    }:
        raise IdentityProjectionError(
            "identity_prior_projection_inactive_status_required"
        )


def _write_operation(
    *,
    projection_root: str | Path,
    artifact_relative_path: str,
    artifact: dict[str, Any],
    artifact_schema_version: str,
    operation: str,
    created_at: str,
    identity_parts: tuple[object, ...],
    inputs: dict[str, Any],
    counts: dict[str, int],
) -> tuple[Path, Path]:
    root = Path(projection_root).expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(artifact)
    artifact_path = root / artifact_relative_path
    write_exclusive_bytes(artifact_path, payload)
    manifest = build_reconciliation_manifest(
        operation=operation,
        created_at=created_at,
        identity_parts=identity_parts,
        inputs=inputs,
        artifacts=[
            artifact_descriptor(
                artifact_relative_path,
                payload,
                schema_version=artifact_schema_version,
            )
        ],
        counts=counts,
    )
    manifest_path = root / "05_receipts" / "reconciliation_manifests" / (
        f"{manifest['manifest_id']}.json"
    )
    write_exclusive_json(manifest_path, manifest)
    return artifact_path, manifest_path


def build_reconciled_identity_projection(
    candidate_path: str | Path,
    evidence_bundle_path: str | Path,
    decision_path: str | Path,
    projection_root: str | Path,
    prior_projection_path: str | Path | None = None,
    clock: Clock = _utc_now,
    *,
    source_run_roots: Mapping[str, str | Path] | None = None,
) -> ProjectionResult:
    candidate, bundle, decision = _load_candidate_bundle_decision(
        candidate_path, evidence_bundle_path, decision_path
    )
    if decision.get("decision") != "approved" or not decision.get(
        "projection_authorized"
    ):
        raise IdentityProjectionError("identity_projection_valid_approval_required")
    if candidate.get("status") == "conflicting":
        raise IdentityProjectionError("identity_projection_conflicting_candidate_prohibited")
    _ensure_current_decision(decision_path, decision)
    _revalidate_sources(candidate, source_run_roots)
    prior_projection: dict[str, Any] | None = None
    if prior_projection_path is not None:
        resolved_prior_projection_path = (
            Path(prior_projection_path).expanduser().resolve(strict=True)
        )
        prior_projection = load_hashed_artifact(
            resolved_prior_projection_path,
            schema_version=PROJECTION_SCHEMA_VERSION,
            hash_field="projection_hash",
            label="reconciled_identity_projection",
        )
        if prior_projection.get("candidate", {}).get("candidate_id") != candidate.get(
            "candidate_id"
        ):
            raise IdentityProjectionError("identity_prior_projection_candidate_mismatch")
        expected_parent = (
            Path(projection_root).expanduser().resolve(strict=False)
            / "04_projections"
            / prior_projection["projection_lineage_id"]
        )
        if resolved_prior_projection_path.parent != expected_parent:
            raise IdentityProjectionError(
                "identity_prior_projection_outside_projection_store"
            )
        _verify_prior_projection_inactive(
            prior_projection, decision, projection_root
        )
    created_at = _require_timestamp(clock())
    lineage_id = (
        prior_projection["projection_lineage_id"]
        if prior_projection
        else derive_id(
            "ril",
            candidate["candidate_id"],
            candidate["candidate_hash"],
            length=20,
        )
    )
    prior_reference = (
        {
            "projection_id": prior_projection["projection_id"],
            "projection_hash": prior_projection["projection_hash"],
        }
        if prior_projection
        else None
    )
    projection_id = derive_id(
        "rip",
        lineage_id,
        decision["decision_id"],
        decision["receipt_hash"],
        prior_reference,
        length=20,
    )
    projection = seal(
        {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_id": projection_id,
            "projection_lineage_id": lineage_id,
            "status": "active",
            "created_at": created_at,
            "candidate": {
                "candidate_id": candidate["candidate_id"],
                "candidate_hash": candidate["candidate_hash"],
            },
            "member_references": [
                candidate["left_identity_reference"],
                candidate["right_identity_reference"],
            ],
            "evidence_bundle": {
                "evidence_bundle_id": bundle["evidence_bundle_id"],
                "bundle_hash": bundle["bundle_hash"],
            },
            "approval_decision_receipt": {
                "decision_id": decision["decision_id"],
                "receipt_hash": decision["receipt_hash"],
            },
            "comparison_policy": candidate["comparison_policy"],
            "prior_projection": prior_reference,
            "assertion_scope": "authorized_reconciled_view_not_established_identity",
            "source_records_mutated": False,
        },
        "projection_hash",
    )
    relative = f"04_projections/{lineage_id}/{projection_id}.json"
    artifact_path, manifest_path = _write_operation(
        projection_root=projection_root,
        artifact_relative_path=relative,
        artifact=projection,
        artifact_schema_version=PROJECTION_SCHEMA_VERSION,
        operation="projection_created",
        created_at=created_at,
        identity_parts=(projection_id, decision["receipt_hash"]),
        inputs={
            "candidate": projection["candidate"],
            "evidence_bundle": projection["evidence_bundle"],
            "approval_decision_receipt": projection["approval_decision_receipt"],
        },
        counts={"active_projection_count": 1, "source_member_count": 2},
    )
    return ProjectionResult(
        success=True,
        projection_id=projection_id,
        projection_lineage_id=lineage_id,
        projection_path=artifact_path,
        manifest_path=manifest_path,
    )


def record_projection_status(
    projection_path: str | Path,
    superseding_decision_path: str | Path,
    projection_root: str | Path,
    clock: Clock = _utc_now,
) -> ProjectionStatusResult:
    resolved_projection_path = Path(projection_path).expanduser().resolve(strict=True)
    projection = load_hashed_artifact(
        resolved_projection_path,
        schema_version=PROJECTION_SCHEMA_VERSION,
        hash_field="projection_hash",
        label="reconciled_identity_projection",
    )
    expected_projection_parent = (
        Path(projection_root).expanduser().resolve(strict=False)
        / "04_projections"
        / projection["projection_lineage_id"]
    )
    if resolved_projection_path.parent != expected_projection_parent:
        raise IdentityProjectionError("projection_outside_projection_store")
    decision = load_hashed_artifact(
        superseding_decision_path,
        schema_version=DECISION_SCHEMA_VERSION,
        hash_field="receipt_hash",
        label="identity_decision_receipt",
    )
    prior_decision = decision.get("prior_decision_receipt") or {}
    if (
        decision.get("candidate") != projection.get("candidate")
        or prior_decision.get("decision_id")
        != projection.get("approval_decision_receipt", {}).get("decision_id")
        or prior_decision.get("receipt_hash")
        != projection.get("approval_decision_receipt", {}).get("receipt_hash")
    ):
        raise IdentityProjectionError("projection_status_superseding_decision_mismatch")
    statuses = {"rejected": "withdrawn", "deferred": "review_required"}
    if decision.get("decision") not in statuses:
        raise IdentityProjectionError("projection_status_reject_or_defer_required")
    created_at = _require_timestamp(clock())
    effective_status = statuses[decision["decision"]]
    status_receipt_id = derive_id(
        "ips",
        projection["projection_id"],
        projection["projection_hash"],
        decision["decision_id"],
        decision["receipt_hash"],
        effective_status,
        length=20,
    )
    status_receipt = seal(
        {
            "schema_version": PROJECTION_STATUS_SCHEMA_VERSION,
            "status_receipt_id": status_receipt_id,
            "projection": {
                "projection_id": projection["projection_id"],
                "projection_hash": projection["projection_hash"],
                "projection_lineage_id": projection["projection_lineage_id"],
            },
            "superseding_decision_receipt": {
                "decision_id": decision["decision_id"],
                "receipt_hash": decision["receipt_hash"],
            },
            "effective_status": effective_status,
            "created_at": created_at,
        },
        "receipt_hash",
    )
    relative = (
        f"04_projections/{projection['projection_lineage_id']}/status/"
        f"{status_receipt_id}.json"
    )
    receipt_path, manifest_path = _write_operation(
        projection_root=projection_root,
        artifact_relative_path=relative,
        artifact=status_receipt,
        artifact_schema_version=PROJECTION_STATUS_SCHEMA_VERSION,
        operation="projection_status_recorded",
        created_at=created_at,
        identity_parts=(status_receipt_id, decision["receipt_hash"]),
        inputs={
            "projection": status_receipt["projection"],
            "superseding_decision_receipt": status_receipt[
                "superseding_decision_receipt"
            ],
        },
        counts={"projection_status_receipt_count": 1},
    )
    return ProjectionStatusResult(
        success=True,
        status_receipt_id=status_receipt_id,
        effective_status=effective_status,
        status_receipt_path=receipt_path,
        manifest_path=manifest_path,
    )
