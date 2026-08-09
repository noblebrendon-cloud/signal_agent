from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from .canonical import (
    derive_id,
    require_offset_timestamp,
    require_sha256,
    require_text,
    sha256_canonical,
)
from .errors import OperationalValidationError
from .secrets import assert_secret_free


Clock = Callable[[], str]
JsonMapping = Mapping[str, Any]


def freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(child) for child in value)
    return value


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value


@dataclass(frozen=True)
class PolicyIdentity:
    policy_id: str
    version: str
    file_sha256: str

    def __post_init__(self) -> None:
        require_text(self.policy_id, "policy_id")
        require_text(self.version, "policy_version")
        require_sha256(self.file_sha256, "policy_file")

    def to_dict(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "file_sha256": self.file_sha256,
        }


@dataclass(frozen=True)
class SourceIdentity:
    source_type: str
    source_instance_id: str

    def __post_init__(self) -> None:
        require_text(self.source_type, "source_type")
        require_text(self.source_instance_id, "source_instance_id")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_type": self.source_type,
            "source_instance_id": self.source_instance_id,
        }


@dataclass(frozen=True)
class AcquisitionIntent:
    source: SourceIdentity
    adapter: PolicyIdentity
    acquisition_policy: PolicyIdentity
    assembly_policy: PolicyIdentity
    retry_policy: PolicyIdentity
    secret_policy: PolicyIdentity
    observation_boundary: JsonMapping
    credential_profile_ref: str
    authentication_mode: str
    prior_checkpoint_id: str | None = None
    prior_checkpoint_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_boundary", freeze_json(self.observation_boundary))
        boundary = thaw_json(self.observation_boundary)
        if not isinstance(boundary, dict):
            raise OperationalValidationError("observation_boundary_object_required")
        if set(boundary) != {"kind", "lower", "upper"}:
            raise OperationalValidationError("observation_boundary_contract_invalid")
        require_text(str(boundary["kind"]), "observation_boundary_kind")
        if boundary["lower"] is None or boundary["upper"] is None:
            raise OperationalValidationError("observation_boundary_limits_required")
        require_text(self.credential_profile_ref, "credential_profile_ref")
        require_text(self.authentication_mode, "authentication_mode")
        if (self.prior_checkpoint_id is None) != (self.prior_checkpoint_hash is None):
            raise OperationalValidationError("prior_checkpoint_reference_incomplete")
        if self.prior_checkpoint_hash is not None:
            require_sha256(self.prior_checkpoint_hash, "prior_checkpoint")
        assert_secret_free(self.to_material_dict(), label="acquisition_intent")

    @property
    def cycle_id(self) -> str:
        return derive_id(
            "oac",
            self.source.to_dict(),
            self.adapter.to_dict(),
            self.acquisition_policy.to_dict(),
            self.assembly_policy.to_dict(),
            thaw_json(self.observation_boundary),
            self.prior_checkpoint_hash or "root",
        )

    def to_material_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "adapter": self.adapter.to_dict(),
            "acquisition_policy": self.acquisition_policy.to_dict(),
            "assembly_policy": self.assembly_policy.to_dict(),
            "retry_policy": self.retry_policy.to_dict(),
            "secret_policy": self.secret_policy.to_dict(),
            "observation_boundary": thaw_json(self.observation_boundary),
            "credential_profile_ref": self.credential_profile_ref,
            "authentication_mode": self.authentication_mode,
            "prior_checkpoint": (
                {
                    "checkpoint_id": self.prior_checkpoint_id,
                    "checkpoint_hash": self.prior_checkpoint_hash,
                }
                if self.prior_checkpoint_id is not None
                else None
            ),
        }


@dataclass(frozen=True)
class RequestAttempt:
    page_ordinal: int
    attempt_ordinal: int
    request_fingerprint: str
    continuation_hash: str
    started_at: str
    completed_at: str
    outcome: str
    status_code: int | None = None
    provider_error_code: str | None = None
    requested_delay_ms: int = 0
    applied_delay_ms: int = 0
    response_metadata: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.page_ordinal < 1 or self.attempt_ordinal < 1:
            raise OperationalValidationError("attempt_ordinals_positive")
        require_sha256(self.request_fingerprint, "request_fingerprint")
        require_sha256(self.continuation_hash, "continuation")
        require_offset_timestamp(self.started_at, "attempt_started_at")
        require_offset_timestamp(self.completed_at, "attempt_completed_at")
        if self.outcome not in {
            "success",
            "retryable_failure",
            "permanent_failure",
            "rate_limited",
            "malformed_response",
            "capture_failed",
        }:
            raise OperationalValidationError("attempt_outcome_unsupported")
        if self.requested_delay_ms < 0 or self.applied_delay_ms < 0:
            raise OperationalValidationError("attempt_delay_nonnegative")
        object.__setattr__(self, "response_metadata", freeze_json(self.response_metadata))
        assert_secret_free(thaw_json(self.response_metadata), label="attempt_response_metadata")


@dataclass(frozen=True)
class CanonicalObservation:
    record_type: str
    protected_source_record_id: str
    protection: JsonMapping
    semantic_payload: JsonMapping
    source_event_time: str | None = None
    remote_modified_at: str | None = None

    def __post_init__(self) -> None:
        require_text(self.record_type, "observation_record_type")
        require_text(self.protected_source_record_id, "protected_source_record_id")
        object.__setattr__(self, "protection", freeze_json(self.protection))
        object.__setattr__(self, "semantic_payload", freeze_json(self.semantic_payload))
        if self.source_event_time is not None:
            require_offset_timestamp(self.source_event_time, "source_event_time")
        if self.remote_modified_at is not None:
            require_offset_timestamp(self.remote_modified_at, "remote_modified_at")
        assert_secret_free(self.semantic_dict(include_observation_id=False), label="canonical_observation")

    @property
    def content_hash(self) -> str:
        return sha256_canonical(thaw_json(self.semantic_payload))

    @property
    def observation_id(self) -> str:
        return derive_id(
            "oob",
            self.record_type,
            self.protected_source_record_id,
            self.content_hash,
        )

    def semantic_dict(self, *, include_observation_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "record_type": self.record_type,
            "protected_source_record_id": self.protected_source_record_id,
            "protection": thaw_json(self.protection),
            "content_hash": self.content_hash,
            "semantic_payload": thaw_json(self.semantic_payload),
            "source_event_time": self.source_event_time,
            "remote_modified_at": self.remote_modified_at,
        }
        if include_observation_id:
            payload["observation_id"] = self.observation_id
        return payload


@dataclass(frozen=True)
class CapturedPage:
    page_ordinal: int
    successful_attempt_ordinal: int
    request_fingerprint: str
    continuation_hash: str
    response_body: bytes
    response_schema: str
    media_type: str
    captured_at: str
    terminal: bool
    next_continuation: JsonMapping
    observations: tuple[CanonicalObservation, ...]
    response_metadata: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.page_ordinal < 1 or self.successful_attempt_ordinal < 1:
            raise OperationalValidationError("capture_ordinals_positive")
        require_sha256(self.request_fingerprint, "capture_request_fingerprint")
        require_sha256(self.continuation_hash, "capture_continuation")
        require_text(self.response_schema, "capture_response_schema")
        require_text(self.media_type, "capture_media_type")
        require_offset_timestamp(self.captured_at, "capture_time")
        object.__setattr__(self, "next_continuation", freeze_json(self.next_continuation))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "response_metadata", freeze_json(self.response_metadata))
        assert_secret_free(thaw_json(self.next_continuation), label="next_continuation")
        assert_secret_free(thaw_json(self.response_metadata), label="capture_response_metadata")


@dataclass(frozen=True)
class CompletedRunReference:
    run_id: str
    run_root: Path
    run_root_ref: str
    manifest_relative_path: str
    preservation_receipt_relative_path: str

    def __post_init__(self) -> None:
        require_text(self.run_id, "completed_run_id")
        require_text(self.run_root_ref, "completed_run_root_ref")
        require_text(self.manifest_relative_path, "manifest_relative_path")
        require_text(self.preservation_receipt_relative_path, "preservation_receipt_relative_path")


@dataclass(frozen=True)
class CompletedManifestVerifierAuthority:
    candidate_id: str
    candidate_hash: str
    verifier_version: str
    completion_policy: PolicyIdentity
    verified_at: str
    completed_run: JsonMapping
    assertions: JsonMapping
    authority_type: str = "completed_manifest_verifier"

    def __post_init__(self) -> None:
        if self.authority_type != "completed_manifest_verifier":
            raise OperationalValidationError("completed_manifest_authority_type_unsupported")
        require_text(self.candidate_id, "completed_manifest_candidate_id")
        require_sha256(self.candidate_hash, "completed_manifest_candidate")
        require_text(self.verifier_version, "completed_manifest_verifier_version")
        require_offset_timestamp(self.verified_at, "completed_manifest_verified_at")
        object.__setattr__(self, "completed_run", freeze_json(self.completed_run))
        object.__setattr__(self, "assertions", freeze_json(self.assertions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_type": self.authority_type,
            "candidate": {
                "candidate_id": self.candidate_id,
                "candidate_hash": self.candidate_hash,
            },
            "verifier_version": self.verifier_version,
            "completion_policy": self.completion_policy.to_dict(),
            "verified_at": self.verified_at,
            "verification_time_basis": "sealed_completed_manifest_created_at",
            "completed_run": thaw_json(self.completed_run),
            "assertions": thaw_json(self.assertions),
            "external_action_authorized": False,
            "network_authorized": False,
            "upstream_write_authorized": False,
        }


@dataclass(frozen=True)
class ObservationIndexReference:
    observation_index_id: str
    observation_index_hash: str
    path: str

    def __post_init__(self) -> None:
        require_text(self.observation_index_id, "observation_index_id")
        require_sha256(self.observation_index_hash, "observation_index")
        require_text(self.path, "observation_index_path")

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_index_id": self.observation_index_id,
            "observation_index_hash": self.observation_index_hash,
            "path": self.path,
        }


@dataclass(frozen=True)
class PersistedArtifact:
    path: Path
    payload: JsonMapping
    idempotent_replay: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_json(self.payload))


@dataclass(frozen=True)
class ResolvedIngestionState:
    stage: str
    source_instance_id: str
    session_id: str | None
    current_checkpoint_id: str | None
    current_checkpoint_hash: str | None


@dataclass(frozen=True)
class IngestionResult:
    source_root: Path
    session_root: Path
    intent: PersistedArtifact
    session: PersistedArtifact
    boundary: PersistedArtifact
    bounded_material: PersistedArtifact
    observation_index: PersistedArtifact
    checkpoint_candidate: PersistedArtifact
    completion_authority: PersistedArtifact
    checkpoint_commit: PersistedArtifact
    completed_run: CompletedRunReference
