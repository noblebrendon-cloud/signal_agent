from __future__ import annotations


class GovernedShellError(Exception):
    """Base exception for governed shell failures."""


class ProposalLoadError(GovernedShellError):
    """Raised when proposal JSON cannot be loaded into a plain dict."""


class ProposalSchemaError(GovernedShellError):
    """Raised when a proposal fails command schema validation."""


class ProposalNormalizationError(GovernedShellError):
    """Raised when a proposal cannot be canonicalized deterministically."""


class ProposalPathError(GovernedShellError):
    """Raised when symbolic path references are invalid or unsafe."""


class PolicyLoadError(GovernedShellError):
    """Raised when a governed shell policy file cannot be loaded."""


class PolicyValidationError(GovernedShellError):
    """Raised when a governed shell policy payload is malformed."""


class PolicyDeniedError(GovernedShellError):
    """Raised when a governed shell proposal is denied by policy review."""


class AuditLogError(GovernedShellError):
    """Raised when governed shell audit events cannot be appended or loaded safely."""


class ReplayVerificationError(GovernedShellError):
    """Raised when governed shell replay or verification cannot complete safely."""


class ConfirmationError(GovernedShellError):
    """Raised when exact proposal-hash confirmation fails."""


class ExecutionPlanError(GovernedShellError):
    """Raised when a governed shell execution plan cannot be built, verified, or written."""
