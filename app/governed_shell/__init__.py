"""Governed shell package.

Phase 2 exposes proposal loading, schema validation, normalization, and
canonical hashing only. Execution, policy evaluation, simulation, and
runner integration remain intentionally unimplemented in this phase.
"""

from pathlib import Path

from .errors import (
    GovernedShellError,
    PolicyDeniedError,
    PolicyLoadError,
    PolicyValidationError,
    ProposalLoadError,
    ProposalNormalizationError,
    ProposalPathError,
    ProposalSchemaError,
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
from .risk import RiskReport, derive_effective_risk
from .schema_validate import (
    ValidationResult,
    require_valid_command_proposal,
    validate_command_proposal,
)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

__all__ = [
    "SCHEMA_DIR",
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
]
