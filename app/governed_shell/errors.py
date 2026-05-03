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
