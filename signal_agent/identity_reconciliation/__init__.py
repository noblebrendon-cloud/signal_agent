"""Offline, governed cross-source identity reconciliation."""

from .candidates import generate_identity_candidates
from .decisions import record_identity_decision
from .models import (
    CandidateGenerationResult,
    IdentityDecisionRationale,
    IdentityDecisionResult,
    IdentityReviewAuthority,
    ProjectionResult,
    ProjectionStatusResult,
)
from .projections import (
    build_reconciled_identity_projection,
    record_projection_status,
)

__all__ = [
    "CandidateGenerationResult",
    "IdentityDecisionRationale",
    "IdentityDecisionResult",
    "IdentityReviewAuthority",
    "ProjectionResult",
    "ProjectionStatusResult",
    "build_reconciled_identity_projection",
    "generate_identity_candidates",
    "record_identity_decision",
    "record_projection_status",
]
