from __future__ import annotations


class OperationalIngestionError(RuntimeError):
    """Base class for source-neutral operational-ingestion failures."""


class OperationalValidationError(OperationalIngestionError):
    pass


class OperationalArtifactError(OperationalIngestionError):
    pass


class ImmutableArtifactConflictError(OperationalArtifactError):
    pass


class SecretBoundaryError(OperationalArtifactError):
    pass


class AcquisitionStateError(OperationalIngestionError):
    pass


class CompletedManifestError(OperationalIngestionError):
    pass


class CheckpointConflictError(OperationalIngestionError):
    pass


class InjectedOperationalFailure(OperationalIngestionError):
    pass
