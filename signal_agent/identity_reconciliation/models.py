from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import IdentityDecisionError


Clock = Callable[[], str]


@dataclass(frozen=True)
class IdentityReviewAuthority:
    authority_type: str
    reviewer_id: str
    reviewer_role: str
    authority_basis: str
    attested_at: str
    attestation_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "authority_type": self.authority_type,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "authority_basis": self.authority_basis,
            "attested_at": self.attested_at,
            "attestation_version": self.attestation_version,
        }


@dataclass(frozen=True)
class IdentityDecisionRationale:
    reason_code: str
    summary: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise IdentityDecisionError("identity_decision_reason_code_required")
        if not self.summary.strip():
            raise IdentityDecisionError("identity_decision_rationale_summary_required")

    def to_dict(self) -> dict[str, str]:
        return {
            "reason_code": self.reason_code.strip(),
            "summary": self.summary.strip(),
        }


@dataclass(frozen=True)
class CandidateGenerationResult:
    success: bool
    run_root: Path
    run_id: str
    candidate_count: int
    proposed_count: int
    conflicting_count: int
    candidate_paths: tuple[Path, ...]
    evidence_bundle_paths: tuple[Path, ...]
    manifest_path: Path


@dataclass(frozen=True)
class IdentityDecisionResult:
    success: bool
    decision_id: str
    decision: str
    receipt_path: Path
    receipt: Mapping[str, Any]
    idempotent_replay: bool


@dataclass(frozen=True)
class ProjectionResult:
    success: bool
    projection_id: str
    projection_lineage_id: str
    projection_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class ProjectionStatusResult:
    success: bool
    status_receipt_id: str
    effective_status: str
    status_receipt_path: Path
    manifest_path: Path
