from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from signal_agent.operational_ingestion.models import IngestionResult, PersistedArtifact


GMAIL_HISTORY_SOURCE_TYPE = "gmail_history_offline.v1"
GMAIL_FIXTURE_SCHEMA = "signal_agent.gmail_history_offline_fixture.v1"
GMAIL_PROJECTION_SCHEMA = "signal_agent.gmail_target_label_projection.v1"
GMAIL_SOURCE_RECEIPT_SCHEMA = "signal_agent.gmail_history_source_receipt.v1"


class GmailHistoryOfflineError(RuntimeError):
    pass


class GmailHistoryContractError(GmailHistoryOfflineError):
    pass


class GmailHistoryCoverageError(GmailHistoryOfflineError):
    pass


class GmailHistoryExpiredError(GmailHistoryOfflineError):
    pass


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw(child) for child in value]
    return value


@dataclass(frozen=True)
class GmailHistoryPolicy:
    path: Path
    file_sha256: str
    payload: Mapping[str, Any] = field(repr=False)
    target_label_id: str
    target_label_token: str
    protection_key_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    @property
    def policy_id(self) -> str:
        return str(self.payload["policy_id"])

    @property
    def version(self) -> str:
        return str(self.payload["version"])

    @property
    def projection_policy(self) -> dict[str, str]:
        value = self.payload["projection_policy"]
        return {
            "policy_id": str(value["policy_id"]),
            "version": str(value["version"]),
            "file_sha256": self.file_sha256,
        }

    @property
    def protection(self) -> dict[str, str]:
        value = self.payload["protection"]
        return {
            "algorithm": str(value["algorithm"]),
            "key_id": self.protection_key_id,
            "namespace": str(value["namespace"]),
            "version": str(value["version"]),
        }

    @property
    def eligible_coverage(self) -> frozenset[str]:
        return frozenset(str(item) for item in self.payload["checkpoint_eligible_coverage"])


@dataclass(frozen=True)
class PageContinuationToken:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value:
            raise GmailHistoryContractError("gmail_page_continuation_required")


@dataclass(frozen=True)
class MailboxHistoryContinuation:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value or not self.value.isdecimal():
            raise GmailHistoryContractError("gmail_history_continuation_invalid")


@dataclass(frozen=True)
class GmailFixtureOperation:
    operation: str
    request: Mapping[str, Any]
    status_code: int
    response: Mapping[str, Any] | None
    attempts: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _freeze(self.request))
        if self.response is not None:
            object.__setattr__(self, "response", _freeze(self.response))
        object.__setattr__(self, "attempts", tuple(_freeze(item) for item in self.attempts))


@dataclass(frozen=True)
class GmailFixtureScript:
    path: Path
    script_id: str
    mode: str
    source_instance_ref: str
    target_label_id: str
    coverage_classification: str
    expected_terminal_history_id: str | None
    operations: tuple[GmailFixtureOperation, ...]


@dataclass(frozen=True)
class GmailProjectionResult:
    artifact: Mapping[str, Any]
    records: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact", _freeze(self.artifact))


@dataclass(frozen=True)
class GmailHistoryOfflineResult:
    success: bool
    status: str
    script_id: str
    execution: IngestionResult | None = None
    failure_receipt: PersistedArtifact | None = None

