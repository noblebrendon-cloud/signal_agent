from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from signal_agent.evidence_sources.canonical import canonical_json_bytes
from signal_agent.transport.schemas import derive_id

from .artifacts import write_exclusive_bytes
from .candidates import CANDIDATE_SCHEMA_VERSION, EVIDENCE_BUNDLE_SCHEMA_VERSION
from .errors import IdentityArtifactCollisionError, IdentityDecisionError
from .inputs import load_hashed_artifact, verify_identity_reference_against_run
from .models import (
    IdentityDecisionRationale,
    IdentityDecisionResult,
    IdentityReviewAuthority,
)
from .policy import (
    SUPPORTED_ATTESTATION_VERSION,
    SUPPORTED_AUTHORITY_TYPE,
    SUPPORTED_REVIEWER_ROLE,
)
from .artifacts import seal


DECISION_SCHEMA_VERSION = "signal_agent.identity_decision_receipt.v1"
DECISIONS = {"approved", "rejected", "deferred"}


def _offset_aware_rfc3339(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_authority(authority: IdentityReviewAuthority) -> dict[str, str]:
    payload = authority.to_dict()
    if payload["authority_type"] != SUPPORTED_AUTHORITY_TYPE:
        raise IdentityDecisionError("identity_review_authority_type_unsupported")
    if payload["attestation_version"] != SUPPORTED_ATTESTATION_VERSION:
        raise IdentityDecisionError("identity_review_attestation_version_unsupported")
    if payload["reviewer_role"] != SUPPORTED_REVIEWER_ROLE:
        raise IdentityDecisionError("identity_review_reviewer_role_unsupported")
    for field in ("reviewer_id", "reviewer_role", "authority_basis", "attested_at"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise IdentityDecisionError(f"identity_review_{field}_required")
    if not _offset_aware_rfc3339(payload["attested_at"]):
        raise IdentityDecisionError("identity_review_attested_at_offset_required")
    return {field: value.strip() for field, value in payload.items()}


def _load_decision(path: str | Path) -> dict[str, Any]:
    return load_hashed_artifact(
        path,
        schema_version=DECISION_SCHEMA_VERSION,
        hash_field="receipt_hash",
        label="identity_decision_receipt",
    )


def _validate_candidate_bundle(
    candidate: dict[str, Any], bundle: dict[str, Any]
) -> None:
    reference = candidate.get("evidence_bundle") or {}
    if (
        reference.get("evidence_bundle_id") != bundle.get("evidence_bundle_id")
        or reference.get("bundle_hash") != bundle.get("bundle_hash")
        or candidate.get("left_identity_reference") != bundle.get("left_identity_reference")
        or candidate.get("right_identity_reference") != bundle.get("right_identity_reference")
        or candidate.get("comparison_policy") != bundle.get("comparison_policy")
    ):
        raise IdentityDecisionError("identity_candidate_evidence_bundle_mismatch")


def _transition_allowed(origin: str, destination: str) -> bool:
    return destination in {
        "proposed": {"approved", "rejected", "deferred"},
        "conflicting": {"rejected", "deferred"},
        "approved": {"rejected", "deferred"},
        "rejected": {"approved", "deferred"},
        "deferred": {"approved", "rejected"},
    }.get(origin, set())


def record_identity_decision(
    candidate_path: str | Path,
    evidence_bundle_path: str | Path,
    decision_root: str | Path,
    authority: IdentityReviewAuthority,
    decision: str,
    rationale: IdentityDecisionRationale,
    prior_decision_path: str | Path | None = None,
    *,
    source_run_roots: Mapping[str, str | Path] | None = None,
) -> IdentityDecisionResult:
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
    _validate_candidate_bundle(candidate, bundle)
    if decision not in DECISIONS:
        raise IdentityDecisionError("identity_decision_unsupported")
    authority_payload = _validate_authority(authority)
    root = Path(decision_root).expanduser().resolve(strict=False)
    prior: dict[str, Any] | None = None
    if prior_decision_path is not None:
        resolved_prior_path = Path(prior_decision_path).expanduser().resolve(strict=True)
        expected_prior_parent = root / "03_review" / candidate["candidate_id"]
        if resolved_prior_path.parent != expected_prior_parent:
            raise IdentityDecisionError("identity_prior_decision_outside_review_store")
        prior = _load_decision(prior_decision_path)
        if (
            prior.get("candidate", {}).get("candidate_id") != candidate.get("candidate_id")
            or prior.get("candidate", {}).get("candidate_hash")
            != candidate.get("candidate_hash")
            or prior.get("evidence_bundle", {}).get("evidence_bundle_id")
            != bundle.get("evidence_bundle_id")
            or prior.get("evidence_bundle", {}).get("bundle_hash")
            != bundle.get("bundle_hash")
        ):
            raise IdentityDecisionError("identity_prior_decision_candidate_mismatch")
    origin = prior["decision"] if prior else candidate["status"]
    if candidate["status"] == "conflicting" and decision == "approved":
        raise IdentityDecisionError("identity_conflicting_candidate_approval_prohibited")
    if not _transition_allowed(origin, decision):
        raise IdentityDecisionError(
            f"identity_decision_transition_invalid:{origin}_to_{decision}"
        )
    if decision == "approved":
        if source_run_roots is None:
            raise IdentityDecisionError(
                "identity_approval_source_revalidation_required"
            )
        for side in ("left_identity_reference", "right_identity_reference"):
            reference = candidate[side]
            source_type = reference["source_type"]
            if source_type not in source_run_roots:
                raise IdentityDecisionError(
                    f"identity_approval_source_run_root_missing:{source_type}"
                )
            verify_identity_reference_against_run(
                reference, source_run_roots[source_type]
            )
    prior_reference = (
        {"decision_id": prior["decision_id"], "receipt_hash": prior["receipt_hash"]}
        if prior
        else None
    )
    decision_id = derive_id(
        "idd",
        candidate["candidate_id"],
        candidate["candidate_hash"],
        decision,
        authority_payload,
        rationale.to_dict(),
        prior_reference,
        length=20,
    )
    receipt = seal(
        {
            "schema_version": DECISION_SCHEMA_VERSION,
            "decision_id": decision_id,
            "candidate": {
                "candidate_id": candidate["candidate_id"],
                "candidate_hash": candidate["candidate_hash"],
            },
            "evidence_bundle": {
                "evidence_bundle_id": bundle["evidence_bundle_id"],
                "bundle_hash": bundle["bundle_hash"],
            },
            "decision": decision,
            "review_authority": authority_payload,
            "rationale": rationale.to_dict(),
            "decided_at": authority_payload["attested_at"],
            "comparison_policy": candidate["comparison_policy"],
            "evidence_references": sorted(
                candidate["left_identity_reference"]["evidence_refs"]
                + candidate["right_identity_reference"]["evidence_refs"]
            ),
            "prior_decision_receipt": prior_reference,
            "transition": {"origin": origin, "destination": decision},
            "projection_authorized": (
                decision == "approved" and candidate["status"] != "conflicting"
            ),
            "authority_limitations": {
                "local_claim_only": True,
                "reviewer_authenticated": False,
                "real_world_identity_verified": False,
                "cryptographic_signature_verified": False,
            },
        },
        "receipt_hash",
    )
    root.mkdir(parents=True, exist_ok=True)
    predecessor = prior["decision_id"] if prior else "root"
    receipt_path = (
        root
        / "03_review"
        / candidate["candidate_id"]
        / f"from-{predecessor}.decision.json"
    )
    payload = canonical_json_bytes(receipt)
    idempotent = False
    if receipt_path.exists():
        if not receipt_path.is_file() or receipt_path.read_bytes() != payload:
            raise IdentityArtifactCollisionError(
                f"identity_decision_successor_slot_occupied:{predecessor}"
            )
        idempotent = True
    else:
        try:
            write_exclusive_bytes(receipt_path, payload)
        except IdentityArtifactCollisionError:
            if not receipt_path.is_file() or receipt_path.read_bytes() != payload:
                raise IdentityArtifactCollisionError(
                    f"identity_decision_successor_slot_occupied:{predecessor}"
                )
            idempotent = True
    return IdentityDecisionResult(
        success=True,
        decision_id=decision_id,
        decision=decision,
        receipt_path=receipt_path,
        receipt=receipt,
        idempotent_replay=idempotent,
    )
