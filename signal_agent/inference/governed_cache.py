from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

import yaml

from app.utils.io_contract import append_jsonl_atomic
from shared.events import emit_event


CACHE_DECISION_SCHEMA_VERSION = 1

REASON_POLICY_DISABLED = "policy_disabled"
REASON_WORKFLOW_NOT_ALLOWED = "workflow_not_allowed"
REASON_WRITE_MODE_BLOCKED = "write_mode_blocked"
REASON_THRESHOLD_NOT_MET = "threshold_not_met"
REASON_TTL_EXPIRED = "ttl_expired"
REASON_ARTIFACT_MISMATCH = "artifact_mismatch"
REASON_VALIDATOR_MISMATCH = "validator_mismatch"
REASON_MODEL_MISMATCH = "model_mismatch"
REASON_PREFIX_FINGERPRINT_MISMATCH = "prefix_fingerprint_mismatch"
REASON_PAYLOAD_VALIDATION_FAILED = "payload_validation_failed"
REASON_CONSTRAINT_PACK_MISMATCH = "constraint_pack_mismatch"
REASON_NO_CANDIDATE_FOUND = "no_candidate_found"
REASON_MISSING_STATIC_PREFIX = "missing_static_prefix"
REASON_ENTRY_TOO_LARGE = "entry_too_large"

OUTCOME_BYPASSED = "bypassed"
OUTCOME_CANDIDATE = "candidate"
OUTCOME_ELIGIBLE = "eligible"
OUTCOME_HIT = "hit"
OUTCOME_INELIGIBLE = "ineligible"
OUTCOME_MISS = "miss"
OUTCOME_NOT_ATTEMPTED = "not_attempted"
OUTCOME_REJECTED = "rejected"

TTL_STATUS_EXPIRED = "expired"
TTL_STATUS_FRESH = "fresh"
TTL_STATUS_NOT_APPLICABLE = "not_applicable"

FRESHNESS_STATUS_STALE = "stale"
FRESHNESS_STATUS_FRESH = "fresh"
FRESHNESS_STATUS_NOT_APPLICABLE = "not_applicable"

ARTIFACT_CONTINUITY_MATCHED = "matched"
ARTIFACT_CONTINUITY_MISMATCH = "mismatch"
ARTIFACT_CONTINUITY_NOT_REQUESTED = "not_requested"
ARTIFACT_CONTINUITY_ENTRY_UNSCOPED = "entry_unscoped"
ARTIFACT_CONTINUITY_NOT_APPLICABLE = "not_applicable"

VALIDATION_STATUS_NOT_ATTEMPTED = "not_attempted"
VALIDATION_STATUS_PENDING = "pending"
VALIDATION_STATUS_VALIDATED = "validated"
VALIDATION_STATUS_REJECTED = "rejected"

_PRIMARY_REASON_PRIORITY = {
    REASON_CONSTRAINT_PACK_MISMATCH: 0,
    REASON_PAYLOAD_VALIDATION_FAILED: 1,
    REASON_ARTIFACT_MISMATCH: 2,
    REASON_VALIDATOR_MISMATCH: 3,
    REASON_MODEL_MISMATCH: 4,
    REASON_PREFIX_FINGERPRINT_MISMATCH: 5,
    REASON_TTL_EXPIRED: 6,
    REASON_THRESHOLD_NOT_MET: 7,
    REASON_NO_CANDIDATE_FOUND: 999,
}


def _get_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def stable_json_dumps(payload: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        default=str,
    )


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_payload(payload: Any) -> str:
    return fingerprint_text(stable_json_dumps(payload, ensure_ascii=True))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_query_text(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(tokens)


def _prompt_part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    return stable_json_dumps(part, ensure_ascii=False)


def _compact_payload_size(payload: Any) -> int:
    return len(stable_json_dumps(payload, ensure_ascii=False).encode("utf-8"))


def _entry_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    return str(entry.get("created_at") or ""), str(entry.get("entry_id") or "")


def _reason_priority(reason_code: str | None) -> int:
    if not reason_code:
        return 10_000
    return _PRIMARY_REASON_PRIORITY.get(reason_code, 5_000)


def _normalize_policy_reason(reason: str) -> str:
    mapping = {
        "semantic_cache_disabled": REASON_POLICY_DISABLED,
        "missing_workflow_id": REASON_WORKFLOW_NOT_ALLOWED,
        "workflow_disallowed": REASON_WORKFLOW_NOT_ALLOWED,
        "workflow_not_allowlisted": REASON_WORKFLOW_NOT_ALLOWED,
        "write_mode_excluded": REASON_WRITE_MODE_BLOCKED,
        "allowed": "",
    }
    return mapping.get(reason, reason or REASON_POLICY_DISABLED)


def _normalize_validation_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    if normalized in {"validated", "allowed", "hit_validated"}:
        return ""
    if normalized in {
        REASON_CONSTRAINT_PACK_MISMATCH,
        REASON_MODEL_MISMATCH,
        REASON_ARTIFACT_MISMATCH,
        REASON_VALIDATOR_MISMATCH,
        REASON_PREFIX_FINGERPRINT_MISMATCH,
        REASON_PAYLOAD_VALIDATION_FAILED,
    }:
        return normalized
    return REASON_PAYLOAD_VALIDATION_FAILED


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    entries.append(row)
    except OSError:
        return []
    return entries


@dataclass(frozen=True)
class PromptEnvelope:
    prefix_text: str
    suffix_text: str
    full_prompt: str
    prefix_fingerprint: str
    prompt_fingerprint: str
    prefix_cache_eligible: bool
    ineligible_reason: str | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        static_prefix_parts: Sequence[Any] = (),
        dynamic_suffix_parts: Sequence[Any] = (),
        separator: str = "\n\n",
    ) -> "PromptEnvelope":
        prefix_parts = tuple(_prompt_part_text(part) for part in static_prefix_parts)
        suffix_parts = tuple(_prompt_part_text(part) for part in dynamic_suffix_parts)

        prefix_text = separator.join(part for part in prefix_parts if part != "")
        suffix_text = separator.join(part for part in suffix_parts if part != "")
        if prefix_text and suffix_text:
            full_prompt = f"{prefix_text}{separator}{suffix_text}"
        else:
            full_prompt = prefix_text or suffix_text

        eligible = bool(prefix_text.strip())
        reason = None if eligible else REASON_MISSING_STATIC_PREFIX
        return cls(
            prefix_text=prefix_text,
            suffix_text=suffix_text,
            full_prompt=full_prompt,
            prefix_fingerprint=fingerprint_text(prefix_text) if prefix_text else "",
            prompt_fingerprint=fingerprint_text(full_prompt),
            prefix_cache_eligible=eligible,
            ineligible_reason=reason,
        )

    @classmethod
    def from_full_prompt(cls, prompt_text: str) -> "PromptEnvelope":
        return cls.from_parts(dynamic_suffix_parts=(prompt_text,))


@dataclass(frozen=True)
class InferenceCachePolicy:
    version: int = 1
    policy_id: str = "inference_cache_policy"
    status: str = "inactive"
    enable_prefix_cache_readiness: bool = False
    enable_semantic_cache: bool = False
    semantic_similarity_threshold: float = 1.0
    cache_ttl: int = 0
    max_cache_entry_size: int = 0
    allowed_workflows_for_reuse: tuple[str, ...] = ()
    disallowed_workflows_for_reuse: tuple[str, ...] = ()
    exclude_write_mode_workflows_from_semantic_reuse: bool = True

    @classmethod
    def load(cls, policy_path: Path | str) -> "InferenceCachePolicy":
        path = Path(policy_path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            return cls()

        return cls(
            version=int(raw.get("version", 1)),
            policy_id=str(raw.get("policy_id", "inference_cache_policy")),
            status=str(raw.get("status", "inactive")),
            enable_prefix_cache_readiness=bool(raw.get("enable_prefix_cache_readiness", False)),
            enable_semantic_cache=bool(raw.get("enable_semantic_cache", False)),
            semantic_similarity_threshold=float(raw.get("semantic_similarity_threshold", 1.0)),
            cache_ttl=int(raw.get("cache_ttl", 0)),
            max_cache_entry_size=int(raw.get("max_cache_entry_size", 0)),
            allowed_workflows_for_reuse=tuple(
                str(item) for item in raw.get("allowed_workflows_for_reuse", ()) or ()
            ),
            disallowed_workflows_for_reuse=tuple(
                str(item) for item in raw.get("disallowed_workflows_for_reuse", ()) or ()
            ),
            exclude_write_mode_workflows_from_semantic_reuse=bool(
                raw.get("exclude_write_mode_workflows_from_semantic_reuse", True)
            ),
        )

    def allows_semantic_reuse(
        self,
        *,
        workflow_id: str,
        workflow_mode: str,
    ) -> tuple[bool, str]:
        if not self.enable_semantic_cache:
            return False, REASON_POLICY_DISABLED
        if not workflow_id:
            return False, REASON_WORKFLOW_NOT_ALLOWED
        if workflow_id in self.disallowed_workflows_for_reuse:
            return False, REASON_WORKFLOW_NOT_ALLOWED
        if (
            self.exclude_write_mode_workflows_from_semantic_reuse
            and workflow_mode == "write"
        ):
            return False, REASON_WRITE_MODE_BLOCKED
        if workflow_id not in self.allowed_workflows_for_reuse:
            return False, REASON_WORKFLOW_NOT_ALLOWED
        return True, ""


@dataclass(frozen=True)
class InferenceRequestContext:
    workflow_id: str
    workflow_mode: str = "read_only"
    artifact_id: str = ""
    model_id: str = ""
    operation: str = ""
    request_id: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class CacheDecision:
    cache_kind: str
    outcome: str
    reason_code: str | None = None
    matched_entry_id: str = ""
    similarity: float | None = None
    similarity_threshold: float | None = None
    prefix_cache_eligible: bool = False
    prefix_fingerprint: str = ""
    prompt_fingerprint: str = ""
    semantic_reuse_attempted: bool = False
    policy_blocked: bool = False
    artifact_continuity_status: str = ARTIFACT_CONTINUITY_NOT_APPLICABLE
    ttl_status: str = TTL_STATUS_NOT_APPLICABLE
    freshness_status: str = FRESHNESS_STATUS_NOT_APPLICABLE
    validator_id: str = ""
    validation_status: str = VALIDATION_STATUS_NOT_ATTEMPTED
    candidate_count: int = 0
    query_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision_schema_version": CACHE_DECISION_SCHEMA_VERSION,
            "cache_kind": self.cache_kind,
            "decision_outcome": self.outcome,
            "status": self.outcome,
            "reason_code": self.reason_code,
            "reason": self.reason_code,
            "semantic_reuse_attempted": self.semantic_reuse_attempted,
            "policy_blocked": self.policy_blocked,
            "prefix_cache_eligible": self.prefix_cache_eligible,
            "prefix_fingerprint": self.prefix_fingerprint or "",
            "prompt_fingerprint": self.prompt_fingerprint or "",
            "artifact_continuity_status": self.artifact_continuity_status,
            "ttl_status": self.ttl_status,
            "freshness_status": self.freshness_status,
            "validator_id": self.validator_id or "",
            "validation_status": self.validation_status,
            "candidate_count": self.candidate_count,
            "entry_id": self.matched_entry_id or "",
            "matched_entry_id": self.matched_entry_id or "",
        }
        if self.similarity is not None:
            payload["similarity"] = self.similarity
        if self.similarity_threshold is not None:
            payload["similarity_threshold"] = self.similarity_threshold
        if self.query_fingerprint:
            payload["query_fingerprint"] = self.query_fingerprint
        return payload


class EmbeddingProvider(Protocol):
    provider_id: str

    def embed(self, text: str) -> list[float]:
        ...


class DeterministicTokenEmbeddingProvider:
    provider_id = "deterministic_token_embedding_v1"

    def __init__(self, dimensions: int = 48) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        normalized = _normalize_query_text(text)
        if not normalized:
            return [0.0] * self.dimensions

        vector = [0.0] * self.dimensions
        for token in normalized.split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            return [0.0] * self.dimensions
        return [round(value / magnitude, 12) for value in vector]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return round(sum(a * b for a, b in zip(left, right)), 12)


ValidatorFn = Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]]


class GovernedInferenceCache:
    def __init__(
        self,
        *,
        repo_root: Path | str | None = None,
        policy_path: Path | str | None = None,
        registry_path: Path | str | None = None,
        event_log_path: Path | str | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repo_root = _get_root(repo_root)
        self.policy_path = Path(policy_path) if policy_path else (
            self.repo_root / "config" / "policies" / "inference_cache_policy.yaml"
        )
        self.registry_path = Path(registry_path) if registry_path else (
            self.repo_root / "data" / "state" / "inference_cache_registry.jsonl"
        )
        self.event_log_path = Path(event_log_path) if event_log_path else (
            self.repo_root / "data" / "state" / "event_log.jsonl"
        )
        self.policy = InferenceCachePolicy.load(self.policy_path)
        self.embedding_provider = embedding_provider or DeterministicTokenEmbeddingProvider()

    def _event_artifact_id(
        self,
        context: InferenceRequestContext,
        envelope: PromptEnvelope | None = None,
    ) -> str:
        if context.artifact_id:
            return context.artifact_id
        if context.workflow_id:
            return context.workflow_id
        if envelope is not None and envelope.prompt_fingerprint:
            return envelope.prompt_fingerprint[:16]
        return "inference_cache"

    def _emit(
        self,
        event_type: str,
        context: InferenceRequestContext,
        payload: dict[str, Any],
        envelope: PromptEnvelope | None = None,
    ) -> None:
        base_payload = {
            "workflow_id": context.workflow_id,
            "workflow_mode": context.workflow_mode,
            "artifact_id": context.artifact_id or None,
            "model_id": context.model_id or None,
            "operation": context.operation or None,
            "request_id": context.request_id or None,
            "run_id": context.run_id or None,
        }
        if envelope is not None:
            base_payload.update(
                {
                    "prompt_fingerprint": envelope.prompt_fingerprint,
                    "prefix_fingerprint": envelope.prefix_fingerprint or None,
                    "prefix_cache_eligible": envelope.prefix_cache_eligible,
                }
            )
        base_payload.update(payload)
        emit_event(
            event_type,
            self._event_artifact_id(context, envelope),
            base_payload,
            event_log_path=self.event_log_path,
        )

    def _emit_decision(
        self,
        event_type: str,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        decision: CacheDecision,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = decision.to_dict()
        if extra:
            payload.update(extra)
        self._emit(event_type, context, payload, envelope=envelope)

    def _prefix_decision(self, *, envelope: PromptEnvelope) -> CacheDecision:
        if not self.policy.enable_prefix_cache_readiness:
            return CacheDecision(
                cache_kind="prefix_cache_readiness",
                outcome=OUTCOME_BYPASSED,
                reason_code=REASON_POLICY_DISABLED,
                prefix_cache_eligible=False,
                prefix_fingerprint="",
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=False,
                policy_blocked=True,
            )
        if not envelope.prefix_cache_eligible:
            return CacheDecision(
                cache_kind="prefix_cache_readiness",
                outcome=OUTCOME_INELIGIBLE,
                reason_code=envelope.ineligible_reason or REASON_MISSING_STATIC_PREFIX,
                prefix_cache_eligible=False,
                prefix_fingerprint="",
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=False,
            )
        return CacheDecision(
            cache_kind="prefix_cache_readiness",
            outcome=OUTCOME_ELIGIBLE,
            reason_code=None,
            prefix_cache_eligible=True,
            prefix_fingerprint=envelope.prefix_fingerprint,
            prompt_fingerprint=envelope.prompt_fingerprint,
            semantic_reuse_attempted=False,
        )

    def assess_prefix_cache(
        self,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
    ) -> dict[str, Any]:
        decision = self._prefix_decision(envelope=envelope)
        if decision.outcome == OUTCOME_BYPASSED:
            self._emit_decision(
                "cache_bypassed_by_policy",
                context=context,
                envelope=envelope,
                decision=decision,
            )
        elif decision.outcome == OUTCOME_INELIGIBLE:
            self._emit_decision(
                "prefix_cache_ineligible",
                context=context,
                envelope=envelope,
                decision=decision,
            )
        else:
            extra = {"prefix_length_chars": len(envelope.prefix_text)}
            self._emit_decision(
                "prefix_cache_eligible",
                context=context,
                envelope=envelope,
                decision=decision,
                extra=extra,
            )
            self._emit_decision(
                "prefix_cache_fingerprint_created",
                context=context,
                envelope=envelope,
                decision=decision,
                extra=extra,
            )
        result = decision.to_dict()
        result["eligible"] = decision.outcome == OUTCOME_ELIGIBLE
        return result

    def _workflow_entries(
        self,
        *,
        context: InferenceRequestContext,
    ) -> list[dict[str, Any]]:
        entries = _load_jsonl(self.registry_path)
        relevant: list[dict[str, Any]] = []
        for entry in entries:
            if entry.get("record_type") != "semantic_cache_entry":
                continue
            if entry.get("workflow_id") != context.workflow_id:
                continue
            relevant.append(entry)
        relevant.sort(key=_entry_sort_key)
        return relevant

    def _artifact_continuity_status(
        self,
        *,
        context_artifact_id: str,
        entry_artifact_id: str,
    ) -> str:
        if not context_artifact_id:
            return ARTIFACT_CONTINUITY_NOT_REQUESTED
        if not entry_artifact_id:
            return ARTIFACT_CONTINUITY_ENTRY_UNSCOPED
        if entry_artifact_id == context_artifact_id:
            return ARTIFACT_CONTINUITY_MATCHED
        return ARTIFACT_CONTINUITY_MISMATCH

    def _candidate_trace(
        self,
        *,
        entry: dict[str, Any],
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        validator_id: str,
        now_dt: datetime,
        query_vector: Sequence[float] | None,
    ) -> dict[str, Any]:
        entry_id = str(entry.get("entry_id") or "")
        entry_artifact_id = str(entry.get("artifact_id") or "")
        artifact_status = self._artifact_continuity_status(
            context_artifact_id=context.artifact_id,
            entry_artifact_id=entry_artifact_id,
        )

        trace: dict[str, Any] = {
            "entry_id": entry_id,
            "artifact_id": entry_artifact_id,
            "model_id": str(entry.get("model_id") or ""),
            "validator_id": str(entry.get("validator_id") or ""),
            "prefix_fingerprint": str(entry.get("prefix_fingerprint") or ""),
            "embedding_provider": str(entry.get("embedding_provider") or ""),
            "artifact_continuity_status": artifact_status,
            "ttl_status": TTL_STATUS_NOT_APPLICABLE,
            "freshness_status": FRESHNESS_STATUS_NOT_APPLICABLE,
            "reason_code": None,
            "similarity": None,
            "validation_status": VALIDATION_STATUS_NOT_ATTEMPTED,
            "outcome": "filtered",
            "created_at": str(entry.get("created_at") or ""),
            "expires_at": str(entry.get("expires_at") or ""),
        }

        if entry.get("workflow_mode") == "write":
            trace["reason_code"] = REASON_WRITE_MODE_BLOCKED
            return trace
        if str(entry.get("validator_id") or "") != validator_id:
            trace["reason_code"] = REASON_VALIDATOR_MISMATCH
            return trace
        if context.model_id and str(entry.get("model_id") or "") != context.model_id:
            trace["reason_code"] = REASON_MODEL_MISMATCH
            return trace
        if envelope.prefix_fingerprint and str(entry.get("prefix_fingerprint") or "") != envelope.prefix_fingerprint:
            trace["reason_code"] = REASON_PREFIX_FINGERPRINT_MISMATCH
            return trace
        if artifact_status == ARTIFACT_CONTINUITY_MISMATCH:
            trace["reason_code"] = REASON_ARTIFACT_MISMATCH
            return trace
        if str(entry.get("embedding_provider") or "") != self.embedding_provider.provider_id:
            trace["reason_code"] = REASON_NO_CANDIDATE_FOUND
            return trace

        expires_at = _parse_utc(str(entry.get("expires_at") or ""))
        if expires_at is not None and expires_at < now_dt:
            trace["reason_code"] = REASON_TTL_EXPIRED
            trace["ttl_status"] = TTL_STATUS_EXPIRED
            trace["freshness_status"] = FRESHNESS_STATUS_STALE
            trace["outcome"] = "expired"
            return trace

        trace["ttl_status"] = TTL_STATUS_FRESH
        trace["freshness_status"] = FRESHNESS_STATUS_FRESH
        if query_vector is not None:
            trace["similarity"] = _cosine_similarity(query_vector, entry.get("embedding_vector", []))
        trace["outcome"] = "eligible"
        return trace

    def _primary_reason(self, traces: Sequence[dict[str, Any]]) -> str:
        reasons = [
            str(trace.get("reason_code") or "")
            for trace in traces
            if trace.get("reason_code")
        ]
        if not reasons:
            return REASON_NO_CANDIDATE_FOUND
        return sorted(reasons, key=_reason_priority)[0]

    def _artifact_status_from_traces(
        self,
        traces: Sequence[dict[str, Any]],
        *,
        context: InferenceRequestContext,
    ) -> str:
        if not context.artifact_id:
            return ARTIFACT_CONTINUITY_NOT_REQUESTED
        for trace in traces:
            status = str(trace.get("artifact_continuity_status") or "")
            if status == ARTIFACT_CONTINUITY_MATCHED:
                return status
        for trace in traces:
            status = str(trace.get("artifact_continuity_status") or "")
            if status:
                return status
        return ARTIFACT_CONTINUITY_NOT_APPLICABLE

    def _ttl_status_from_traces(self, traces: Sequence[dict[str, Any]]) -> str:
        for trace in traces:
            if trace.get("ttl_status") == TTL_STATUS_FRESH:
                return TTL_STATUS_FRESH
        for trace in traces:
            if trace.get("ttl_status") == TTL_STATUS_EXPIRED:
                return TTL_STATUS_EXPIRED
        return TTL_STATUS_NOT_APPLICABLE

    def _freshness_status_from_ttl(self, ttl_status: str) -> str:
        if ttl_status == TTL_STATUS_FRESH:
            return FRESHNESS_STATUS_FRESH
        if ttl_status == TTL_STATUS_EXPIRED:
            return FRESHNESS_STATUS_STALE
        return FRESHNESS_STATUS_NOT_APPLICABLE

    def _semantic_bypass_decision(
        self,
        *,
        envelope: PromptEnvelope,
        validator_id: str,
        reason_code: str,
    ) -> CacheDecision:
        return CacheDecision(
            cache_kind="semantic_reuse",
            outcome=OUTCOME_BYPASSED,
            reason_code=reason_code,
            prefix_cache_eligible=envelope.prefix_cache_eligible,
            prefix_fingerprint=envelope.prefix_fingerprint,
            prompt_fingerprint=envelope.prompt_fingerprint,
            semantic_reuse_attempted=False,
            policy_blocked=True,
            validator_id=validator_id,
        )

    def _semantic_no_attempt_decision(
        self,
        *,
        envelope: PromptEnvelope,
        validator_id: str,
    ) -> CacheDecision:
        return CacheDecision(
            cache_kind="semantic_reuse",
            outcome=OUTCOME_NOT_ATTEMPTED,
            reason_code=None,
            prefix_cache_eligible=envelope.prefix_cache_eligible,
            prefix_fingerprint=envelope.prefix_fingerprint,
            prompt_fingerprint=envelope.prompt_fingerprint,
            semantic_reuse_attempted=False,
            validator_id=validator_id,
        )

    def _evaluate_semantic_reuse(
        self,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        normalized_query: str,
        validator_id: str,
        validator: ValidatorFn,
        validation_context: dict[str, Any] | None = None,
        now_utc: str | None = None,
        emit_events: bool,
    ) -> tuple[dict[str, Any] | None, CacheDecision, list[dict[str, Any]]]:
        allowed, reason = self.policy.allows_semantic_reuse(
            workflow_id=context.workflow_id,
            workflow_mode=context.workflow_mode,
        )
        reason_code = _normalize_policy_reason(reason)
        if not allowed:
            decision = self._semantic_bypass_decision(
                envelope=envelope,
                validator_id=validator_id,
                reason_code=reason_code,
            )
            if emit_events:
                self._emit_decision(
                    "cache_bypassed_by_policy",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            return None, decision, []

        query_text = _normalize_query_text(normalized_query)
        query_fingerprint = fingerprint_text(query_text) if query_text else ""
        if not query_text:
            decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_MISS,
                reason_code=REASON_NO_CANDIDATE_FOUND,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                validator_id=validator_id,
                candidate_count=0,
                query_fingerprint=query_fingerprint,
            )
            if emit_events:
                self._emit_decision(
                    "semantic_cache_miss",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            return None, decision, []

        query_vector = self.embedding_provider.embed(query_text)
        threshold = self.policy.semantic_similarity_threshold
        now_dt = _parse_utc(now_utc or _now_utc_iso()) or datetime.now(timezone.utc)
        validation_payload = dict(validation_context or {})

        traces: list[dict[str, Any]] = []
        eligible_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        workflow_entries = self._workflow_entries(context=context)
        for entry in workflow_entries:
            trace = self._candidate_trace(
                entry=entry,
                context=context,
                envelope=envelope,
                validator_id=validator_id,
                now_dt=now_dt,
                query_vector=query_vector,
            )
            traces.append(trace)
            if trace.get("reason_code") == REASON_TTL_EXPIRED and emit_events:
                expired_decision = CacheDecision(
                    cache_kind="semantic_reuse",
                    outcome=OUTCOME_MISS,
                    reason_code=REASON_TTL_EXPIRED,
                    matched_entry_id=str(trace.get("entry_id") or ""),
                    prefix_cache_eligible=envelope.prefix_cache_eligible,
                    prefix_fingerprint=envelope.prefix_fingerprint,
                    prompt_fingerprint=envelope.prompt_fingerprint,
                    semantic_reuse_attempted=True,
                    policy_blocked=False,
                    artifact_continuity_status=str(trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                    ttl_status=TTL_STATUS_EXPIRED,
                    freshness_status=FRESHNESS_STATUS_STALE,
                    validator_id=validator_id,
                    validation_status=VALIDATION_STATUS_NOT_ATTEMPTED,
                    candidate_count=len(workflow_entries),
                    query_fingerprint=query_fingerprint,
                )
                self._emit_decision(
                    "cache_entry_expired",
                    context=context,
                    envelope=envelope,
                    decision=expired_decision,
                    extra={"expires_at": trace.get("expires_at")},
                )
            if trace.get("outcome") == "eligible":
                eligible_candidates.append(
                    (
                        float(trace.get("similarity") or 0.0),
                        entry,
                        trace,
                    )
                )

        if not eligible_candidates:
            primary_reason = self._primary_reason(traces)
            ttl_status = self._ttl_status_from_traces(traces)
            decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_MISS,
                reason_code=primary_reason,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                artifact_continuity_status=self._artifact_status_from_traces(traces, context=context),
                ttl_status=ttl_status,
                freshness_status=self._freshness_status_from_ttl(ttl_status),
                validator_id=validator_id,
                validation_status=VALIDATION_STATUS_NOT_ATTEMPTED,
                candidate_count=len(traces),
                query_fingerprint=query_fingerprint,
                similarity_threshold=threshold,
            )
            if emit_events:
                self._emit_decision(
                    "semantic_cache_miss",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            return None, decision, traces

        eligible_candidates.sort(
            key=lambda item: (
                -item[0],
                *_entry_sort_key(item[1]),
            ),
        )
        best_similarity, best_entry, best_trace = eligible_candidates[0]
        if best_similarity < threshold:
            decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_MISS,
                reason_code=REASON_THRESHOLD_NOT_MET,
                matched_entry_id=str(best_entry.get("entry_id") or ""),
                similarity=best_similarity,
                similarity_threshold=threshold,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                artifact_continuity_status=str(best_trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                ttl_status=str(best_trace.get("ttl_status") or TTL_STATUS_NOT_APPLICABLE),
                freshness_status=str(best_trace.get("freshness_status") or FRESHNESS_STATUS_NOT_APPLICABLE),
                validator_id=validator_id,
                validation_status=VALIDATION_STATUS_NOT_ATTEMPTED,
                candidate_count=len(eligible_candidates),
                query_fingerprint=query_fingerprint,
            )
            if emit_events:
                self._emit_decision(
                    "semantic_cache_miss",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            return None, decision, traces

        rejections: list[tuple[CacheDecision, dict[str, Any]]] = []
        for score, entry, trace in eligible_candidates:
            if score < threshold:
                break
            candidate_decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_CANDIDATE,
                reason_code=None,
                matched_entry_id=str(entry.get("entry_id") or ""),
                similarity=score,
                similarity_threshold=threshold,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                artifact_continuity_status=str(trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                ttl_status=TTL_STATUS_FRESH,
                freshness_status=FRESHNESS_STATUS_FRESH,
                validator_id=validator_id,
                validation_status=VALIDATION_STATUS_PENDING,
                candidate_count=len(eligible_candidates),
                query_fingerprint=query_fingerprint,
            )
            if emit_events:
                self._emit_decision(
                    "semantic_cache_candidate_found",
                    context=context,
                    envelope=envelope,
                    decision=candidate_decision,
                )

            is_valid, validation_reason = validator(entry, validation_payload)
            normalized_validation_reason = _normalize_validation_reason(validation_reason)
            if is_valid:
                decision = CacheDecision(
                    cache_kind="semantic_reuse",
                    outcome=OUTCOME_HIT,
                    reason_code=None,
                    matched_entry_id=str(entry.get("entry_id") or ""),
                    similarity=score,
                    similarity_threshold=threshold,
                    prefix_cache_eligible=envelope.prefix_cache_eligible,
                    prefix_fingerprint=envelope.prefix_fingerprint,
                    prompt_fingerprint=envelope.prompt_fingerprint,
                    semantic_reuse_attempted=True,
                    policy_blocked=False,
                    artifact_continuity_status=str(trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                    ttl_status=TTL_STATUS_FRESH,
                    freshness_status=FRESHNESS_STATUS_FRESH,
                    validator_id=validator_id,
                    validation_status=VALIDATION_STATUS_VALIDATED,
                    candidate_count=len(eligible_candidates),
                    query_fingerprint=query_fingerprint,
                )
                if emit_events:
                    self._emit_decision(
                        "semantic_cache_hit_validated",
                        context=context,
                        envelope=envelope,
                        decision=decision,
                    )
                payload = entry.get("response_payload")
                return (dict(payload) if isinstance(payload, dict) else None), decision, traces

            decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_REJECTED,
                reason_code=normalized_validation_reason or REASON_PAYLOAD_VALIDATION_FAILED,
                matched_entry_id=str(entry.get("entry_id") or ""),
                similarity=score,
                similarity_threshold=threshold,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                artifact_continuity_status=str(trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                ttl_status=TTL_STATUS_FRESH,
                freshness_status=FRESHNESS_STATUS_FRESH,
                validator_id=validator_id,
                validation_status=VALIDATION_STATUS_REJECTED,
                candidate_count=len(eligible_candidates),
                query_fingerprint=query_fingerprint,
            )
            trace["reason_code"] = decision.reason_code
            trace["validation_status"] = VALIDATION_STATUS_REJECTED
            trace["outcome"] = OUTCOME_REJECTED
            if emit_events:
                self._emit_decision(
                    "semantic_cache_hit_rejected",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            rejections.append((decision, trace))

        if rejections:
            rejected_decision, rejected_trace = rejections[0]
            decision = CacheDecision(
                cache_kind="semantic_reuse",
                outcome=OUTCOME_MISS,
                reason_code=rejected_decision.reason_code,
                matched_entry_id=rejected_decision.matched_entry_id,
                similarity=rejected_decision.similarity,
                similarity_threshold=threshold,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=True,
                policy_blocked=False,
                artifact_continuity_status=str(rejected_trace.get("artifact_continuity_status") or ARTIFACT_CONTINUITY_NOT_APPLICABLE),
                ttl_status=TTL_STATUS_FRESH,
                freshness_status=FRESHNESS_STATUS_FRESH,
                validator_id=validator_id,
                validation_status=VALIDATION_STATUS_REJECTED,
                candidate_count=len(eligible_candidates),
                query_fingerprint=query_fingerprint,
            )
            if emit_events:
                self._emit_decision(
                    "semantic_cache_miss",
                    context=context,
                    envelope=envelope,
                    decision=decision,
                )
            return None, decision, traces

        decision = CacheDecision(
            cache_kind="semantic_reuse",
            outcome=OUTCOME_MISS,
            reason_code=REASON_NO_CANDIDATE_FOUND,
            prefix_cache_eligible=envelope.prefix_cache_eligible,
            prefix_fingerprint=envelope.prefix_fingerprint,
            prompt_fingerprint=envelope.prompt_fingerprint,
            semantic_reuse_attempted=True,
            policy_blocked=False,
            validator_id=validator_id,
            candidate_count=len(eligible_candidates),
            query_fingerprint=query_fingerprint,
            similarity_threshold=threshold,
        )
        if emit_events:
            self._emit_decision(
                "semantic_cache_miss",
                context=context,
                envelope=envelope,
                decision=decision,
            )
        return None, decision, traces

    def lookup_semantic_reuse(
        self,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        normalized_query: str,
        validator_id: str,
        validator: ValidatorFn,
        validation_context: dict[str, Any] | None = None,
        now_utc: str | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        payload, decision, _ = self._evaluate_semantic_reuse(
            context=context,
            envelope=envelope,
            normalized_query=normalized_query,
            validator_id=validator_id,
            validator=validator,
            validation_context=validation_context,
            now_utc=now_utc,
            emit_events=True,
        )
        return payload, decision.to_dict()

    def inspect_inference_cache_status(
        self,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        normalized_query: str | None = None,
        validator_id: str = "",
        validator: ValidatorFn | None = None,
        validation_context: dict[str, Any] | None = None,
        now_utc: str | None = None,
    ) -> dict[str, Any]:
        prefix_decision = self._prefix_decision(envelope=envelope)
        if normalized_query is None or validator is None or not validator_id:
            semantic_decision = self._semantic_no_attempt_decision(
                envelope=envelope,
                validator_id=validator_id,
            )
            traces: list[dict[str, Any]] = []
        else:
            _, semantic_decision, traces = self._evaluate_semantic_reuse(
                context=context,
                envelope=envelope,
                normalized_query=normalized_query,
                validator_id=validator_id,
                validator=validator,
                validation_context=validation_context,
                now_utc=now_utc,
                emit_events=False,
            )

        result = {
            "workflow_id": context.workflow_id,
            "workflow_mode": context.workflow_mode,
            "artifact_id": context.artifact_id,
            "model_id": context.model_id,
            "prefix_cache_eligible": prefix_decision.outcome == OUTCOME_ELIGIBLE,
            "prefix_outcome": prefix_decision.outcome,
            "prefix_reason_code": prefix_decision.reason_code,
            "prefix_fingerprint": prefix_decision.prefix_fingerprint,
            "prompt_fingerprint": prefix_decision.prompt_fingerprint,
            "semantic_reuse_attempted": semantic_decision.semantic_reuse_attempted,
            "outcome": semantic_decision.outcome,
            "status": semantic_decision.outcome,
            "reason_code": semantic_decision.reason_code,
            "reason": semantic_decision.reason_code,
            "matched_cache_entry_id": semantic_decision.matched_entry_id,
            "entry_id": semantic_decision.matched_entry_id,
            "artifact_continuity_status": semantic_decision.artifact_continuity_status,
            "ttl_status": semantic_decision.ttl_status,
            "freshness_status": semantic_decision.freshness_status,
            "policy_blocked": semantic_decision.policy_blocked,
            "validator_id": validator_id,
            "candidate_count": semantic_decision.candidate_count,
            "decision_schema_version": CACHE_DECISION_SCHEMA_VERSION,
            "candidate_traces": traces,
        }
        if semantic_decision.similarity is not None:
            result["similarity"] = semantic_decision.similarity
        if semantic_decision.similarity_threshold is not None:
            result["similarity_threshold"] = semantic_decision.similarity_threshold
        return result

    def explain_cache_decision(self, **kwargs: Any) -> dict[str, Any]:
        return self.inspect_inference_cache_status(**kwargs)

    def write_semantic_entry(
        self,
        *,
        context: InferenceRequestContext,
        envelope: PromptEnvelope,
        normalized_query: str,
        response_payload: dict[str, Any],
        validator_id: str,
        validation_metadata: dict[str, Any] | None = None,
        now_utc: str | None = None,
    ) -> dict[str, Any] | None:
        allowed, reason = self.policy.allows_semantic_reuse(
            workflow_id=context.workflow_id,
            workflow_mode=context.workflow_mode,
        )
        if not allowed:
            decision = self._semantic_bypass_decision(
                envelope=envelope,
                validator_id=validator_id,
                reason_code=_normalize_policy_reason(reason),
            )
            self._emit_decision(
                "cache_bypassed_by_policy",
                context=context,
                envelope=envelope,
                decision=decision,
                extra={"cache_kind": "semantic_reuse_write"},
            )
            return None

        query_text = _normalize_query_text(normalized_query)
        if not query_text:
            decision = CacheDecision(
                cache_kind="semantic_reuse_write",
                outcome=OUTCOME_BYPASSED,
                reason_code=REASON_NO_CANDIDATE_FOUND,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=False,
                policy_blocked=False,
                validator_id=validator_id,
            )
            self._emit_decision(
                "cache_bypassed_by_policy",
                context=context,
                envelope=envelope,
                decision=decision,
            )
            return None

        created_at = now_utc or _now_utc_iso()
        created_dt = _parse_utc(created_at) or datetime.now(timezone.utc)
        expires_at = (created_dt + timedelta(seconds=max(self.policy.cache_ttl, 0))).isoformat().replace("+00:00", "Z")
        normalized_query_fp = fingerprint_text(query_text)
        response_fingerprint = fingerprint_payload(response_payload)
        entry_id = fingerprint_text(
            "|".join(
                [
                    context.workflow_id,
                    context.artifact_id,
                    context.model_id,
                    envelope.prefix_fingerprint,
                    normalized_query_fp,
                    response_fingerprint,
                    validator_id,
                ]
            )
        )[:24]

        entry = {
            "record_type": "semantic_cache_entry",
            "record_version": "1",
            "entry_id": entry_id,
            "workflow_id": context.workflow_id,
            "workflow_mode": context.workflow_mode,
            "artifact_id": context.artifact_id,
            "model_id": context.model_id,
            "operation": context.operation,
            "created_at": created_at,
            "expires_at": expires_at,
            "prefix_fingerprint": envelope.prefix_fingerprint,
            "prompt_fingerprint": envelope.prompt_fingerprint,
            "normalized_query": query_text,
            "normalized_query_fingerprint": normalized_query_fp,
            "embedding_provider": self.embedding_provider.provider_id,
            "embedding_vector": self.embedding_provider.embed(query_text),
            "validator_id": validator_id,
            "validation_metadata": dict(validation_metadata or {}),
            "response_payload": dict(response_payload),
            "response_fingerprint": response_fingerprint,
        }
        entry_size = _compact_payload_size(entry)
        if self.policy.max_cache_entry_size and entry_size > self.policy.max_cache_entry_size:
            decision = CacheDecision(
                cache_kind="semantic_reuse_write",
                outcome=OUTCOME_BYPASSED,
                reason_code=REASON_ENTRY_TOO_LARGE,
                prefix_cache_eligible=envelope.prefix_cache_eligible,
                prefix_fingerprint=envelope.prefix_fingerprint,
                prompt_fingerprint=envelope.prompt_fingerprint,
                semantic_reuse_attempted=False,
                policy_blocked=False,
                validator_id=validator_id,
            )
            self._emit_decision(
                "cache_bypassed_by_policy",
                context=context,
                envelope=envelope,
                decision=decision,
                extra={
                    "entry_size": entry_size,
                    "max_cache_entry_size": self.policy.max_cache_entry_size,
                },
            )
            return None

        append_jsonl_atomic(self.registry_path, entry)
        decision = CacheDecision(
            cache_kind="semantic_reuse_write",
            outcome=OUTCOME_ELIGIBLE,
            reason_code=None,
            matched_entry_id=entry_id,
            prefix_cache_eligible=envelope.prefix_cache_eligible,
            prefix_fingerprint=envelope.prefix_fingerprint,
            prompt_fingerprint=envelope.prompt_fingerprint,
            semantic_reuse_attempted=False,
            policy_blocked=False,
            artifact_continuity_status=self._artifact_continuity_status(
                context_artifact_id=context.artifact_id,
                entry_artifact_id=context.artifact_id,
            ),
            ttl_status=TTL_STATUS_FRESH,
            freshness_status=FRESHNESS_STATUS_FRESH,
            validator_id=validator_id,
            validation_status=VALIDATION_STATUS_VALIDATED,
            candidate_count=1,
            query_fingerprint=normalized_query_fp,
        )
        self._emit_decision(
            "cache_entry_written",
            context=context,
            envelope=envelope,
            decision=decision,
            extra={
                "expires_at": expires_at,
                "entry_size": entry_size,
            },
        )
        return entry


def inspect_inference_cache_status(
    *,
    context: InferenceRequestContext,
    envelope: PromptEnvelope,
    normalized_query: str | None = None,
    validator_id: str = "",
    validator: ValidatorFn | None = None,
    validation_context: dict[str, Any] | None = None,
    now_utc: str | None = None,
    cache: GovernedInferenceCache | None = None,
    repo_root: Path | str | None = None,
    policy_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    event_log_path: Path | str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    resolved_cache = cache or GovernedInferenceCache(
        repo_root=repo_root,
        policy_path=policy_path,
        registry_path=registry_path,
        event_log_path=event_log_path,
        embedding_provider=embedding_provider,
    )
    return resolved_cache.inspect_inference_cache_status(
        context=context,
        envelope=envelope,
        normalized_query=normalized_query,
        validator_id=validator_id,
        validator=validator,
        validation_context=validation_context,
        now_utc=now_utc,
    )


def explain_cache_decision(**kwargs: Any) -> dict[str, Any]:
    return inspect_inference_cache_status(**kwargs)
