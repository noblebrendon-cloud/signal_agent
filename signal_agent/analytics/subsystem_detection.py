from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Any


_DENIED_STATUSES = {"denied", "failed", "held", "rejected"}
_MINIMUM_REPETITION = 3
_MAX_CANDIDATES = 20
_MAX_EVIDENCE_PER_CANDIDATE = 10
_PROVIDER_RETRY_FALLBACK_EVENTS = {
    "retry_attempt",
    "fallback_selected",
    "circuit_opened",
    "circuit_half_opened",
    "circuit_closed",
    "half_open_probe_failure",
    "provider_error",
    "provider_failed",
    "provider_failure",
    "provider_unavailable",
}
_NON_OK_RUN_STATUSES = {
    "contract_violation",
    "error",
    "failed",
    "partial_success",
    "rejected",
    "unsupported",
}
_PATTERN_PRIORITY = {
    "transition_denial": 0,
    "transition_source_operation": 1,
    "transition_pair": 2,
    "operator_workflow": 3,
    "event_log_workflow": 4,
    "provider_retry_fallback": 5,
}


def detect_subsystem_candidates(
    rows_by_source: Mapping[str, list[dict[str, Any]]],
    *,
    minimum_repetition: int = _MINIMUM_REPETITION,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows_by_source.get("transition_events", []):
        _add_transition_groups(groups, row)
    for row in rows_by_source.get("operator_runs", []):
        _add_operator_run_groups(groups, row)
    for row in rows_by_source.get("provider_events", []):
        _add_provider_event_groups(groups, row)
    for row in rows_by_source.get("event_log", []):
        _add_event_log_groups(groups, row)

    candidates = [
        _build_candidate(group)
        for group in groups.values()
        if _candidate_group_is_supported(group, minimum_repetition=minimum_repetition)
    ]
    candidates.sort(
        key=lambda candidate: (
            -candidate["confidence"],
            -int(candidate["repeated_pattern"]["repetition_count"]),
            _PATTERN_PRIORITY.get(candidate["repeated_pattern"]["pattern_type"], 99),
            candidate["name_guess"],
            candidate["repeated_pattern"]["key"],
        )
    )
    return _dedupe_candidates_by_evidence(candidates)[:_MAX_CANDIDATES]


def _add_transition_groups(groups: dict[tuple[str, str], dict[str, Any]], row: Mapping[str, Any]) -> None:
    status = _clean(row.get("status"), default="unknown")
    policy_result = row.get("policy_result")
    policy_allowed = policy_result.get("allowed") if isinstance(policy_result, Mapping) else None
    if status not in _DENIED_STATUSES and policy_allowed is not False:
        return

    explicit = _has_explicit_transition_classification(row)
    weak_legacy = _is_legacy_unknown_denial(row)
    if not explicit and not weak_legacy:
        return

    source_module = _clean(_first(row, "source_module", "module"), default="")
    source_operation = _clean(_first(row, "source_operation", "operation"), default="")
    state_from = _clean(_first(row, "state_from", "current_state"), default="")
    state_to = _clean(_first(row, "state_to", "attempted_state", "next_state"), default="")
    denial_category = _clean(row.get("denial_category"), default="")
    denial_reason = _clean(_first(row, "denial_reason", "reason"), default="")

    if source_module and source_operation:
        _add_group_row(
            groups,
            group_type="transition_source_operation",
            key=f"{source_module}:{source_operation}",
            row=row,
            explicit=explicit,
            context={
                "source_module": source_module,
                "source_operation": source_operation,
                "denial_category": denial_category or None,
                "denial_reason": denial_reason or None,
            },
        )

    if explicit and state_from and state_to:
        _add_group_row(
            groups,
            group_type="transition_pair",
            key=f"{state_from}->{state_to}",
            row=row,
            explicit=True,
            context={
                "state_from": state_from,
                "state_to": state_to,
                "denial_category": denial_category or None,
                "denial_reason": denial_reason or None,
            },
        )

    if explicit and denial_category and denial_reason:
        _add_group_row(
            groups,
            group_type="transition_denial",
            key=f"{denial_category}:{denial_reason}",
            row=row,
            explicit=True,
            context={
                "denial_category": denial_category,
                "denial_reason": denial_reason,
                "source_module": source_module or None,
                "source_operation": source_operation or None,
            },
        )


def _add_operator_run_groups(groups: dict[tuple[str, str], dict[str, Any]], row: Mapping[str, Any]) -> None:
    workflow_id = _workflow_id(row)
    if not workflow_id:
        return
    status = _clean(row.get("status"), default="unknown")
    _add_group_row(
        groups,
        group_type="operator_workflow",
        key=workflow_id,
        row=row,
        explicit=status in _NON_OK_RUN_STATUSES,
        context={
            "workflow_id": workflow_id,
            "status": status,
        },
    )


def _add_provider_event_groups(groups: dict[tuple[str, str], dict[str, Any]], row: Mapping[str, Any]) -> None:
    event_name = _clean(_first(row, "event", "event_type"), default="")
    if event_name not in _PROVIDER_RETRY_FALLBACK_EVENTS:
        return
    provider_id = _clean(row.get("provider_id"), default="unknown_provider")
    model_id = _clean(row.get("model_id"), default="unknown_model")
    _add_group_row(
        groups,
        group_type="provider_retry_fallback",
        key=f"{provider_id}:{model_id}",
        row=row,
        explicit=True,
        context={
            "provider_id": provider_id,
            "model_id": model_id,
            "event_name": event_name,
        },
    )


def _add_event_log_groups(groups: dict[tuple[str, str], dict[str, Any]], row: Mapping[str, Any]) -> None:
    workflow_id = _workflow_id(row)
    if not workflow_id:
        return
    event_type = _clean(_first(row, "event_type", "event"), default="")
    _add_group_row(
        groups,
        group_type="event_log_workflow",
        key=workflow_id,
        row=row,
        explicit=True,
        context={
            "workflow_id": workflow_id,
            "event_type": event_type or None,
        },
    )


def _add_group_row(
    groups: dict[tuple[str, str], dict[str, Any]],
    *,
    group_type: str,
    key: str,
    row: Mapping[str, Any],
    explicit: bool,
    context: Mapping[str, Any],
) -> None:
    group_key = (group_type, key)
    if group_key not in groups:
        groups[group_key] = {
            "group_type": group_type,
            "key": key,
            "rows": [],
            "explicit_count": 0,
            "weak_count": 0,
            "contexts": defaultdict(set),
        }
    group = groups[group_key]
    group["rows"].append(dict(row))
    if explicit:
        group["explicit_count"] += 1
    else:
        group["weak_count"] += 1
    contexts = group["contexts"]
    for context_key, value in context.items():
        if value is not None:
            contexts[context_key].add(str(value))


def _candidate_group_is_supported(group: Mapping[str, Any], *, minimum_repetition: int) -> bool:
    if not group.get("key"):
        return False
    if int(group.get("explicit_count", 0)) < minimum_repetition:
        return False
    return len(group.get("rows") or []) >= minimum_repetition


def _build_candidate(group: Mapping[str, Any]) -> dict[str, Any]:
    rows = sorted(group["rows"], key=_row_sort_key)
    explicit_rows = [row for row in rows if not _is_legacy_unknown_denial(row)]
    evidence_rows = explicit_rows[:_MAX_EVIDENCE_PER_CANDIDATE]
    contexts = group["contexts"]
    repeated_pattern = {
        "pattern_type": group["group_type"],
        "key": group["key"],
        "repetition_count": int(group["explicit_count"]),
        "weak_legacy_evidence_count": int(group["weak_count"]),
        "distinct_evidence_surface_count": _distinct_evidence_surface_count(evidence_rows),
    }
    return {
        "candidate_id": _candidate_id(group),
        "name_guess": _name_guess(group),
        "evidence": [_evidence_reference(row) for row in evidence_rows],
        "repeated_pattern": repeated_pattern,
        "involved_files_or_events": [_event_reference(row) for row in evidence_rows],
        "confidence": _confidence(
            repetition_count=repeated_pattern["repetition_count"],
            distinct_evidence_surface_count=repeated_pattern["distinct_evidence_surface_count"],
        ),
        "recommended_next_action": _recommended_next_action(group, contexts),
    }


def _dedupe_candidates_by_evidence(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        signature = tuple(candidate.get("involved_files_or_events") or [])
        if signature in seen:
            continue
        selected.append(candidate)
        seen.add(signature)
    return selected


def _candidate_id(group: Mapping[str, Any]) -> str:
    group_type = str(group.get("group_type") or "unknown")
    key = str(group.get("key") or "unknown")
    token = hashlib.sha256(f"{group_type}|{key}".encode("utf-8")).hexdigest()[:16]
    return f"{_slug(group_type)}:{token}"


def _has_explicit_transition_classification(row: Mapping[str, Any]) -> bool:
    denial_reason = _clean(row.get("denial_reason"), default="")
    denial_category = _clean(row.get("denial_category"), default="")
    denial_subtype = _clean(row.get("denial_subtype"), default="")
    return bool(
        denial_category
        or denial_subtype
        or (denial_reason and denial_reason != "unknown_denial")
    )


def _is_legacy_unknown_denial(row: Mapping[str, Any]) -> bool:
    if _clean(row.get("__self_observation_source"), default="") != "transition_events":
        return False
    return (
        not row.get("denial_category")
        and not row.get("denial_subtype")
        and _clean(row.get("denial_reason"), default="") in {"", "unknown_denial"}
        and not _clean(row.get("reason"), default="")
    )


def _workflow_id(row: Mapping[str, Any]) -> str:
    payload = row.get("payload")
    return _clean(
        row.get("workflow_id")
        or row.get("target_workflow_id")
        or (payload.get("workflow_id") if isinstance(payload, Mapping) else None),
        default="",
    )


def _name_guess(group: Mapping[str, Any]) -> str:
    group_type = str(group.get("group_type") or "")
    key = str(group.get("key") or "")
    contexts = group.get("contexts") or {}
    denial_categories = contexts.get("denial_category", set())
    denial_reasons = contexts.get("denial_reason", set())

    if "app.governor.activation_governor" in key:
        return "activation_governor_review_flow"
    if key == "intake_append_and_stage_session" or "intake_stage" in key:
        return "intake_stage_session_flow"
    if "duplicate_protection" in denial_categories or "duplicate_record_detected" in denial_reasons:
        return "duplicate_record_protection_flow"
    if group_type == "provider_retry_fallback":
        return "provider_retry_fallback_flow"
    if group_type in {"operator_workflow", "event_log_workflow"}:
        return f"{_slug(key)}_flow"
    if group_type == "transition_pair":
        return f"{_slug(key.replace('->', '_to_'))}_transition_candidate"
    return f"{_slug(key)}_candidate_flow"


def _recommended_next_action(group: Mapping[str, Any], contexts: Mapping[str, Any]) -> str:
    group_type = str(group.get("group_type") or "")
    if group_type == "provider_retry_fallback":
        return "Review provider retry/fallback evidence; do not mutate routing or provider policy from this report."
    if group_type in {"operator_workflow", "event_log_workflow"}:
        return "Review repeated workflow evidence and operator ergonomics; do not change workflow definitions from this report."
    return "Review the observed candidate evidence; do not change governance state or policy from this report."


def _confidence(*, repetition_count: int, distinct_evidence_surface_count: int) -> float:
    score = 0.35
    score += 0.10 * min(int(repetition_count), 5)
    score += 0.10 * int(distinct_evidence_surface_count)
    return round(min(score, 0.95), 2)


def _distinct_evidence_surface_count(rows: list[Mapping[str, Any]]) -> int:
    return len({_clean(row.get("__self_observation_source"), default="unknown_source") for row in rows})


def _evidence_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "source": _clean(row.get("__self_observation_source"), default="unknown_source"),
        "line_number": row.get("__self_observation_line_number"),
        "line_sha256": row.get("__self_observation_line_sha256"),
    }
    for output_key, fields in (
        ("event_type", ("event_type", "event")),
        ("source_module", ("source_module", "module")),
        ("source_operation", ("source_operation", "operation")),
        ("denial_category", ("denial_category",)),
        ("denial_reason", ("denial_reason", "reason")),
        ("denial_subtype", ("denial_subtype",)),
        ("state_from", ("state_from", "current_state")),
        ("state_to", ("state_to", "attempted_state", "next_state")),
        ("workflow_id", ("workflow_id", "target_workflow_id")),
        ("run_id", ("run_id",)),
        ("artifact_id", ("artifact_id",)),
        ("request_id", ("request_id",)),
        ("provider_id", ("provider_id",)),
        ("model_id", ("model_id",)),
    ):
        value = _first(row, *fields)
        if value is not None:
            evidence[output_key] = value
    return evidence


def _event_reference(row: Mapping[str, Any]) -> str:
    source = _clean(row.get("__self_observation_source"), default="unknown_source")
    line_number = row.get("__self_observation_line_number")
    line_sha = _clean(row.get("__self_observation_line_sha256"), default="")
    if line_number is not None and line_sha:
        return f"{source}:line={line_number}:sha256={line_sha[:16]}"
    for field in ("run_id", "request_id", "artifact_id", "event_type", "event"):
        value = _clean(row.get(field), default="")
        if value:
            return f"{source}:{field}={value}"
    return f"{source}:unreferenced"


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str, str]:
    return (
        _clean(row.get("__self_observation_source"), default="unknown_source"),
        int(row.get("__self_observation_line_number") or 0),
        _clean(row.get("__self_observation_line_sha256"), default=""),
        _clean(_first(row, "run_id", "request_id", "artifact_id"), default=""),
    )


def _first(row: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return value
    return None


def _clean(value: Any, *, default: str) -> str:
    text = str(value or "").strip()
    return text if text else default


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug[:80] or "observed"
