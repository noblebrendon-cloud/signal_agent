from __future__ import annotations


class IdentityReconciliationError(RuntimeError):
    """Base class for governed identity-reconciliation failures."""


class IdentityPolicyError(IdentityReconciliationError):
    pass


class IdentityEvidenceError(IdentityReconciliationError):
    pass


class IdentityCandidateError(IdentityReconciliationError):
    pass


class IdentityDecisionError(IdentityReconciliationError):
    pass


class IdentityProjectionError(IdentityReconciliationError):
    pass


class IdentityArtifactCollisionError(IdentityReconciliationError):
    pass
