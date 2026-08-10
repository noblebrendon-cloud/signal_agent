from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .artifacts import (
    SESSION_SCHEMA,
    load_artifact,
    persist_attempt,
    persist_capture,
    persist_failure,
    persist_intent,
    persist_session,
    safe_artifact_path,
)
from .canonical import (
    canonical_json_bytes,
    derive_id,
    require_offset_timestamp,
    require_sha256,
    require_text,
    sha256_bytes,
    sha256_canonical,
)
from .contracts import GovernedProcessor
from .errors import OperationalIngestionError, OperationalValidationError
from .kernel import OperationalIngestionKernel
from .models import (
    AcquisitionIntent,
    CapturedPage,
    Clock,
    IngestionResult,
    PersistedArtifact,
    PolicyIdentity,
    RequestAttempt,
    SourceIdentity,
    freeze_json,
    thaw_json,
)
from .secrets import assert_secret_free, assert_secret_free_bytes


RETRY_POLICY_SCHEMA = "signal_agent.operational_retry_policy.v1"
SIMULATED_PAGE_SCHEMA = "signal_agent.simulated_remote_relationship_page.v1"
SIMULATED_RECORD_TYPE = "simulated_operational_relationship_observation"
SIMULATED_TRANSPORT_KIND = "offline_deterministic_simulator"
SIMULATED_MODE = "simulation"
PROTECTION_ALGORITHM = "HMAC-SHA-256"
PROTECTION_VERSION = "simulated_operational_record_token.v1"


class SimulatedOperationalError(OperationalIngestionError):
    pass


class SimulatedPermanentFailure(SimulatedOperationalError):
    pass


class SimulatedRetryExhausted(SimulatedOperationalError):
    pass


class SimulatedTransportInterruption(SimulatedOperationalError):
    pass


class SimulatedAcquisitionInterrupted(SimulatedOperationalError):
    def __init__(self, message: str, partial: "PartialAcquisition") -> None:
        super().__init__(message)
        self.partial = partial


class DeterministicVirtualClock:
    """Injected clock that records simulated delay without sleeping."""

    def __init__(self, start: str) -> None:
        normalized = require_offset_timestamp(start, "virtual_clock_start")
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        self._current = parsed.astimezone(timezone.utc)
        self._elapsed_ms = 0

    def __call__(self) -> str:
        value = self._current.isoformat(timespec="milliseconds")
        return value.replace("+00:00", "Z")

    @property
    def elapsed_ms(self) -> int:
        return self._elapsed_ms

    def advance_ms(self, value: int) -> None:
        if value < 0:
            raise OperationalValidationError("virtual_clock_delay_nonnegative")
        self._current += timedelta(milliseconds=value)
        self._elapsed_ms += value


@dataclass(frozen=True)
class RetryPolicy:
    identity: PolicyIdentity
    retryable_outcomes: tuple[str, ...]
    maximum_attempts: int
    initial_delay_ms: int
    multiplier: int
    maximum_delay_ms: int
    jitter_rule: str
    maximum_jitter_ms: int
    maximum_elapsed_ms: int
    retry_after_mode: str
    maximum_retry_after_ms: int

    def __post_init__(self) -> None:
        if not self.retryable_outcomes:
            raise OperationalValidationError("retry_policy_outcomes_required")
        if self.maximum_attempts < 1:
            raise OperationalValidationError("retry_policy_attempts_positive")
        if min(
            self.initial_delay_ms,
            self.maximum_delay_ms,
            self.maximum_jitter_ms,
            self.maximum_elapsed_ms,
            self.maximum_retry_after_ms,
        ) < 0:
            raise OperationalValidationError("retry_policy_bounds_nonnegative")
        if self.multiplier < 1:
            raise OperationalValidationError("retry_policy_multiplier_positive")
        if self.jitter_rule != "sha256_modulo_ms":
            raise OperationalValidationError("retry_policy_jitter_rule_unsupported")
        if self.retry_after_mode != "maximum_of_backoff_and_retry_after":
            raise OperationalValidationError("retry_after_mode_unsupported")

    def delay_ms(
        self,
        *,
        request_fingerprint: str,
        attempt_ordinal: int,
        retry_after_ms: int | None,
    ) -> int:
        exponent = max(0, attempt_ordinal - 1)
        backoff = min(
            self.maximum_delay_ms,
            self.initial_delay_ms * (self.multiplier**exponent),
        )
        jitter_material = f"{request_fingerprint}:{attempt_ordinal}".encode("utf-8")
        jitter_value = int(hashlib.sha256(jitter_material).hexdigest(), 16)
        jitter = (
            0
            if self.maximum_jitter_ms == 0
            else jitter_value % (self.maximum_jitter_ms + 1)
        )
        provider_delay = min(
            self.maximum_retry_after_ms,
            max(0, int(retry_after_ms or 0)),
        )
        return max(backoff + jitter, provider_delay)


def load_retry_policy(path: str | Path) -> RetryPolicy:
    target = Path(path).expanduser().resolve(strict=True)
    try:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperationalValidationError("retry_policy_unreadable") from exc
    if not isinstance(payload, dict):
        raise OperationalValidationError("retry_policy_object_required")
    required = {
        "schema_version",
        "policy_id",
        "version",
        "retryable_outcome_classes",
        "maximum_attempts",
        "exponential_backoff",
        "deterministic_simulation_jitter",
        "maximum_elapsed_acquisition_ms",
        "retry_after",
    }
    if set(payload) != required or payload["schema_version"] != RETRY_POLICY_SCHEMA:
        raise OperationalValidationError("retry_policy_contract_invalid")
    assert_secret_free(payload, label="retry_policy")
    backoff = payload["exponential_backoff"]
    jitter = payload["deterministic_simulation_jitter"]
    retry_after = payload["retry_after"]
    if not all(isinstance(item, dict) for item in (backoff, jitter, retry_after)):
        raise OperationalValidationError("retry_policy_nested_contract_invalid")
    return RetryPolicy(
        identity=PolicyIdentity(
            policy_id=require_text(str(payload["policy_id"]), "retry_policy_id"),
            version=require_text(str(payload["version"]), "retry_policy_version"),
            file_sha256=sha256_bytes(raw),
        ),
        retryable_outcomes=tuple(str(item) for item in payload["retryable_outcome_classes"]),
        maximum_attempts=int(payload["maximum_attempts"]),
        initial_delay_ms=int(backoff["initial_delay_ms"]),
        multiplier=int(backoff["multiplier"]),
        maximum_delay_ms=int(backoff["maximum_delay_ms"]),
        jitter_rule=str(jitter["rule"]),
        maximum_jitter_ms=int(jitter["maximum_jitter_ms"]),
        maximum_elapsed_ms=int(payload["maximum_elapsed_acquisition_ms"]),
        retry_after_mode=str(retry_after["mode"]),
        maximum_retry_after_ms=int(retry_after["maximum_retry_after_ms"]),
    )


@dataclass(frozen=True)
class SimulatedOperationalRequest:
    source_instance_id: str
    page_ordinal: int
    continuation: str
    endpoint_id: str = "simulated_relationship_pages"

    def __post_init__(self) -> None:
        require_text(self.source_instance_id, "simulated_request_source")
        require_text(self.continuation, "simulated_request_continuation")
        if self.page_ordinal < 1:
            raise OperationalValidationError("simulated_request_page_positive")
        assert_secret_free(self.to_safe_dict(), label="simulated_request")

    @property
    def request_fingerprint(self) -> str:
        return sha256_canonical(self.to_safe_dict())

    @property
    def continuation_hash(self) -> str:
        return sha256_canonical(
            {"kind": "safe_simulated_cursor", "value": self.continuation}
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "source_instance_id": self.source_instance_id,
            "page_ordinal": self.page_ordinal,
            "continuation": self.continuation,
            "method": "SIMULATED_READ",
        }


@dataclass(frozen=True)
class SimulatedTransportOutcome:
    outcome: str
    status_code: int | None
    elapsed_ms: int = 25
    retry_after_ms: int | None = None
    provider_error_code: str | None = None
    response_body: bytes | None = field(default=None, repr=False)
    response_metadata: Mapping[str, Any] = field(default_factory=dict)
    private_error_detail: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.outcome not in {
            "success",
            "rate_limited",
            "retryable_failure",
            "permanent_failure",
            "interruption",
        }:
            raise OperationalValidationError("simulated_outcome_unsupported")
        if self.elapsed_ms < 0 or (self.retry_after_ms is not None and self.retry_after_ms < 0):
            raise OperationalValidationError("simulated_outcome_timing_nonnegative")
        object.__setattr__(self, "response_metadata", freeze_json(self.response_metadata))
        assert_secret_free(thaw_json(self.response_metadata), label="simulated_response_metadata")
        if self.outcome == "success" and self.response_body is None:
            raise OperationalValidationError("simulated_success_body_required")


@dataclass(frozen=True)
class SimulatedPagePlan:
    request_continuation: str
    outcomes: tuple[SimulatedTransportOutcome, ...]

    def __post_init__(self) -> None:
        require_text(self.request_continuation, "simulated_plan_continuation")
        if not self.outcomes:
            raise OperationalValidationError("simulated_plan_outcomes_required")


@dataclass(frozen=True)
class SimulatedAcquisitionScript:
    script_id: str
    source_instance_id: str
    pages: tuple[SimulatedPagePlan, ...]
    response_schema: str = SIMULATED_PAGE_SCHEMA

    def __post_init__(self) -> None:
        require_text(self.script_id, "simulated_script_id")
        require_text(self.source_instance_id, "simulated_script_source")
        if not self.pages:
            raise OperationalValidationError("simulated_script_pages_required")
        continuations = [item.request_continuation for item in self.pages]
        if len(continuations) != len(set(continuations)):
            raise OperationalValidationError("simulated_script_duplicate_request_continuation")

    def plan_for(self, continuation: str) -> SimulatedPagePlan:
        for page in self.pages:
            if page.request_continuation == continuation:
                return page
        raise SimulatedPermanentFailure("simulated_continuation_not_scripted")


def _outcome_from_fixture(value: Any) -> SimulatedTransportOutcome:
    if not isinstance(value, dict):
        raise OperationalValidationError("simulated_fixture_outcome_object_required")
    response_body = None
    if "page" in value:
        response_body = canonical_json_bytes(value["page"])
    elif "raw_body" in value:
        raw_body = value["raw_body"]
        if not isinstance(raw_body, str):
            raise OperationalValidationError("simulated_fixture_raw_body_string_required")
        response_body = raw_body.encode("utf-8")
    return SimulatedTransportOutcome(
        outcome=str(value.get("outcome") or ""),
        status_code=(None if value.get("status_code") is None else int(value["status_code"])),
        elapsed_ms=int(value.get("elapsed_ms", 25)),
        retry_after_ms=(
            None if value.get("retry_after_ms") is None else int(value["retry_after_ms"])
        ),
        provider_error_code=(
            None if value.get("provider_error_code") is None else str(value["provider_error_code"])
        ),
        response_body=response_body,
        response_metadata=value.get("response_metadata", {}),
        private_error_detail=(
            None if value.get("private_error_detail") is None else str(value["private_error_detail"])
        ),
    )


def load_simulated_script(path: str | Path) -> SimulatedAcquisitionScript:
    target = Path(path).expanduser().resolve(strict=True)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperationalValidationError("simulated_fixture_unreadable") from exc
    if not isinstance(payload, dict):
        raise OperationalValidationError("simulated_fixture_object_required")
    if payload.get("schema_version") != "signal_agent.simulated_acquisition_script.v1":
        raise OperationalValidationError("simulated_fixture_schema_invalid")
    page_values = payload.get("pages")
    if not isinstance(page_values, list):
        raise OperationalValidationError("simulated_fixture_pages_required")
    pages = []
    for value in page_values:
        if not isinstance(value, dict) or not isinstance(value.get("outcomes"), list):
            raise OperationalValidationError("simulated_fixture_page_contract_invalid")
        pages.append(
            SimulatedPagePlan(
                request_continuation=str(value.get("request_continuation") or ""),
                outcomes=tuple(_outcome_from_fixture(item) for item in value["outcomes"]),
            )
        )
    return SimulatedAcquisitionScript(
        script_id=str(payload.get("script_id") or ""),
        source_instance_id=str(payload.get("source_instance_id") or ""),
        response_schema=str(payload.get("response_schema") or SIMULATED_PAGE_SCHEMA),
        pages=tuple(pages),
    )


class SimulatedOperationalTransport:
    """Deterministic in-memory transport; it performs no networking."""

    def __init__(self, script: SimulatedAcquisitionScript) -> None:
        self.script = script
        self._positions: dict[str, int] = {}

    def fetch(self, request: SimulatedOperationalRequest) -> SimulatedTransportOutcome:
        plan = self.script.plan_for(request.continuation)
        position = self._positions.get(request.continuation, 0)
        if position >= len(plan.outcomes):
            position = len(plan.outcomes) - 1
        self._positions[request.continuation] = position + 1
        outcome = plan.outcomes[position]
        if outcome.outcome == "interruption":
            raise SimulatedTransportInterruption(
                outcome.private_error_detail or "simulated_transport_interruption"
            )
        return outcome


@dataclass(frozen=True)
class SimulatedCanonicalObservation:
    record_type: str
    protected_source_record_id: str
    protection: Mapping[str, Any]
    semantic_payload: Mapping[str, Any]
    observation_state: str
    source_event_time: str | None
    remote_modified_at: str | None
    supersedes_observation_id: str | None = None
    predecessor_content_hash: str | None = None
    ordering_state: str = "provider_version_ordered"

    def __post_init__(self) -> None:
        require_text(self.record_type, "simulated_observation_record_type")
        require_text(self.protected_source_record_id, "simulated_observation_identity")
        if self.observation_state not in {"active", "tombstone"}:
            raise OperationalValidationError("simulated_observation_state_invalid")
        object.__setattr__(self, "protection", freeze_json(self.protection))
        object.__setattr__(self, "semantic_payload", freeze_json(self.semantic_payload))
        if self.source_event_time is not None:
            require_offset_timestamp(self.source_event_time, "simulated_source_event_time")
        if self.remote_modified_at is not None:
            require_offset_timestamp(self.remote_modified_at, "simulated_remote_modified_at")
        if self.predecessor_content_hash is not None:
            require_sha256(self.predecessor_content_hash, "simulated_predecessor_content")
        assert_secret_free(self.semantic_dict(include_observation_id=False), label="simulated_observation")

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
            "observation_state": self.observation_state,
            "source_event_time": self.source_event_time,
            "remote_modified_at": self.remote_modified_at,
            "supersedes_observation_id": self.supersedes_observation_id,
            "predecessor_content_hash": self.predecessor_content_hash,
            "ordering_state": self.ordering_state,
        }
        if include_observation_id:
            payload["observation_id"] = self.observation_id
        return payload


class SimulatedRemoteInteractionSource:
    """Simulator-specific page semantics and protected observation extraction."""

    def __init__(
        self,
        *,
        script: SimulatedAcquisitionScript,
        protection_key: bytes,
        protection_key_id: str,
        maximum_pages: int = 10,
        maximum_records: int = 100,
        maximum_response_bytes: int = 1024 * 1024,
    ) -> None:
        if len(protection_key) < 32:
            raise OperationalValidationError("simulated_protection_key_too_short")
        require_text(protection_key_id, "simulated_protection_key_id")
        if min(maximum_pages, maximum_records, maximum_response_bytes) < 1:
            raise OperationalValidationError("simulated_source_bounds_positive")
        self.script = script
        self._protection_key = bytes(protection_key)
        self.protection_key_id = protection_key_id
        self.maximum_pages = maximum_pages
        self.maximum_records = maximum_records
        self.maximum_response_bytes = maximum_response_bytes
        self._versions: dict[tuple[str, str], SimulatedCanonicalObservation] = {}
        self._latest: dict[str, SimulatedCanonicalObservation] = {}

    def reset(self) -> None:
        self._versions.clear()
        self._latest.clear()

    def prime(self, pages: Sequence[CapturedPage]) -> None:
        self.reset()
        for page in sorted(pages, key=lambda item: item.page_ordinal):
            for value in page.observations:
                if not isinstance(value, SimulatedCanonicalObservation):
                    raise OperationalValidationError("simulated_partial_observation_type_invalid")
                semantic = thaw_json(value.semantic_payload)
                canonical_record = {
                    key: semantic[key]
                    for key in (
                        "fixture_source_record_label",
                        "source_record_version",
                        "observation_state",
                        "display_name",
                        "company",
                        "position",
                        "source_event_time",
                        "remote_modified_at",
                    )
                }
                key = (
                    value.protected_source_record_id,
                    sha256_canonical(canonical_record),
                )
                self._versions[key] = value
                self._latest[value.protected_source_record_id] = value

    def protected_record_id(self, clear_record_id: str) -> str:
        digest = hmac.new(
            self._protection_key,
            clear_record_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"hmac-sha256:{digest}"

    def initial_request(self, intent: AcquisitionIntent) -> SimulatedOperationalRequest:
        if intent.source.source_instance_id != self.script.source_instance_id:
            raise OperationalValidationError("simulated_source_instance_mismatch")
        return SimulatedOperationalRequest(
            source_instance_id=intent.source.source_instance_id,
            page_ordinal=1,
            continuation="root",
        )

    def next_request(self, page: CapturedPage) -> SimulatedOperationalRequest | None:
        if page.terminal:
            return None
        continuation = thaw_json(page.next_continuation)
        if continuation.get("kind") != "safe_simulated_cursor":
            raise OperationalValidationError("simulated_continuation_classification_invalid")
        return SimulatedOperationalRequest(
            source_instance_id=self.script.source_instance_id,
            page_ordinal=page.page_ordinal + 1,
            continuation=require_text(str(continuation.get("value") or ""), "next_cursor"),
        )

    def _observation(self, record: Mapping[str, Any]) -> SimulatedCanonicalObservation:
        required = {
            "record_id",
            "version",
            "state",
            "display_name",
            "company",
            "position",
            "source_event_time",
            "remote_modified_at",
        }
        if set(record) != required:
            raise OperationalValidationError("simulated_record_contract_invalid")
        clear_record_id = require_text(str(record["record_id"]), "simulated_record_id")
        state = str(record["state"])
        if state not in {"active", "tombstone"}:
            raise OperationalValidationError("simulated_record_state_invalid")
        version = int(record["version"])
        if version < 1:
            raise OperationalValidationError("simulated_record_version_positive")
        source_event_time = require_offset_timestamp(
            str(record["source_event_time"]), "simulated_record_event_time"
        )
        remote_modified_at = require_offset_timestamp(
            str(record["remote_modified_at"]), "simulated_record_modified_time"
        )
        protected = self.protected_record_id(clear_record_id)
        canonical_record = {
            "fixture_source_record_label": clear_record_id,
            "source_record_version": version,
            "observation_state": state,
            "display_name": str(record["display_name"]),
            "company": str(record["company"]),
            "position": str(record["position"]),
            "source_event_time": source_event_time,
            "remote_modified_at": remote_modified_at,
        }
        base_hash = sha256_canonical(canonical_record)
        duplicate = self._versions.get((protected, base_hash))
        if duplicate is not None:
            return duplicate
        predecessor = self._latest.get(protected)
        ordering_state = "provider_version_ordered"
        supersedes = None
        predecessor_hash = None
        if predecessor is not None:
            prior_version = int(thaw_json(predecessor.semantic_payload)["source_record_version"])
            if version > prior_version:
                supersedes = predecessor.observation_id
                predecessor_hash = predecessor.content_hash
            else:
                ordering_state = "ambiguous"
        semantic_payload = {
            **canonical_record,
            "supersedes_observation_id": supersedes,
            "predecessor_content_hash": predecessor_hash,
            "ordering_state": ordering_state,
        }
        observation = SimulatedCanonicalObservation(
            record_type=SIMULATED_RECORD_TYPE,
            protected_source_record_id=protected,
            protection={
                "algorithm": PROTECTION_ALGORITHM,
                "key_id": self.protection_key_id,
                "version": PROTECTION_VERSION,
            },
            semantic_payload=semantic_payload,
            observation_state=state,
            source_event_time=source_event_time,
            remote_modified_at=remote_modified_at,
            supersedes_observation_id=supersedes,
            predecessor_content_hash=predecessor_hash,
            ordering_state=ordering_state,
        )
        self._versions[(protected, base_hash)] = observation
        if predecessor is None or ordering_state == "provider_version_ordered":
            self._latest[protected] = observation
        return observation

    def assess_response(
        self,
        *,
        request: SimulatedOperationalRequest,
        outcome: SimulatedTransportOutcome,
        attempt_ordinal: int,
        captured_at: str,
    ) -> CapturedPage:
        if outcome.outcome != "success" or outcome.response_body is None:
            raise OperationalValidationError("simulated_success_response_required")
        if len(outcome.response_body) > self.maximum_response_bytes:
            raise OperationalValidationError("simulated_response_size_bound_exhausted")
        assert_secret_free_bytes(outcome.response_body, label="simulated_success_response")
        try:
            payload = json.loads(outcome.response_body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OperationalValidationError("simulated_success_response_malformed") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "page_id",
            "records",
            "next_cursor",
            "terminal",
        }:
            raise OperationalValidationError("simulated_page_contract_invalid")
        if payload["schema_version"] != self.script.response_schema:
            raise OperationalValidationError("simulated_page_schema_mismatch")
        records = payload["records"]
        if not isinstance(records, list):
            raise OperationalValidationError("simulated_page_records_array_required")
        terminal = payload["terminal"]
        if not isinstance(terminal, bool):
            raise OperationalValidationError("simulated_page_terminal_boolean_required")
        next_cursor = payload["next_cursor"]
        if terminal and next_cursor is not None:
            raise OperationalValidationError("simulated_terminal_cursor_forbidden")
        if not terminal and (not isinstance(next_cursor, str) or not next_cursor):
            raise OperationalValidationError("simulated_nonterminal_cursor_required")
        if not records and not terminal:
            raise OperationalValidationError("simulated_empty_nonterminal_page_invalid")
        observations = tuple(self._observation(record) for record in records)
        return CapturedPage(
            page_ordinal=request.page_ordinal,
            successful_attempt_ordinal=attempt_ordinal,
            request_fingerprint=request.request_fingerprint,
            continuation_hash=request.continuation_hash,
            response_body=outcome.response_body,
            response_schema=self.script.response_schema,
            media_type="application/json",
            captured_at=captured_at,
            terminal=terminal,
            next_continuation=(
                {"kind": "end_of_stream"}
                if terminal
                else {"kind": "safe_simulated_cursor", "value": next_cursor}
            ),
            observations=observations,
            response_metadata=thaw_json(outcome.response_metadata),
        )


@dataclass(frozen=True)
class PartialAcquisition:
    intent: AcquisitionIntent
    session_started_at: str
    source_root: Path
    session_root: Path
    attempts: tuple[RequestAttempt, ...]
    pages: tuple[CapturedPage, ...]
    attempt_artifacts: tuple[PersistedArtifact, ...]
    capture_artifacts: tuple[PersistedArtifact, ...]
    next_request: SimulatedOperationalRequest


@dataclass(frozen=True)
class SimulatedExecutionResult:
    ingestion: IngestionResult
    attempts: tuple[RequestAttempt, ...]
    pages: tuple[CapturedPage, ...]
    retry_count: int
    requested_delay_ms: int


AcquisitionFailureInjector = Callable[[str], None]


class SimulatedAcquisitionCoordinator:
    """Offline retry/pagination consumer that terminates in the real M4A kernel."""

    def __init__(
        self,
        store_root: str | Path,
        *,
        clock: DeterministicVirtualClock,
        retry_policy: RetryPolicy,
        acquisition_failure_injector: AcquisitionFailureInjector | None = None,
        kernel_failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.store_root = Path(store_root).resolve(strict=False)
        self.clock = clock
        self.retry_policy = retry_policy
        self.acquisition_failure_injector = acquisition_failure_injector
        self.kernel_failure_injector = kernel_failure_injector

    def _inject(self, stage: str) -> None:
        if self.acquisition_failure_injector is not None:
            self.acquisition_failure_injector(stage)

    def _source_root(self, intent: AcquisitionIntent) -> Path:
        return self.store_root / derive_id(
            "osi", intent.source.source_type, intent.source.source_instance_id
        )

    def _open_session(
        self,
        intent: AcquisitionIntent,
        session_started_at: str,
    ) -> tuple[Path, Path, PersistedArtifact, PersistedArtifact]:
        source_root = self._source_root(intent)
        source_root.mkdir(parents=True, exist_ok=True)
        session_id = derive_id(
            "oas",
            SESSION_SCHEMA,
            intent.cycle_id,
            session_started_at,
            SIMULATED_TRANSPORT_KIND,
            SIMULATED_MODE,
        )
        session_root = source_root / f"sessions/{session_id}"
        intent_artifact = persist_intent(session_root, intent)
        session_artifact = persist_session(
            session_root,
            intent_payload=thaw_json(intent_artifact.payload),
            started_at=session_started_at,
            transport_kind=SIMULATED_TRANSPORT_KIND,
            mode=SIMULATED_MODE,
        )
        return source_root, session_root, intent_artifact, session_artifact

    def _persist_acquisition_failure(
        self,
        *,
        session_root: Path,
        session_id: str,
        stage: str,
        exc: Exception,
        valid: Sequence[PersistedArtifact],
    ) -> None:
        persist_failure(
            session_root,
            session_id=session_id,
            failed_stage=stage,
            failed_at=self.clock(),
            error_class=exc.__class__.__name__,
            error_code=exc.__class__.__name__,
            last_valid_artifacts=valid,
        )

    def verify_partial(self, partial: PartialAcquisition) -> None:
        source_root = partial.source_root.resolve(strict=True)
        if partial.session_root.resolve(strict=True).parent != source_root / "sessions":
            raise OperationalValidationError("simulated_partial_session_root_invalid")
        attempts: dict[str, dict[str, Any]] = {}
        for artifact in partial.attempt_artifacts:
            loaded = load_artifact(artifact.path)
            if loaded != thaw_json(artifact.payload):
                raise OperationalValidationError("simulated_partial_attempt_reference_mismatch")
            attempts[str(loaded["attempt_id"])] = loaded
        previous: dict[str, Any] | None = None
        if len(partial.capture_artifacts) != len(partial.pages):
            raise OperationalValidationError("simulated_partial_capture_count_mismatch")
        for artifact, page in zip(partial.capture_artifacts, partial.pages):
            loaded = load_artifact(artifact.path)
            if loaded != thaw_json(artifact.payload):
                raise OperationalValidationError("simulated_partial_capture_reference_mismatch")
            body_ref = loaded["response_body"]
            body_path = safe_artifact_path(partial.session_root, str(body_ref["path"]))
            body = body_path.read_bytes()
            if sha256_bytes(body) != body_ref["body_sha256"]:
                raise OperationalValidationError("simulated_partial_capture_body_hash_mismatch")
            if len(body) != body_ref["byte_size"]:
                raise OperationalValidationError("simulated_partial_capture_body_size_mismatch")
            if body != page.response_body:
                raise OperationalValidationError("simulated_partial_capture_body_reference_mismatch")
            attempt = attempts.get(str(loaded["attempt"]["attempt_id"]))
            if attempt is None or attempt["artifact_hash"] != loaded["attempt"]["attempt_hash"]:
                raise OperationalValidationError("simulated_partial_capture_attempt_mismatch")
            expected_previous = None if previous is None else {
                "capture_id": previous["capture_id"],
                "capture_hash": previous["artifact_hash"],
                "page_ordinal": previous["page_ordinal"],
            }
            if loaded["previous_capture"] != expected_previous:
                raise OperationalValidationError("simulated_partial_capture_chain_invalid")
            previous = loaded
        if partial.pages and partial.pages[-1].terminal:
            raise OperationalValidationError("simulated_partial_must_be_nonterminal")
        if partial.next_request.continuation in {"", "root"} and partial.pages:
            raise OperationalValidationError("simulated_partial_continuation_invalid")

    def recover_partial(
        self,
        *,
        intent: AcquisitionIntent,
        source: SimulatedRemoteInteractionSource,
        session_started_at: str,
    ) -> PartialAcquisition:
        """Reconstruct and fully verify a resumable partial chain from disk."""

        require_offset_timestamp(session_started_at, "simulated_session_started_at")
        source_root = self._source_root(intent).resolve(strict=True)
        session_id = derive_id(
            "oas",
            SESSION_SCHEMA,
            intent.cycle_id,
            session_started_at,
            SIMULATED_TRANSPORT_KIND,
            SIMULATED_MODE,
        )
        session_root = (source_root / f"sessions/{session_id}").resolve(strict=True)
        intent_payload = load_artifact(
            session_root / "00_intent/acquisition_intent.json"
        )
        session_payload = load_artifact(
            session_root / "00_intent/session_descriptor.json"
        )
        if intent_payload.get("acquisition_cycle_id") != intent.cycle_id:
            raise OperationalValidationError("simulated_partial_intent_mismatch")
        if session_payload.get("session_id") != session_id:
            raise OperationalValidationError("simulated_partial_session_mismatch")

        attempt_pairs: list[tuple[RequestAttempt, PersistedArtifact]] = []
        attempts_by_id: dict[str, tuple[RequestAttempt, PersistedArtifact]] = {}
        for path in (session_root / "01_attempts").glob("*.attempt.json"):
            payload = load_artifact(path)
            attempt = RequestAttempt(
                page_ordinal=int(payload["page_ordinal"]),
                attempt_ordinal=int(payload["attempt_ordinal"]),
                request_fingerprint=str(payload["request_fingerprint"]),
                continuation_hash=str(payload["continuation_hash"]),
                started_at=str(payload["started_at"]),
                completed_at=str(payload["completed_at"]),
                outcome=str(payload["outcome"]),
                status_code=(
                    None
                    if payload.get("status_code") is None
                    else int(payload["status_code"])
                ),
                provider_error_code=(
                    None
                    if payload.get("provider_error_code") is None
                    else str(payload["provider_error_code"])
                ),
                requested_delay_ms=int(payload["requested_delay_ms"]),
                applied_delay_ms=int(payload["applied_delay_ms"]),
                response_metadata=payload["response_metadata"],
            )
            artifact = PersistedArtifact(path, payload, True)
            pair = (attempt, artifact)
            attempt_pairs.append(pair)
            attempts_by_id[str(payload["attempt_id"])] = pair
        attempt_pairs.sort(key=lambda item: (item[0].page_ordinal, item[0].attempt_ordinal))

        capture_payloads = [
            (path, load_artifact(path))
            for path in (session_root / "02_captures").glob("*.capture.json")
        ]
        capture_payloads.sort(key=lambda item: int(item[1]["page_ordinal"]))
        if not capture_payloads:
            raise OperationalValidationError("simulated_partial_capture_required")
        source.reset()
        pages: list[CapturedPage] = []
        capture_artifacts: list[PersistedArtifact] = []
        continuation = "root"
        for path, payload in capture_payloads:
            page_ordinal = int(payload["page_ordinal"])
            request = SimulatedOperationalRequest(
                source_instance_id=source.script.source_instance_id,
                page_ordinal=page_ordinal,
                continuation=continuation,
            )
            attempt_id = str(payload["attempt"]["attempt_id"])
            attempt_pair = attempts_by_id.get(attempt_id)
            if attempt_pair is None or attempt_pair[0].outcome != "success":
                raise OperationalValidationError(
                    "simulated_partial_success_attempt_missing"
                )
            attempt, _attempt_artifact = attempt_pair
            body_path = safe_artifact_path(
                session_root, str(payload["response_body"]["path"])
            )
            outcome = SimulatedTransportOutcome(
                outcome="success",
                status_code=attempt.status_code,
                elapsed_ms=0,
                response_body=body_path.read_bytes(),
                response_metadata=attempt.response_metadata,
            )
            page = source.assess_response(
                request=request,
                outcome=outcome,
                attempt_ordinal=attempt.attempt_ordinal,
                captured_at=str(payload["captured_at"]),
            )
            expected_observations = sorted(
                [
                    {
                        "record_type": item.record_type,
                        "protected_source_record_id": item.protected_source_record_id,
                        "content_hash": item.content_hash,
                        "observation_id": item.observation_id,
                    }
                    for item in page.observations
                ],
                key=lambda item: str(item["observation_id"]),
            )
            if (
                page.request_fingerprint != payload["request_fingerprint"]
                or page.continuation_hash != payload["continuation_hash"]
                or page.response_schema != payload["response_schema"]
                or page.media_type != payload["media_type"]
                or page.terminal is not payload["terminal"]
                or thaw_json(page.next_continuation) != payload["next_continuation"]
                or thaw_json(page.response_metadata) != payload["response_metadata"]
                or expected_observations != payload["observations"]
            ):
                raise OperationalValidationError(
                    "simulated_partial_capture_semantics_mismatch"
                )
            pages.append(page)
            capture_artifacts.append(PersistedArtifact(path, payload, True))
            next_request = source.next_request(page)
            continuation = "" if next_request is None else next_request.continuation
        if next_request is None:
            raise OperationalValidationError("simulated_partial_must_be_nonterminal")
        recovered = PartialAcquisition(
            intent=intent,
            session_started_at=session_started_at,
            source_root=source_root,
            session_root=session_root,
            attempts=tuple(item[0] for item in attempt_pairs),
            pages=tuple(pages),
            attempt_artifacts=tuple(item[1] for item in attempt_pairs),
            capture_artifacts=tuple(capture_artifacts),
            next_request=next_request,
        )
        self.verify_partial(recovered)
        return recovered

    def run(
        self,
        *,
        intent: AcquisitionIntent,
        source: SimulatedRemoteInteractionSource,
        transport: SimulatedOperationalTransport,
        processor: GovernedProcessor,
        governed_run_root: str | Path,
        session_started_at: str,
        resume: PartialAcquisition | None = None,
        interrupt_after_pages: int | None = None,
    ) -> SimulatedExecutionResult:
        require_offset_timestamp(session_started_at, "simulated_session_started_at")
        source_root, session_root, intent_artifact, session_artifact = self._open_session(
            intent, session_started_at
        )
        session_id = str(session_artifact.payload["session_id"])
        valid: list[PersistedArtifact] = [intent_artifact, session_artifact]
        attempts: list[RequestAttempt] = []
        pages: list[CapturedPage] = []
        attempt_artifacts: list[PersistedArtifact] = []
        capture_artifacts: list[PersistedArtifact] = []
        request = source.initial_request(intent)
        if resume is not None:
            if resume.session_root != session_root or resume.intent != intent:
                raise OperationalValidationError("simulated_partial_resume_identity_mismatch")
            self.verify_partial(resume)
            attempts.extend(resume.attempts)
            pages.extend(resume.pages)
            attempt_artifacts.extend(resume.attempt_artifacts)
            capture_artifacts.extend(resume.capture_artifacts)
            valid.extend(attempt_artifacts)
            valid.extend(capture_artifacts)
            request = resume.next_request
            source.prime(pages)
        else:
            source.reset()
        self._inject("after_session")
        seen_continuations = {"root"}
        for page in pages:
            continuation = thaw_json(page.next_continuation)
            if continuation.get("kind") == "safe_simulated_cursor":
                seen_continuations.add(str(continuation["value"]))
        total_records = sum(len(page.observations) for page in pages)
        acquisition_elapsed_start = self.clock.elapsed_ms
        try:
            while request is not None:
                if request.page_ordinal > source.maximum_pages:
                    raise SimulatedPermanentFailure("simulated_maximum_page_bound_exhausted")
                outcome: SimulatedTransportOutcome | None = None
                success_attempt: RequestAttempt | None = None
                success_artifact: PersistedArtifact | None = None
                for attempt_ordinal in range(1, self.retry_policy.maximum_attempts + 1):
                    started_at = self.clock()
                    try:
                        outcome = transport.fetch(request)
                    except SimulatedTransportInterruption as exc:
                        self.clock.advance_ms(25)
                        attempt = RequestAttempt(
                            page_ordinal=request.page_ordinal,
                            attempt_ordinal=attempt_ordinal,
                            request_fingerprint=request.request_fingerprint,
                            continuation_hash=request.continuation_hash,
                            started_at=started_at,
                            completed_at=self.clock(),
                            outcome="retryable_failure",
                            status_code=None,
                            provider_error_code="simulated_transport_interruption",
                            response_metadata={"detail_omitted": True},
                        )
                        artifact = persist_attempt(
                            session_root, session_id=session_id, attempt=attempt
                        )
                        attempts.append(attempt)
                        attempt_artifacts.append(artifact)
                        valid.append(artifact)
                        self._persist_acquisition_failure(
                            session_root=session_root,
                            session_id=session_id,
                            stage="transport_interruption",
                            exc=exc,
                            valid=valid,
                        )
                        partial = PartialAcquisition(
                            intent=intent,
                            session_started_at=session_started_at,
                            source_root=source_root,
                            session_root=session_root,
                            attempts=tuple(attempts),
                            pages=tuple(pages),
                            attempt_artifacts=tuple(attempt_artifacts),
                            capture_artifacts=tuple(capture_artifacts),
                            next_request=request,
                        )
                        raise SimulatedAcquisitionInterrupted(
                            "simulated_transport_interruption", partial
                        ) from exc
                    self.clock.advance_ms(outcome.elapsed_ms)
                    if outcome.outcome == "success":
                        attempt = RequestAttempt(
                            page_ordinal=request.page_ordinal,
                            attempt_ordinal=attempt_ordinal,
                            request_fingerprint=request.request_fingerprint,
                            continuation_hash=request.continuation_hash,
                            started_at=started_at,
                            completed_at=self.clock(),
                            outcome="success",
                            status_code=outcome.status_code,
                            response_metadata=thaw_json(outcome.response_metadata),
                        )
                        artifact = persist_attempt(
                            session_root, session_id=session_id, attempt=attempt
                        )
                        attempts.append(attempt)
                        attempt_artifacts.append(artifact)
                        valid.append(artifact)
                        self._inject("after_attempt_persist")
                        success_attempt = attempt
                        success_artifact = artifact
                        break
                    persisted_outcome = (
                        outcome.outcome
                        if outcome.outcome in {"rate_limited", "retryable_failure", "permanent_failure"}
                        else "permanent_failure"
                    )
                    delay = 0
                    if persisted_outcome in self.retry_policy.retryable_outcomes:
                        delay = self.retry_policy.delay_ms(
                            request_fingerprint=request.request_fingerprint,
                            attempt_ordinal=attempt_ordinal,
                            retry_after_ms=outcome.retry_after_ms,
                        )
                    attempt = RequestAttempt(
                        page_ordinal=request.page_ordinal,
                        attempt_ordinal=attempt_ordinal,
                        request_fingerprint=request.request_fingerprint,
                        continuation_hash=request.continuation_hash,
                        started_at=started_at,
                        completed_at=self.clock(),
                        outcome=persisted_outcome,
                        status_code=outcome.status_code,
                        provider_error_code=outcome.provider_error_code,
                        requested_delay_ms=delay,
                        applied_delay_ms=delay,
                        response_metadata=thaw_json(outcome.response_metadata),
                    )
                    artifact = persist_attempt(session_root, session_id=session_id, attempt=attempt)
                    attempts.append(attempt)
                    attempt_artifacts.append(artifact)
                    valid.append(artifact)
                    self._inject("after_attempt_persist")
                    if persisted_outcome not in self.retry_policy.retryable_outcomes:
                        raise SimulatedPermanentFailure("simulated_permanent_transport_failure")
                    if attempt_ordinal >= self.retry_policy.maximum_attempts:
                        raise SimulatedRetryExhausted("simulated_retry_attempts_exhausted")
                    elapsed = self.clock.elapsed_ms - acquisition_elapsed_start
                    if elapsed + delay > self.retry_policy.maximum_elapsed_ms:
                        raise SimulatedRetryExhausted("simulated_retry_elapsed_bound_exhausted")
                    self.clock.advance_ms(delay)
                if outcome is None or success_attempt is None or success_artifact is None:
                    raise SimulatedRetryExhausted("simulated_success_not_reached")
                try:
                    page = source.assess_response(
                        request=request,
                        outcome=outcome,
                        attempt_ordinal=success_attempt.attempt_ordinal,
                        captured_at=self.clock(),
                    )
                except Exception as exc:
                    malformed = RequestAttempt(
                        page_ordinal=request.page_ordinal,
                        attempt_ordinal=success_attempt.attempt_ordinal + 1,
                        request_fingerprint=request.request_fingerprint,
                        continuation_hash=request.continuation_hash,
                        started_at=self.clock(),
                        completed_at=self.clock(),
                        outcome="malformed_response",
                        status_code=outcome.status_code,
                        provider_error_code="simulated_response_rejected",
                        response_metadata={"detail_omitted": True},
                    )
                    artifact = persist_attempt(session_root, session_id=session_id, attempt=malformed)
                    attempts.append(malformed)
                    attempt_artifacts.append(artifact)
                    valid.append(artifact)
                    raise exc
                total_records += len(page.observations)
                if total_records > source.maximum_records:
                    raise SimulatedPermanentFailure("simulated_maximum_record_bound_exhausted")
                self._inject("before_capture_persist")
                capture = persist_capture(
                    session_root,
                    session_id=session_id,
                    page=page,
                    successful_attempt=success_artifact,
                    previous_capture=(capture_artifacts[-1] if capture_artifacts else None),
                )
                pages.append(page)
                capture_artifacts.append(capture)
                valid.append(capture)
                self._inject("after_capture_persist")
                next_request = source.next_request(page)
                if next_request is not None:
                    if next_request.continuation in seen_continuations:
                        raise SimulatedPermanentFailure("simulated_pagination_cycle")
                    seen_continuations.add(next_request.continuation)
                if interrupt_after_pages is not None and len(pages) == interrupt_after_pages:
                    if next_request is None:
                        raise OperationalValidationError("simulated_interrupt_requires_nonterminal_page")
                    exc = SimulatedTransportInterruption("simulated_interruption_after_capture")
                    self._persist_acquisition_failure(
                        session_root=session_root,
                        session_id=session_id,
                        stage="partial_capture_interruption",
                        exc=exc,
                        valid=valid,
                    )
                    raise SimulatedAcquisitionInterrupted(
                        "simulated_interruption_after_capture",
                        PartialAcquisition(
                            intent=intent,
                            session_started_at=session_started_at,
                            source_root=source_root,
                            session_root=session_root,
                            attempts=tuple(attempts),
                            pages=tuple(pages),
                            attempt_artifacts=tuple(attempt_artifacts),
                            capture_artifacts=tuple(capture_artifacts),
                            next_request=next_request,
                        ),
                    )
                request = next_request
            kernel = OperationalIngestionKernel(
                self.store_root,
                clock=self.clock,
                failure_injector=self.kernel_failure_injector,
            )
            ingestion = kernel.run_from_captured_pages(
                intent=intent,
                session_started_at=session_started_at,
                transport_kind=SIMULATED_TRANSPORT_KIND,
                mode=SIMULATED_MODE,
                attempts=tuple(attempts),
                pages=tuple(pages),
                processor=processor,
                governed_run_root=governed_run_root,
            )
            return SimulatedExecutionResult(
                ingestion=ingestion,
                attempts=tuple(attempts),
                pages=tuple(pages),
                retry_count=sum(1 for item in attempts if item.outcome != "success"),
                requested_delay_ms=sum(item.requested_delay_ms for item in attempts),
            )
        except SimulatedAcquisitionInterrupted:
            raise
        except Exception as exc:
            self._persist_acquisition_failure(
                session_root=session_root,
                session_id=session_id,
                stage="simulated_acquisition",
                exc=exc,
                valid=valid,
            )
            raise


def simulated_policy_identity(policy_id: str, material: Mapping[str, Any]) -> PolicyIdentity:
    return PolicyIdentity(
        policy_id=policy_id,
        version="1.0.0",
        file_sha256=sha256_canonical(dict(material)),
    )


def build_simulated_intent(
    *,
    source_instance_id: str,
    retry_policy: RetryPolicy,
    prior_checkpoint: PersistedArtifact | None = None,
    upper_boundary: str = "terminal",
) -> AcquisitionIntent:
    require_text(source_instance_id, "simulated_intent_source_instance")
    adapter = simulated_policy_identity(
        "simulated_remote_interaction_source",
        {"source_type": "simulated_operational_relationship.v1", "version": "1.0.0"},
    )
    return AcquisitionIntent(
        source=SourceIdentity(
            source_type="simulated_operational_relationship.v1",
            source_instance_id=source_instance_id,
        ),
        adapter=adapter,
        acquisition_policy=simulated_policy_identity(
            "simulated_bounded_paginated_acquisition",
            {"coverage": "explicit_terminal", "version": "1.0.0"},
        ),
        assembly_policy=simulated_policy_identity(
            "simulated_canonical_observation_assembly",
            {"identity": "protected_key_plus_content_hash", "version": "1.0.0"},
        ),
        retry_policy=retry_policy.identity,
        secret_policy=simulated_policy_identity(
            "operational_secret_allowlist",
            {"success_body_scan": True, "raw_errors_persisted": False, "version": "1.0.0"},
        ),
        observation_boundary={
            "kind": "simulated_explicit_terminal_window",
            "lower": (
                "root"
                if prior_checkpoint is None
                else str(prior_checkpoint.payload["checkpoint_id"])
            ),
            "upper": upper_boundary,
        },
        credential_profile_ref="protected-simulated-credential-profile-v1",
        authentication_mode="injected_fixture",
        prior_checkpoint_id=(
            None if prior_checkpoint is None else str(prior_checkpoint.payload["checkpoint_id"])
        ),
        prior_checkpoint_hash=(
            None if prior_checkpoint is None else str(prior_checkpoint.payload["artifact_hash"])
        ),
    )
