from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


_DENIED_STATUSES = {"denied", "failed", "held", "rejected"}
_NON_OK_RUN_STATUSES = {
    "contract_violation",
    "error",
    "failed",
    "partial_success",
    "rejected",
    "unsupported",
}
_PROVIDER_FAILURE_EVENTS = {
    "call_error",
    "call_failed",
    "half_open_probe_failure",
    "provider_error",
    "provider_failed",
    "provider_unavailable",
}
_CIRCUIT_EVENTS = {
    "circuit_opened",
    "circuit_half_opened",
    "circuit_closed",
    "half_open_probe_failure",
}


def build_metrics(
    rows_by_source: Mapping[str, list[dict[str, Any]]],
    *,
    repo_root: Path,
    source_paths: Mapping[str, Path],
    last_n_events: int | None = None,
) -> dict[str, Any]:
    transition_events = rows_by_source.get("transition_events", [])
    operator_runs = rows_by_source.get("operator_runs", [])
    provider_events = rows_by_source.get("provider_events", [])
    event_log = rows_by_source.get("event_log", [])

    transition_counts_by_status = Counter()
    transition_counts_by_pair = Counter()
    policy_denials_by_reason = Counter()
    transition_denials_by_module_operation = Counter()
    rejection_evidence_quality_counts = Counter()
    denial_reasons_by_evidence_quality: dict[str, Counter[str]] = defaultdict(Counter)
    denial_categories_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    policy_denial_count = 0

    for row in transition_events:
        status = _normalize_key(row.get("status"), default="unknown")
        transition_counts_by_status[status] += 1

        current_state = _normalize_key(row.get("current_state"), default="missing")
        attempted_state = _normalize_key(row.get("attempted_state"), default="missing")
        transition_counts_by_pair[f"{current_state}->{attempted_state}"] += 1

        policy_result = row.get("policy_result")
        policy_allowed = (
            policy_result.get("allowed")
            if isinstance(policy_result, dict)
            else None
        )
        denied = status in _DENIED_STATUSES or policy_allowed is False
        if denied:
            policy_denial_count += 1
            evidence_quality = _rejection_evidence_quality(row)
            rejection_evidence_quality_counts[evidence_quality] += 1
            reasons = _denial_reasons(row)
            for reason in reasons:
                policy_denials_by_reason[reason] += 1
                denial_reasons_by_evidence_quality[evidence_quality][reason] += 1
            if evidence_quality == "explicit_classification":
                category = _normalize_key(row.get("denial_category"), default="unknown")
                source_key = _classification_source_key(row)
                denial_categories_by_source[source_key][category] += 1
            module = _normalize_key(row.get("module"), default="unknown_module")
            operation = _normalize_key(row.get("operation"), default="unknown_operation")
            transition_denials_by_module_operation[f"{module}:{operation}"] += 1

    operator_run_counts_by_status = Counter(
        _normalize_key(row.get("status"), default="unknown")
        for row in operator_runs
    )
    workflow_invocation_counts = Counter(
        _workflow_id(row)
        for row in operator_runs
    )

    operator_failures_by_workflow = Counter()
    for row in operator_runs:
        status = _normalize_key(row.get("status"), default="unknown")
        if status in _NON_OK_RUN_STATUSES:
            operator_failures_by_workflow[_workflow_id(row)] += 1

    provider_retry_count = 0
    provider_fallback_count = 0
    circuit_breaker_count = 0
    provider_failures_by_model = Counter()
    provider_event_counts_by_type = Counter()

    for row in provider_events:
        event_name = _normalize_key(row.get("event"), default="")
        if not event_name:
            event_name = _normalize_key(row.get("event_type"), default="unknown")
        provider_event_counts_by_type[event_name] += 1
        if event_name == "retry_attempt":
            provider_retry_count += 1
        if event_name == "fallback_selected":
            provider_fallback_count += 1
        if event_name in _CIRCUIT_EVENTS:
            circuit_breaker_count += 1
        if event_name in _PROVIDER_FAILURE_EVENTS:
            model_id = _normalize_key(row.get("model_id"), default="unknown_model")
            provider_id = _normalize_key(row.get("provider_id"), default="unknown_provider")
            provider_failures_by_model[f"{provider_id}:{model_id}"] += 1

    repeated_workflow_patterns = _top_patterns(
        workflow_invocation_counts,
        minimum_count=2,
        label_key="workflow_id",
    )
    repeated_failure_patterns = _repeated_failure_patterns(
        policy_denials_by_reason=policy_denials_by_reason,
        operator_failures_by_workflow=operator_failures_by_workflow,
        provider_failures_by_model=provider_failures_by_model,
    )
    high_friction_workflow_clusters = _high_friction_clusters(
        workflow_invocation_counts=workflow_invocation_counts,
        operator_failures_by_workflow=operator_failures_by_workflow,
        transition_denials_by_module_operation=transition_denials_by_module_operation,
    )

    return {
        "transition_counts_by_status": _sorted_counter(transition_counts_by_status),
        "transition_counts_by_pair": _sorted_counter(transition_counts_by_pair),
        "failed_transition_count": sum(
            count
            for status, count in transition_counts_by_status.items()
            if status in _DENIED_STATUSES
        ),
        "rejected_transition_count": policy_denial_count,
        "explicitly_classified_rejection_count": int(
            rejection_evidence_quality_counts["explicit_classification"]
        ),
        "legacy_fallback_rejection_count": int(
            rejection_evidence_quality_counts["legacy_reason"]
            + rejection_evidence_quality_counts["legacy_policy_failure"]
        ),
        "legacy_unknown_rejection_count": int(
            rejection_evidence_quality_counts["legacy_unknown"]
        ),
        "classification_coverage_ratio": _ratio(
            rejection_evidence_quality_counts["explicit_classification"],
            policy_denial_count,
        ),
        "rejection_evidence_quality_counts": _quality_counts(rejection_evidence_quality_counts),
        "denial_categories_by_source": _sorted_nested_counters(denial_categories_by_source),
        "denial_reasons_by_evidence_quality": _quality_nested_counters(
            denial_reasons_by_evidence_quality
        ),
        "policy_denial_count": policy_denial_count,
        "policy_denials_by_reason": _sorted_counter(policy_denials_by_reason),
        "operator_run_counts_by_status": _sorted_counter(operator_run_counts_by_status),
        "workflow_invocation_counts": _sorted_counter(workflow_invocation_counts),
        "provider_retry_count": provider_retry_count,
        "provider_fallback_count": provider_fallback_count,
        "circuit_breaker_count": circuit_breaker_count,
        "provider_failures_by_model": _sorted_counter(provider_failures_by_model),
        "provider_event_counts_by_type": _sorted_counter(provider_event_counts_by_type),
        "cache_summary": _cache_summary(
            repo_root=repo_root,
            source_paths=source_paths,
            event_log=event_log,
            cache_registry=rows_by_source.get("inference_cache_registry", []),
            last_n_events=last_n_events,
        ),
        "repeated_workflow_patterns": repeated_workflow_patterns,
        "repeated_failure_patterns": repeated_failure_patterns,
        "high_friction_workflow_clusters": high_friction_workflow_clusters,
    }


def _cache_summary(
    *,
    repo_root: Path,
    source_paths: Mapping[str, Path],
    event_log: list[dict[str, Any]],
    cache_registry: list[dict[str, Any]],
    last_n_events: int | None,
) -> dict[str, Any]:
    try:
        from signal_agent.inference import build_inference_cache_report
    except Exception as exc:
        return {
            "available": False,
            "reason": "inference_cache_audit_unavailable",
            "error": str(exc),
        }

    event_log_path = source_paths.get("event_log")
    registry_path = source_paths.get("inference_cache_registry")
    if event_log_path is None or registry_path is None:
        return {"available": False, "reason": "cache_source_paths_missing"}
    if not event_log_path.exists() and not registry_path.exists():
        return {"available": False, "reason": "cache_sources_missing"}

    try:
        cache_report = build_inference_cache_report(
            repo_root=repo_root,
            event_log_path=event_log_path,
            registry_path=registry_path,
            last_n_events=last_n_events,
            now_utc=_latest_observed_timestamp(event_log, cache_registry),
        )
    except Exception as exc:
        return {
            "available": False,
            "reason": "inference_cache_audit_failed",
            "error": str(exc),
        }

    return {
        "available": True,
        "report_version": cache_report.get("report_version"),
        "total_cache_related_events": int(cache_report.get("total_cache_related_events", 0)),
        "prefix_cache_eligible_count": int(cache_report.get("prefix_cache_eligible_count", 0)),
        "prefix_cache_ineligible_count": int(cache_report.get("prefix_cache_ineligible_count", 0)),
        "semantic_reuse_attempted_count": int(cache_report.get("semantic_reuse_attempted_count", 0)),
        "semantic_cache_hit_validated_count": int(cache_report.get("semantic_cache_hit_validated_count", 0)),
        "semantic_cache_hit_rejected_count": int(cache_report.get("semantic_cache_hit_rejected_count", 0)),
        "semantic_cache_miss_count": int(cache_report.get("semantic_cache_miss_count", 0)),
        "cache_entry_written_count": int(cache_report.get("cache_entry_written_count", 0)),
        "cache_entry_expired_count": int(cache_report.get("cache_entry_expired_count", 0)),
        "cache_bypassed_by_policy_count": int(cache_report.get("cache_bypassed_by_policy_count", 0)),
        "validated_hit_rate": cache_report.get("validated_hit_rate"),
        "registry_summary": dict(cache_report.get("registry_summary", {})),
    }


def _latest_observed_timestamp(
    event_log: list[dict[str, Any]],
    cache_registry: list[dict[str, Any]],
) -> str | None:
    timestamps: list[str] = []
    for row in event_log:
        for field in ("timestamp", "timestamp_utc", "created_at", "updated_at"):
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                timestamps.append(value.strip())
    for row in cache_registry:
        for field in ("created_at", "expires_at", "timestamp", "timestamp_utc"):
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                timestamps.append(value.strip())
    return max(timestamps) if timestamps else None


def _denial_reasons(row: Mapping[str, Any]) -> list[str]:
    denial_reason = row.get("denial_reason")
    if denial_reason:
        text = str(denial_reason).strip()
        if text:
            return [text]

    reason = row.get("reason")
    if reason:
        text = str(reason).strip()
        if text:
            return [text]

    reasons: list[str] = []
    policy_result = row.get("policy_result")
    if isinstance(policy_result, Mapping):
        failures = policy_result.get("failures")
        if isinstance(failures, list):
            reasons.extend(str(item) for item in failures if str(item).strip())
    if not reasons:
        reasons.append("unknown_denial")
    return sorted(set(reasons))


def _rejection_evidence_quality(row: Mapping[str, Any]) -> str:
    if _has_explicit_classification(row):
        return "explicit_classification"
    if _clean_text(row.get("reason")):
        return "legacy_reason"
    policy_result = row.get("policy_result")
    if isinstance(policy_result, Mapping):
        failures = policy_result.get("failures")
        if isinstance(failures, list) and any(_clean_text(item) for item in failures):
            return "legacy_policy_failure"
    return "legacy_unknown"


def _has_explicit_classification(row: Mapping[str, Any]) -> bool:
    denial_category = _clean_text(row.get("denial_category"))
    denial_subtype = _clean_text(row.get("denial_subtype"))
    denial_reason = _clean_text(row.get("denial_reason"))
    return bool(
        denial_category
        or denial_subtype
        or (denial_reason and denial_reason != "unknown_denial")
    )


def _classification_source_key(row: Mapping[str, Any]) -> str:
    module = _normalize_key(
        row.get("source_module") or row.get("module"),
        default="unknown_module",
    )
    operation = _normalize_key(
        row.get("source_operation") or row.get("operation"),
        default="unknown_operation",
    )
    return f"{module}:{operation}"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _workflow_id(row: Mapping[str, Any]) -> str:
    return _normalize_key(
        row.get("workflow_id") or row.get("target_workflow_id"),
        default="unknown_workflow",
    )


def _normalize_key(value: Any, *, default: str) -> str:
    text = str(value or "").strip()
    return text if text else default


def _sorted_counter(counter: Counter[str] | Mapping[str, int]) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0])))
    }


def _quality_counts(counter: Counter[str]) -> dict[str, int]:
    return {
        quality: int(counter.get(quality, 0))
        for quality in (
            "explicit_classification",
            "legacy_reason",
            "legacy_policy_failure",
            "legacy_unknown",
        )
    }


def _quality_nested_counters(counters: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        quality: _sorted_counter(counters.get(quality, Counter()))
        for quality in (
            "explicit_classification",
            "legacy_reason",
            "legacy_policy_failure",
            "legacy_unknown",
        )
    }


def _sorted_nested_counters(counters: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        str(key): _sorted_counter(value)
        for key, value in sorted(counters.items(), key=lambda item: str(item[0]))
    }


def _top_patterns(
    counter: Counter[str],
    *,
    minimum_count: int,
    label_key: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return [
        {label_key: key, "count": int(count)}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count >= minimum_count
    ][:limit]


def _repeated_failure_patterns(
    *,
    policy_denials_by_reason: Counter[str],
    operator_failures_by_workflow: Counter[str],
    provider_failures_by_model: Counter[str],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for reason, count in sorted(policy_denials_by_reason.items(), key=lambda item: (-item[1], item[0])):
        if count >= 2:
            patterns.append(
                {
                    "pattern_type": "policy_denial_reason",
                    "pattern": reason,
                    "count": int(count),
                }
            )
    for workflow_id, count in sorted(operator_failures_by_workflow.items(), key=lambda item: (-item[1], item[0])):
        if count >= 2:
            patterns.append(
                {
                    "pattern_type": "operator_failure_workflow",
                    "pattern": workflow_id,
                    "count": int(count),
                }
            )
    for model_key, count in sorted(provider_failures_by_model.items(), key=lambda item: (-item[1], item[0])):
        if count >= 2:
            patterns.append(
                {
                    "pattern_type": "provider_failure_model",
                    "pattern": model_key,
                    "count": int(count),
                }
            )
    return patterns[:20]


def _high_friction_clusters(
    *,
    workflow_invocation_counts: Counter[str],
    operator_failures_by_workflow: Counter[str],
    transition_denials_by_module_operation: Counter[str],
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for workflow_id, failure_count in sorted(operator_failures_by_workflow.items(), key=lambda item: (-item[1], item[0])):
        invocation_count = workflow_invocation_counts.get(workflow_id, 0)
        if failure_count <= 0:
            continue
        clusters.append(
            {
                "cluster_type": "workflow",
                "cluster_id": workflow_id,
                "failure_count": int(failure_count),
                "invocation_count": int(invocation_count),
                "friction_ratio": _ratio(failure_count, invocation_count),
            }
        )
    for module_operation, denial_count in sorted(transition_denials_by_module_operation.items(), key=lambda item: (-item[1], item[0])):
        clusters.append(
            {
                "cluster_type": "transition_module_operation",
                "cluster_id": module_operation,
                "failure_count": int(denial_count),
                "invocation_count": None,
                "friction_ratio": None,
            }
        )
    return clusters[:20]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)
