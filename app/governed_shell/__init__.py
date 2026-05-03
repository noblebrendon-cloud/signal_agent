"""Governed shell package.

Phase 2 exposes proposal loading, schema validation, normalization, and
canonical hashing only. Execution, policy evaluation, simulation, and
runner integration remain intentionally unimplemented in this phase.
"""

from pathlib import Path

from .errors import (
    GovernedShellError,
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
from .proposal import dump_canonical_json, load_json_text, load_proposal
from .schema_validate import (
    ValidationResult,
    require_valid_command_proposal,
    validate_command_proposal,
)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

__all__ = [
    "SCHEMA_DIR",
    "GovernedShellError",
    "ProposalLoadError",
    "ProposalNormalizationError",
    "ProposalPathError",
    "ProposalSchemaError",
    "ValidationResult",
    "PathValidationResult",
    "NormalizedProposal",
    "load_proposal",
    "load_json_text",
    "dump_canonical_json",
    "validate_command_proposal",
    "require_valid_command_proposal",
    "validate_path_refs",
    "canonicalize_proposal",
    "compute_proposal_hash",
    "normalize_and_hash_proposal",
]
