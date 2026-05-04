"""Governed shell package.

Phase 4 exposes proposal loading, schema validation, normalization,
policy review, append-only audit logging, and replay verification only.
Execution, approval, simulation, and runner integration remain
intentionally unimplemented in this phase.
"""

from pathlib import Path

from .errors import (
    AuditLogError,
    GovernedShellError,
    PolicyDeniedError,
    PolicyLoadError,
    PolicyValidationError,
    ProposalLoadError,
    ProposalNormalizationError,
    ProposalPathError,
    ProposalSchemaError,
    ReplayVerificationError,
)
from .logstore import (
    AUDIT_ZERO_HASH,
    AuditVerificationResult,
    append_audit_event,
    build_review_event,
    canonical_event_json,
    compute_event_hash,
    read_audit_events,
    verify_audit_chain,
)
from .normalize import (
    NormalizedProposal,
    PathValidationResult,
    canonicalize_proposal,
    compute_proposal_hash,
    normalize_and_hash_proposal,
    validate_path_refs,
)
from .policy import (
    PolicyDecision,
    PolicyValidationResult,
    evaluate_policy,
    load_policy,
    require_policy_allowed,
    validate_policy,
)
from .proposal import dump_canonical_json, load_json_text, load_proposal
from .replay import ReplayResult, replay_session, summarize_review_chain, verify_log
from .risk import RiskReport, derive_effective_risk
from .schema_validate import (
    ValidationResult,
    require_valid_command_proposal,
    validate_command_proposal,
)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

__all__ = [
    "SCHEMA_DIR",
    "AUDIT_ZERO_HASH",
    "AuditLogError",
    "ReplayVerificationError",
    "GovernedShellError",
    "PolicyDeniedError",
    "PolicyLoadError",
    "PolicyValidationError",
    "ProposalLoadError",
    "ProposalNormalizationError",
    "ProposalPathError",
    "ProposalSchemaError",
    "ValidationResult",
    "PathValidationResult",
    "NormalizedProposal",
    "PolicyValidationResult",
    "PolicyDecision",
    "RiskReport",
    "AuditVerificationResult",
    "ReplayResult",
    "load_proposal",
    "load_json_text",
    "dump_canonical_json",
    "validate_command_proposal",
    "require_valid_command_proposal",
    "validate_path_refs",
    "canonicalize_proposal",
    "compute_proposal_hash",
    "normalize_and_hash_proposal",
    "load_policy",
    "validate_policy",
    "evaluate_policy",
    "require_policy_allowed",
    "derive_effective_risk",
    "canonical_event_json",
    "compute_event_hash",
    "read_audit_events",
    "verify_audit_chain",
    "append_audit_event",
    "build_review_event",
    "replay_session",
    "summarize_review_chain",
    "verify_log",
]
