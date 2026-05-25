from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


def stable_json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(payload: object) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()


def derive_id(prefix: str, *parts: object, length: int = 16) -> str:
    return f"{prefix}_{stable_digest([str(part or '') for part in parts])[:length]}"


def _dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _tuple(value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


class ExecutionMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    SIMULATION = "simulation"


@dataclass(frozen=True)
class CanonicalArtifact:
    artifact_id: str
    intent: str
    body: str
    identity_key: str
    lineage_id: str
    title: str | None = None
    source_refs: tuple[str, ...] = ()
    confidence: float = 1.0
    policy_tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("artifact_id", "intent", "body", "identity_key", "lineage_id"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"canonical_artifact_{field_name}_required")
        object.__setattr__(self, "source_refs", _tuple(self.source_refs))
        object.__setattr__(self, "policy_tags", _tuple(self.policy_tags))
        object.__setattr__(self, "metadata", _dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "intent": self.intent,
            "body": self.body,
            "identity_key": self.identity_key,
            "lineage_id": self.lineage_id,
            "title": self.title,
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "policy_tags": list(self.policy_tags),
            "metadata": _dict(self.metadata),
        }


@dataclass(frozen=True)
class AccountBinding:
    binding_id: str
    platform: str
    account_ref: str
    display_name: str | None = None
    provider_account_refs: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("binding_id", "platform", "account_ref"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"account_binding_{field_name}_required")
        object.__setattr__(self, "provider_account_refs", dict(self.provider_account_refs or {}))
        object.__setattr__(self, "metadata", _dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "platform": self.platform,
            "account_ref": self.account_ref,
            "display_name": self.display_name,
            "provider_account_refs": dict(self.provider_account_refs),
            "metadata": _dict(self.metadata),
        }


@dataclass(frozen=True)
class PlatformCapability:
    platform: str
    provider_id: str | None
    max_text_chars: int
    supports_text: bool = True
    supports_analytics: bool = False
    content_kinds: tuple[str, ...] = ("text",)
    capability_version: str = "transport-mvp-v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.platform or "").strip():
            raise ValueError("platform_capability_platform_required")
        if self.max_text_chars <= 0:
            raise ValueError("platform_capability_max_text_chars_positive")
        object.__setattr__(self, "content_kinds", _tuple(self.content_kinds))
        object.__setattr__(self, "metadata", _dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "provider_id": self.provider_id,
            "max_text_chars": self.max_text_chars,
            "supports_text": self.supports_text,
            "supports_analytics": self.supports_analytics,
            "content_kinds": list(self.content_kinds),
            "capability_version": self.capability_version,
            "metadata": _dict(self.metadata),
        }


@dataclass(frozen=True)
class PostRequest:
    request_id: str
    artifact_id: str
    derivative_id: str
    platform: str
    account_binding_id: str
    text: str
    intent: str
    identity_key: str
    lineage_id: str
    source_refs: tuple[str, ...] = ()
    confidence: float = 1.0
    policy_tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "artifact_id",
            "derivative_id",
            "platform",
            "account_binding_id",
            "text",
            "intent",
            "identity_key",
            "lineage_id",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"post_request_{field_name}_required")
        object.__setattr__(self, "source_refs", _tuple(self.source_refs))
        object.__setattr__(self, "policy_tags", _tuple(self.policy_tags))
        object.__setattr__(self, "metadata", _dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "artifact_id": self.artifact_id,
            "derivative_id": self.derivative_id,
            "platform": self.platform,
            "account_binding_id": self.account_binding_id,
            "text": self.text,
            "intent": self.intent,
            "identity_key": self.identity_key,
            "lineage_id": self.lineage_id,
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "policy_tags": list(self.policy_tags),
            "metadata": _dict(self.metadata),
        }


@dataclass(frozen=True)
class PostResult:
    result_id: str
    request_id: str
    platform: str
    status: str
    mode: ExecutionMode
    occurred_at: str
    provider_id: str | None = None
    external_post_id: str | None = None
    error_code: str | None = None
    retryable: bool = False
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("result_id", "request_id", "platform", "status", "occurred_at"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"post_result_{field_name}_required")
        object.__setattr__(self, "mode", ExecutionMode(self.mode))
        object.__setattr__(self, "detail", _dict(self.detail))

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "request_id": self.request_id,
            "platform": self.platform,
            "status": self.status,
            "mode": self.mode.value,
            "occurred_at": self.occurred_at,
            "provider_id": self.provider_id,
            "external_post_id": self.external_post_id,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "detail": _dict(self.detail),
        }


@dataclass(frozen=True)
class AnalyticsSnapshot:
    snapshot_id: str
    request_id: str
    platform: str
    captured_at: str
    metrics: Mapping[str, int | float]
    provider_id: str | None = None
    external_post_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("snapshot_id", "request_id", "platform", "captured_at"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"analytics_snapshot_{field_name}_required")
        object.__setattr__(self, "metrics", dict(self.metrics or {}))
        object.__setattr__(self, "metadata", _dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "request_id": self.request_id,
            "platform": self.platform,
            "captured_at": self.captured_at,
            "metrics": dict(self.metrics),
            "provider_id": self.provider_id,
            "external_post_id": self.external_post_id,
            "metadata": _dict(self.metadata),
        }


@dataclass(frozen=True)
class RetryEvent:
    retry_id: str
    request_id: str
    result_id: str
    attempt_number: int
    next_attempt_number: int
    reason_code: str
    recorded_at: str
    provider_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retry_id": self.retry_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "attempt_number": self.attempt_number,
            "next_attempt_number": self.next_attempt_number,
            "reason_code": self.reason_code,
            "recorded_at": self.recorded_at,
            "provider_id": self.provider_id,
        }


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    request_id: str
    decision: str
    decided_by: str
    decided_at: str
    authorization_scope: str = "publish"
    reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("approval_id", "request_id", "decision", "decided_by", "decided_at"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"approval_decision_{field_name}_required")

    @property
    def permits_live_publish(self) -> bool:
        return self.decision == "approved" and self.authorization_scope == "publish"

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "authorization_scope": self.authorization_scope,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QueueState:
    request_id: str
    state: str
    revision: int
    updated_at: str
    scheduled_for: str | None = None
    approval_id: str | None = None
    attempt_count: int = 0
    last_result_id: str | None = None
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "state": self.state,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "scheduled_for": self.scheduled_for,
            "approval_id": self.approval_id,
            "attempt_count": self.attempt_count,
            "last_result_id": self.last_result_id,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QueueState":
        return cls(
            request_id=str(payload["request_id"]),
            state=str(payload["state"]),
            revision=int(payload["revision"]),
            updated_at=str(payload["updated_at"]),
            scheduled_for=str(payload["scheduled_for"]) if payload.get("scheduled_for") else None,
            approval_id=str(payload["approval_id"]) if payload.get("approval_id") else None,
            attempt_count=int(payload.get("attempt_count", 0) or 0),
            last_result_id=str(payload["last_result_id"]) if payload.get("last_result_id") else None,
            reason_code=str(payload["reason_code"]) if payload.get("reason_code") else None,
        )


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    status: str
    checked_at: str
    platforms: tuple[str, ...]
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "platforms", _tuple(self.platforms))
        object.__setattr__(self, "detail", _dict(self.detail))

    @property
    def available(self) -> bool:
        return self.status in {"healthy", "degraded"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "checked_at": self.checked_at,
            "platforms": list(self.platforms),
            "detail": _dict(self.detail),
        }


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    request_id: str
    policy_id: str
    allowed: bool
    evaluated_at: str
    reason_codes: tuple[str, ...] = ()
    stage: str = "pre_transport"

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", _tuple(self.reason_codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "allowed": self.allowed,
            "evaluated_at": self.evaluated_at,
            "reason_codes": list(self.reason_codes),
            "stage": self.stage,
        }


@dataclass(frozen=True)
class TransformationRecord:
    transformation_id: str
    artifact_id: str
    request_id: str
    derivative_id: str
    platform: str
    transformed_at: str
    canonical_digest: str
    derivative_digest: str
    identity_key: str
    lineage_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformation_id": self.transformation_id,
            "artifact_id": self.artifact_id,
            "request_id": self.request_id,
            "derivative_id": self.derivative_id,
            "platform": self.platform,
            "transformed_at": self.transformed_at,
            "canonical_digest": self.canonical_digest,
            "derivative_digest": self.derivative_digest,
            "identity_key": self.identity_key,
            "lineage_id": self.lineage_id,
        }
