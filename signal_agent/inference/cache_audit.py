from __future__ import annotations

import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shared.event_reader import read_events


INFERENCE_CACHE_ACTIVITY_REPORT_VERSION = 1
INFERENCE_CACHE_ACTIVITY_RENDER_VERSION = 1
INFERENCE_CACHE_ACTIVITY_SNAPSHOT_VERSION = 1
INFERENCE_CACHE_ACTIVITY_DIFF_VERSION = 1

_REUSE_LOSS_REASON_GROUPS = {
    "reuse_loss_due_to_threshold": {"threshold_not_met"},
    "reuse_loss_due_to_prefix_mismatch": {
        "missing_static_prefix",
        "prefix_fingerprint_mismatch",
    },
    "reuse_loss_due_to_policy": {
        "entry_too_large",
        "policy_disabled",
        "workflow_not_allowed",
        "write_mode_blocked",
    },
    "reuse_loss_due_to_validation": {
        "artifact_mismatch",
        "constraint_pack_mismatch",
        "model_mismatch",
        "payload_validation_failed",
        "validator_mismatch",
    },
    "reuse_loss_due_to_ttl": {"ttl_expired"},
}

_DEFAULT_DIAGNOSTIC_CONFIG = {
    "prefix_instability_min_issue_count": 2,
    "prefix_instability_max_eligibility_ratio": 0.8,
    "semantic_threshold_too_strict_min_attempts": 3,
    "semantic_threshold_too_strict_min_ratio": 0.4,
    "validator_rejection_dominant_min_attempts": 3,
    "validator_rejection_dominant_min_ratio": 0.3,
    "cache_ttl_too_short_min_attempts": 3,
    "cache_ttl_too_short_min_ratio": 0.2,
    "policy_blocking_high_min_decisions": 3,
    "policy_blocking_high_min_ratio": 0.25,
}

_DEFAULT_EXPANSION_CONFIG = {
    "min_semantic_reuse_attempted_count": 3,
    "min_validated_hit_rate": 0.6,
    "max_rejection_rate": 0.2,
}

_CACHE_EVENT_TYPES = (
    "prefix_cache_eligible",
    "prefix_cache_ineligible",
    "prefix_cache_fingerprint_created",
    "semantic_cache_candidate_found",
    "semantic_cache_hit_validated",
    "semantic_cache_hit_rejected",
    "semantic_cache_miss",
    "cache_entry_written",
    "cache_entry_expired",
    "cache_bypassed_by_policy",
)

_EVENT_COUNT_FIELDS = {
    "prefix_cache_eligible": "prefix_cache_eligible_count",
    "prefix_cache_ineligible": "prefix_cache_ineligible_count",
    "semantic_cache_hit_validated": "semantic_cache_hit_validated_count",
    "semantic_cache_hit_rejected": "semantic_cache_hit_rejected_count",
    "semantic_cache_miss": "semantic_cache_miss_count",
    "cache_entry_written": "cache_entry_written_count",
    "cache_entry_expired": "cache_entry_expired_count",
    "cache_bypassed_by_policy": "cache_bypassed_by_policy_count",
}

_SEMANTIC_TERMINAL_EVENT_TYPES = {
    "semantic_cache_hit_validated",
    "semantic_cache_miss",
}

_TERMINAL_REASON_EVENT_TYPES = {
    "prefix_cache_ineligible",
    "semantic_cache_miss",
    "cache_bypassed_by_policy",
}

_CANDIDATE_REJECTION_EVENT_TYPES = {"semantic_cache_hit_rejected"}

_DEFAULT_WORKFLOW_ID = "unknown"

_TOP_LEVEL_COUNT_FIELDS = (
    "total_cache_related_events",
    "prefix_cache_eligible_count",
    "prefix_cache_ineligible_count",
    "semantic_reuse_attempted_count",
    "semantic_cache_hit_validated_count",
    "semantic_cache_hit_rejected_count",
    "semantic_cache_miss_count",
    "cache_entry_written_count",
    "cache_entry_expired_count",
    "cache_bypassed_by_policy_count",
    "policy_block_count",
)

_REGISTRY_COUNT_FIELDS = (
    "entries_in_scope",
    "active_entries",
    "expired_entries",
    "entries_with_unknown_freshness",
)

_RATIO_FIELDS = (
    "prefix_eligibility_ratio",
    "validated_hit_rate",
    "candidate_rejection_rate",
    "policy_blocking_ratio",
)

_REUSE_LOSS_FIELDS = (
    "reuse_loss_due_to_threshold",
    "reuse_loss_due_to_prefix_mismatch",
    "reuse_loss_due_to_policy",
    "reuse_loss_due_to_validation",
    "reuse_loss_due_to_ttl",
    "reuse_loss_total",
    "reuse_loss_uncategorized",
)

_REUSE_LOSS_SHORT_LABELS = {
    "reuse_loss_due_to_threshold": "threshold",
    "reuse_loss_due_to_prefix_mismatch": "prefix_mismatch",
    "reuse_loss_due_to_policy": "policy",
    "reuse_loss_due_to_validation": "validation",
    "reuse_loss_due_to_ttl": "ttl",
    "reuse_loss_total": "total",
    "reuse_loss_uncategorized": "uncategorized",
}

_WORKFLOW_DIFF_COUNT_FIELDS = _TOP_LEVEL_COUNT_FIELDS + ("registry_entries_in_scope",)
_EXPANSION_CANDIDATE_COUNT_FIELDS = (
    "semantic_reuse_attempted_count",
    "policy_block_count",
)
_EXPANSION_CANDIDATE_RATIO_FIELDS = (
    "validated_hit_rate",
    "candidate_rejection_rate",
)


def _get_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_registry_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get("record_type") != "semantic_cache_entry":
                    continue
                entries.append(payload)
    except OSError:
        return []
    return entries


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _workflow_id(event: dict[str, Any]) -> str:
    payload = _payload(event)
    workflow_id = str(payload.get("workflow_id") or "").strip()
    return workflow_id or _DEFAULT_WORKFLOW_ID


def _artifact_id(event: dict[str, Any]) -> str:
    payload = _payload(event)
    artifact_id = payload.get("artifact_id")
    if artifact_id is None:
        artifact_id = event.get("artifact_id")
    return str(artifact_id or "").strip()


def _event_timestamp(event: dict[str, Any]) -> datetime | None:
    return _parse_utc(str(event.get("timestamp") or ""))


def _registry_timestamp(entry: dict[str, Any]) -> datetime | None:
    created_at = _parse_utc(str(entry.get("created_at") or ""))
    if created_at is not None:
        return created_at
    return _parse_utc(str(entry.get("expires_at") or ""))


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _round_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _merge_config(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(defaults)
    if overrides:
        for key, value in overrides.items():
            merged[str(key)] = value
    return merged


def _derive_reuse_loss_categories(reason_counts: Counter[str] | dict[str, int]) -> dict[str, int]:
    categories = {
        "reuse_loss_due_to_threshold": 0,
        "reuse_loss_due_to_prefix_mismatch": 0,
        "reuse_loss_due_to_policy": 0,
        "reuse_loss_due_to_validation": 0,
        "reuse_loss_due_to_ttl": 0,
    }
    seen_reason_codes: set[str] = set()
    for category_name, reason_codes in _REUSE_LOSS_REASON_GROUPS.items():
        categories[category_name] = sum(int(reason_counts.get(reason_code, 0)) for reason_code in reason_codes)
        seen_reason_codes.update(reason_codes)
    categories["reuse_loss_uncategorized"] = sum(
        int(count)
        for reason_code, count in reason_counts.items()
        if reason_code not in seen_reason_codes
    )
    categories["reuse_loss_total"] = sum(int(count) for count in reason_counts.values())
    return categories


def _policy_blocking_ratio(policy_block_count: int, semantic_reuse_attempted_count: int) -> float | None:
    return _round_ratio(policy_block_count, policy_block_count + semantic_reuse_attempted_count)


def _candidate_rejection_rate(
    semantic_cache_hit_rejected_count: int,
    semantic_reuse_attempted_count: int,
) -> float | None:
    return _round_ratio(semantic_cache_hit_rejected_count, semantic_reuse_attempted_count)


def _prefix_issue_count(summary: dict[str, Any]) -> int:
    categories = summary.get("reuse_loss_categories", {})
    return int(summary.get("prefix_cache_ineligible_count", 0)) + int(
        categories.get("reuse_loss_due_to_prefix_mismatch", 0)
    )


def _initial_summary() -> dict[str, Any]:
    return {
        "total_cache_related_events": 0,
        "prefix_cache_eligible_count": 0,
        "prefix_cache_ineligible_count": 0,
        "semantic_reuse_attempted_count": 0,
        "semantic_cache_hit_validated_count": 0,
        "semantic_cache_hit_rejected_count": 0,
        "semantic_cache_miss_count": 0,
        "cache_entry_written_count": 0,
        "cache_entry_expired_count": 0,
        "cache_bypassed_by_policy_count": 0,
        "policy_block_count": 0,
    }


def _derive_reference_time(
    *,
    events: list[dict[str, Any]],
    registry_entries: list[dict[str, Any]],
    now_utc: str | None,
) -> datetime | None:
    if now_utc:
        return _parse_utc(now_utc)

    candidates: list[datetime] = []
    for event in events:
        parsed = _event_timestamp(event)
        if parsed is not None:
            candidates.append(parsed)
    for entry in registry_entries:
        parsed = _registry_timestamp(entry)
        if parsed is not None:
            candidates.append(parsed)
    if not candidates:
        return None
    return max(candidates)


def _event_in_scope(
    event: dict[str, Any],
    *,
    workflow_id: str | None,
    artifact_id: str | None,
    cutoff: datetime | None,
) -> bool:
    if str(event.get("event_type") or "") not in _CACHE_EVENT_TYPES:
        return False
    if workflow_id and _workflow_id(event) != workflow_id:
        return False
    if artifact_id and _artifact_id(event) != artifact_id:
        return False
    if cutoff is not None:
        timestamp = _event_timestamp(event)
        if timestamp is None or timestamp < cutoff:
            return False
    return True


def _entry_in_scope(
    entry: dict[str, Any],
    *,
    workflow_id: str | None,
    artifact_id: str | None,
    cutoff: datetime | None,
) -> bool:
    if workflow_id and str(entry.get("workflow_id") or "") != workflow_id:
        return False
    if artifact_id and str(entry.get("artifact_id") or "") != artifact_id:
        return False
    if cutoff is not None:
        created_at = _parse_utc(str(entry.get("created_at") or ""))
        if created_at is None or created_at < cutoff:
            return False
    return True


def _finalize_breakdown(
    event_counts: dict[str, Counter[str]],
    reason_counts: dict[str, Counter[str]],
    candidate_rejection_reason_counts: dict[str, Counter[str]],
    registry_entries_by_workflow: Counter[str],
    policy_block_counts_by_workflow: Counter[str],
) -> dict[str, dict[str, Any]]:
    workflows = set(event_counts) | set(registry_entries_by_workflow) | set(policy_block_counts_by_workflow)
    breakdown: dict[str, dict[str, Any]] = {}
    for workflow_id in sorted(workflows):
        counts = event_counts[workflow_id]
        summary = dict(_initial_summary())
        for event_type, field_name in _EVENT_COUNT_FIELDS.items():
            summary[field_name] = counts.get(event_type, 0)
        summary["total_cache_related_events"] = sum(counts.values())
        summary["semantic_reuse_attempted_count"] = (
            counts.get("semantic_cache_hit_validated", 0)
            + counts.get("semantic_cache_miss", 0)
        )
        summary["policy_block_count"] = policy_block_counts_by_workflow.get(workflow_id, 0)
        prefix_denominator = (
            summary["prefix_cache_eligible_count"]
            + summary["prefix_cache_ineligible_count"]
        )
        summary["prefix_eligibility_ratio"] = _round_ratio(
            summary["prefix_cache_eligible_count"],
            prefix_denominator,
        )
        summary["validated_hit_rate"] = _round_ratio(
            summary["semantic_cache_hit_validated_count"],
            summary["semantic_reuse_attempted_count"],
        )
        summary["candidate_rejection_rate"] = _candidate_rejection_rate(
            summary["semantic_cache_hit_rejected_count"],
            summary["semantic_reuse_attempted_count"],
        )
        summary["policy_blocking_ratio"] = _policy_blocking_ratio(
            summary["policy_block_count"],
            summary["semantic_reuse_attempted_count"],
        )
        summary["event_counts_by_type"] = {
            event_type: counts.get(event_type, 0)
            for event_type in _CACHE_EVENT_TYPES
            if counts.get(event_type, 0) > 0
        }
        summary["reason_code_counts"] = _sorted_counter(reason_counts[workflow_id])
        summary["candidate_rejection_reason_code_counts"] = _sorted_counter(
            candidate_rejection_reason_counts[workflow_id]
        )
        summary["reuse_loss_categories"] = _derive_reuse_loss_categories(reason_counts[workflow_id])
        summary["registry_entries_in_scope"] = registry_entries_by_workflow.get(workflow_id, 0)
        breakdown[workflow_id] = summary
    return breakdown


def _build_flag(
    *,
    triggered: bool,
    metric_name: str,
    metric_value: float | int | None,
    threshold: float | int,
    comparison: str,
    affected_workflows: list[str],
    supporting_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "triggered": bool(triggered),
        "metric_name": metric_name,
        "metric_value": metric_value,
        "threshold": threshold,
        "comparison": comparison,
        "affected_workflows": sorted(affected_workflows),
        "supporting_counts": {
            key: int(value)
            for key, value in sorted(supporting_counts.items())
        },
    }


def _build_diagnostics(
    *,
    report_summary: dict[str, Any],
    workflow_breakdown: dict[str, dict[str, Any]],
    diagnostic_config: dict[str, Any],
) -> dict[str, Any]:
    reuse_loss_categories = report_summary["reuse_loss_categories"]
    prefix_issue_count = _prefix_issue_count(report_summary)
    threshold_loss_ratio = _round_ratio(
        reuse_loss_categories["reuse_loss_due_to_threshold"],
        int(report_summary["semantic_reuse_attempted_count"]),
    )
    validation_loss_ratio = _round_ratio(
        reuse_loss_categories["reuse_loss_due_to_validation"],
        int(report_summary["semantic_reuse_attempted_count"]),
    )
    ttl_loss_ratio = _round_ratio(
        reuse_loss_categories["reuse_loss_due_to_ttl"],
        int(report_summary["semantic_reuse_attempted_count"]),
    )
    policy_blocking_ratio = report_summary["policy_blocking_ratio"]

    prefix_affected = [
        workflow_id
        for workflow_id, workflow_summary in workflow_breakdown.items()
        if _prefix_issue_count(workflow_summary) >= int(diagnostic_config["prefix_instability_min_issue_count"])
        and (
            workflow_summary["prefix_eligibility_ratio"] is None
            or workflow_summary["prefix_eligibility_ratio"]
            <= float(diagnostic_config["prefix_instability_max_eligibility_ratio"])
        )
    ]
    threshold_affected = [
        workflow_id
        for workflow_id, workflow_summary in workflow_breakdown.items()
        if int(workflow_summary["semantic_reuse_attempted_count"])
        >= int(diagnostic_config["semantic_threshold_too_strict_min_attempts"])
        and (workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_threshold"] > 0)
        and (
            _round_ratio(
                workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_threshold"],
                int(workflow_summary["semantic_reuse_attempted_count"]),
            )
            or 0.0
        )
        >= float(diagnostic_config["semantic_threshold_too_strict_min_ratio"])
    ]
    validation_affected = [
        workflow_id
        for workflow_id, workflow_summary in workflow_breakdown.items()
        if int(workflow_summary["semantic_reuse_attempted_count"])
        >= int(diagnostic_config["validator_rejection_dominant_min_attempts"])
        and (workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_validation"] > 0)
        and (
            _round_ratio(
                workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_validation"],
                int(workflow_summary["semantic_reuse_attempted_count"]),
            )
            or 0.0
        )
        >= float(diagnostic_config["validator_rejection_dominant_min_ratio"])
    ]
    ttl_affected = [
        workflow_id
        for workflow_id, workflow_summary in workflow_breakdown.items()
        if int(workflow_summary["semantic_reuse_attempted_count"])
        >= int(diagnostic_config["cache_ttl_too_short_min_attempts"])
        and (workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_ttl"] > 0)
        and (
            _round_ratio(
                workflow_summary["reuse_loss_categories"]["reuse_loss_due_to_ttl"],
                int(workflow_summary["semantic_reuse_attempted_count"]),
            )
            or 0.0
        )
        >= float(diagnostic_config["cache_ttl_too_short_min_ratio"])
    ]
    policy_affected = [
        workflow_id
        for workflow_id, workflow_summary in workflow_breakdown.items()
        if (
            int(workflow_summary["policy_block_count"])
            + int(workflow_summary["semantic_reuse_attempted_count"])
        )
        >= int(diagnostic_config["policy_blocking_high_min_decisions"])
        and ((workflow_summary["policy_blocking_ratio"] or 0.0) >= float(diagnostic_config["policy_blocking_high_min_ratio"]))
    ]

    flags = {
        "prefix_instability_problem": _build_flag(
            triggered=(
                prefix_issue_count >= int(diagnostic_config["prefix_instability_min_issue_count"])
                and (
                    report_summary["prefix_eligibility_ratio"] is None
                    or report_summary["prefix_eligibility_ratio"]
                    <= float(diagnostic_config["prefix_instability_max_eligibility_ratio"])
                )
            ),
            metric_name="prefix_issue_count",
            metric_value=prefix_issue_count,
            threshold=int(diagnostic_config["prefix_instability_min_issue_count"]),
            comparison="gte",
            affected_workflows=prefix_affected,
            supporting_counts={
                "prefix_cache_ineligible_count": int(report_summary["prefix_cache_ineligible_count"]),
                "reuse_loss_due_to_prefix_mismatch": int(reuse_loss_categories["reuse_loss_due_to_prefix_mismatch"]),
            },
        ),
        "semantic_threshold_too_strict": _build_flag(
            triggered=(
                int(report_summary["semantic_reuse_attempted_count"])
                >= int(diagnostic_config["semantic_threshold_too_strict_min_attempts"])
                and (threshold_loss_ratio or 0.0)
                >= float(diagnostic_config["semantic_threshold_too_strict_min_ratio"])
            ),
            metric_name="threshold_loss_ratio",
            metric_value=threshold_loss_ratio,
            threshold=float(diagnostic_config["semantic_threshold_too_strict_min_ratio"]),
            comparison="gte",
            affected_workflows=threshold_affected,
            supporting_counts={
                "reuse_loss_due_to_threshold": int(reuse_loss_categories["reuse_loss_due_to_threshold"]),
                "semantic_reuse_attempted_count": int(report_summary["semantic_reuse_attempted_count"]),
            },
        ),
        "validator_rejection_dominant": _build_flag(
            triggered=(
                int(report_summary["semantic_reuse_attempted_count"])
                >= int(diagnostic_config["validator_rejection_dominant_min_attempts"])
                and (validation_loss_ratio or 0.0)
                >= float(diagnostic_config["validator_rejection_dominant_min_ratio"])
            ),
            metric_name="validation_loss_ratio",
            metric_value=validation_loss_ratio,
            threshold=float(diagnostic_config["validator_rejection_dominant_min_ratio"]),
            comparison="gte",
            affected_workflows=validation_affected,
            supporting_counts={
                "reuse_loss_due_to_validation": int(reuse_loss_categories["reuse_loss_due_to_validation"]),
                "semantic_reuse_attempted_count": int(report_summary["semantic_reuse_attempted_count"]),
            },
        ),
        "cache_ttl_too_short": _build_flag(
            triggered=(
                int(report_summary["semantic_reuse_attempted_count"])
                >= int(diagnostic_config["cache_ttl_too_short_min_attempts"])
                and (ttl_loss_ratio or 0.0)
                >= float(diagnostic_config["cache_ttl_too_short_min_ratio"])
            ),
            metric_name="ttl_loss_ratio",
            metric_value=ttl_loss_ratio,
            threshold=float(diagnostic_config["cache_ttl_too_short_min_ratio"]),
            comparison="gte",
            affected_workflows=ttl_affected,
            supporting_counts={
                "reuse_loss_due_to_ttl": int(reuse_loss_categories["reuse_loss_due_to_ttl"]),
                "semantic_reuse_attempted_count": int(report_summary["semantic_reuse_attempted_count"]),
            },
        ),
        "policy_blocking_high": _build_flag(
            triggered=(
                int(report_summary["policy_block_count"]) + int(report_summary["semantic_reuse_attempted_count"])
                >= int(diagnostic_config["policy_blocking_high_min_decisions"])
                and (policy_blocking_ratio or 0.0)
                >= float(diagnostic_config["policy_blocking_high_min_ratio"])
            ),
            metric_name="policy_blocking_ratio",
            metric_value=policy_blocking_ratio,
            threshold=float(diagnostic_config["policy_blocking_high_min_ratio"]),
            comparison="gte",
            affected_workflows=policy_affected,
            supporting_counts={
                "policy_block_count": int(report_summary["policy_block_count"]),
                "semantic_reuse_attempted_count": int(report_summary["semantic_reuse_attempted_count"]),
            },
        ),
    }
    return {
        "config": {
            key: diagnostic_config[key]
            for key in sorted(diagnostic_config)
        },
        "flags": flags,
    }


def _build_expansion_candidates(
    *,
    workflow_breakdown: dict[str, dict[str, Any]],
    expansion_config: dict[str, Any],
) -> dict[str, Any]:
    workflows: list[dict[str, Any]] = []
    min_attempts = int(expansion_config["min_semantic_reuse_attempted_count"])
    min_hit_rate = float(expansion_config["min_validated_hit_rate"])
    max_rejection_rate = float(expansion_config["max_rejection_rate"])

    for workflow_id in sorted(workflow_breakdown):
        workflow_summary = workflow_breakdown[workflow_id]
        attempts = int(workflow_summary["semantic_reuse_attempted_count"])
        hit_rate = workflow_summary["validated_hit_rate"]
        rejection_rate = workflow_summary["candidate_rejection_rate"]
        if attempts < min_attempts:
            continue
        if hit_rate is None or hit_rate < min_hit_rate:
            continue
        if rejection_rate is None:
            rejection_rate = 0.0
        if rejection_rate > max_rejection_rate:
            continue
        workflows.append(
            {
                "workflow_id": workflow_id,
                "semantic_reuse_attempted_count": attempts,
                "validated_hit_rate": hit_rate,
                "candidate_rejection_rate": rejection_rate,
                "reuse_loss_categories": dict(workflow_summary["reuse_loss_categories"]),
                "policy_block_count": int(workflow_summary["policy_block_count"]),
            }
        )

    return {
        "criteria": {
            key: expansion_config[key]
            for key in sorted(expansion_config)
        },
        "workflows": workflows,
    }


def _format_scalar(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_ratio(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


def _format_sorted_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "none"
    return ", ".join(
        f"{key}={_format_scalar(mapping[key])}"
        for key in sorted(mapping)
    )


def _format_sequence(values: list[str] | tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ", ".join(str(value) for value in values)


def _format_reuse_loss_summary(losses: dict[str, Any]) -> str:
    return ", ".join(
        f"{_REUSE_LOSS_SHORT_LABELS[field]}={int(losses.get(field, 0))}"
        for field in _REUSE_LOSS_FIELDS
    )


def _write_text_file(path: Path | str, content: str) -> Path:
    resolved_path = Path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content, encoding="utf-8")
    return resolved_path


def _resolve_generated_at(generated_at: str | None) -> str:
    if generated_at is not None:
        parsed = _parse_utc(generated_at)
        if parsed is None:
            raise ValueError("generated_at must be a valid ISO-8601 timestamp")
        resolved = _isoformat_utc(parsed)
        if resolved is None:
            raise ValueError("generated_at must be a valid ISO-8601 timestamp")
        return resolved
    resolved_now = _isoformat_utc(datetime.now(timezone.utc))
    if resolved_now is None:
        raise ValueError("failed to derive generated_at")
    return resolved_now


def _guess_repo_root_from_report(report: dict[str, Any]) -> Path | None:
    source_paths = report.get("source_paths", {})
    for field_name, expected_file_name in (
        ("event_log_path", "event_log.jsonl"),
        ("registry_path", "inference_cache_registry.jsonl"),
    ):
        raw_path = source_paths.get(field_name)
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if path.name != expected_file_name:
            continue
        if len(path.parents) < 3:
            continue
        if path.parents[0].name != "state" or path.parents[1].name != "data":
            continue
        return path.parents[2]
    return None


def _resolve_snapshot_repo_root(
    report: dict[str, Any],
    repo_root: Path | str | None,
) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    guessed_root = _guess_repo_root_from_report(report)
    if guessed_root is not None:
        return guessed_root
    return _get_root(None)


def _read_git_commit_hash(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit_hash = result.stdout.strip()
    return commit_hash or None


def _build_inference_cache_snapshot(
    report: dict[str, Any],
    *,
    repo_root: Path | str | None = None,
    generated_at: str | None = None,
    git_commit_hash: str | None = None,
    resolve_git_commit_hash: bool = True,
) -> dict[str, Any]:
    resolved_repo_root = _resolve_snapshot_repo_root(report, repo_root)
    resolved_generated_at = _resolve_generated_at(generated_at)
    resolved_git_commit_hash = git_commit_hash
    if resolved_git_commit_hash is None and resolve_git_commit_hash:
        resolved_git_commit_hash = _read_git_commit_hash(resolved_repo_root)
    return {
        "snapshot_metadata": {
            "snapshot_type": "inference_cache_audit",
            "snapshot_version": INFERENCE_CACHE_ACTIVITY_SNAPSHOT_VERSION,
            "generated_at": resolved_generated_at,
            "repo_root": str(resolved_repo_root),
            "git_commit_hash": resolved_git_commit_hash,
            "report_version": report.get("report_version"),
            "render_version": INFERENCE_CACHE_ACTIVITY_RENDER_VERSION,
            "filters": dict(report.get("filters", {})),
            "source_paths": dict(report.get("source_paths", {})),
        },
        "report": report,
    }


def _format_inference_cache_snapshot(snapshot: dict[str, Any]) -> str:
    metadata = snapshot.get("snapshot_metadata", {})
    report = snapshot.get("report", {})
    lines = [
        "Inference Cache Audit Snapshot",
        f"snapshot_version: {_format_scalar(metadata.get('snapshot_version'))}",
        f"generated_at: {_format_scalar(metadata.get('generated_at'))}",
        f"repo_root: {_format_scalar(metadata.get('repo_root'))}",
        f"git_commit_hash: {_format_scalar(metadata.get('git_commit_hash'))}",
        f"filters: {_format_sorted_mapping(metadata.get('filters', {}))}",
        f"source_paths: {_format_sorted_mapping(metadata.get('source_paths', {}))}",
        "",
        format_inference_cache_report(report),
    ]
    return "\n".join(lines) + "\n"


def _load_json_object(path: Path | str) -> dict[str, Any]:
    resolved_path = Path(path)
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {resolved_path}")
    return payload


def _is_numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare_value(baseline: Any, candidate: Any) -> dict[str, Any]:
    return {
        "baseline": baseline,
        "candidate": candidate,
        "changed": baseline != candidate,
    }


def _compare_numeric(baseline: Any, candidate: Any) -> dict[str, Any]:
    entry = _compare_value(baseline, candidate)
    if (baseline is None or _is_numeric_value(baseline)) and (
        candidate is None or _is_numeric_value(candidate)
    ):
        if baseline is None or candidate is None:
            entry["delta"] = None
        elif isinstance(baseline, int) and isinstance(candidate, int):
            entry["delta"] = int(candidate) - int(baseline)
        else:
            entry["delta"] = round(float(candidate) - float(baseline), 6)
    else:
        entry["delta"] = None
    return entry


def _compare_count_fields(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    return {
        field_name: _compare_numeric(
            int(baseline.get(field_name, 0)),
            int(candidate.get(field_name, 0)),
        )
        for field_name in fields
    }


def _compare_ratio_fields(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    return {
        field_name: _compare_numeric(
            baseline.get(field_name),
            candidate.get(field_name),
        )
        for field_name in fields
    }


def _compare_counter_like_mappings(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        key: _compare_numeric(
            int(baseline.get(key, 0)),
            int(candidate.get(key, 0)),
        )
        for key in sorted(set(baseline) | set(candidate))
    }


def _compare_value_mappings(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        key: _compare_value(baseline.get(key), candidate.get(key))
        for key in sorted(set(baseline) | set(candidate))
    }


def _compare_sequences(
    baseline: list[Any] | tuple[Any, ...],
    candidate: list[Any] | tuple[Any, ...],
) -> dict[str, Any]:
    baseline_values = sorted(str(value) for value in baseline)
    candidate_values = sorted(str(value) for value in candidate)
    baseline_set = set(baseline_values)
    candidate_set = set(candidate_values)
    return {
        "baseline": baseline_values,
        "candidate": candidate_values,
        "added": sorted(candidate_set - baseline_set),
        "removed": sorted(baseline_set - candidate_set),
        "changed": baseline_values != candidate_values,
    }


def _comparison_map_changed(comparison: dict[str, Any]) -> bool:
    return any(bool(entry.get("changed")) for entry in comparison.values() if isinstance(entry, dict))


def _build_snapshot_metadata_comparison(
    baseline_metadata: dict[str, Any],
    candidate_metadata: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        field_name: _compare_value(
            baseline_metadata.get(field_name),
            candidate_metadata.get(field_name),
        )
        for field_name in (
            "snapshot_type",
            "snapshot_version",
            "generated_at",
            "repo_root",
            "git_commit_hash",
            "report_version",
            "render_version",
        )
    }
    filters = _compare_value_mappings(
        dict(baseline_metadata.get("filters", {})),
        dict(candidate_metadata.get("filters", {})),
    )
    source_paths = _compare_value_mappings(
        dict(baseline_metadata.get("source_paths", {})),
        dict(candidate_metadata.get("source_paths", {})),
    )
    return {
        "fields": fields,
        "filters": filters,
        "source_paths": source_paths,
        "changed": (
            _comparison_map_changed(fields)
            or _comparison_map_changed(filters)
            or _comparison_map_changed(source_paths)
        ),
    }


def _build_diagnostic_flag_changes(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
) -> dict[str, Any]:
    baseline_diagnostics = dict(baseline_report.get("diagnostics", {}))
    candidate_diagnostics = dict(candidate_report.get("diagnostics", {}))
    config_comparison = _compare_value_mappings(
        dict(baseline_diagnostics.get("config", {})),
        dict(candidate_diagnostics.get("config", {})),
    )
    baseline_flags = dict(baseline_diagnostics.get("flags", {}))
    candidate_flags = dict(candidate_diagnostics.get("flags", {}))
    flags: dict[str, dict[str, Any]] = {}
    for flag_name in sorted(set(baseline_flags) | set(candidate_flags)):
        baseline_flag = dict(baseline_flags.get(flag_name, {}))
        candidate_flag = dict(candidate_flags.get(flag_name, {}))
        flag_changes = {
            "triggered": _compare_value(
                bool(baseline_flag.get("triggered", False)),
                bool(candidate_flag.get("triggered", False)),
            ),
            "metric_name": _compare_value(
                baseline_flag.get("metric_name"),
                candidate_flag.get("metric_name"),
            ),
            "metric_value": _compare_numeric(
                baseline_flag.get("metric_value"),
                candidate_flag.get("metric_value"),
            ),
            "threshold": _compare_numeric(
                baseline_flag.get("threshold"),
                candidate_flag.get("threshold"),
            ),
            "comparison": _compare_value(
                baseline_flag.get("comparison"),
                candidate_flag.get("comparison"),
            ),
            "affected_workflows": _compare_sequences(
                list(baseline_flag.get("affected_workflows", [])),
                list(candidate_flag.get("affected_workflows", [])),
            ),
            "supporting_counts_deltas": _compare_counter_like_mappings(
                dict(baseline_flag.get("supporting_counts", {})),
                dict(candidate_flag.get("supporting_counts", {})),
            ),
        }
        flag_changes["changed"] = (
            bool(flag_changes["triggered"]["changed"])
            or bool(flag_changes["metric_name"]["changed"])
            or bool(flag_changes["metric_value"]["changed"])
            or bool(flag_changes["threshold"]["changed"])
            or bool(flag_changes["comparison"]["changed"])
            or bool(flag_changes["affected_workflows"]["changed"])
            or _comparison_map_changed(flag_changes["supporting_counts_deltas"])
        )
        flags[flag_name] = flag_changes
    return {
        "config": config_comparison,
        "flags": flags,
        "changed": _comparison_map_changed(config_comparison)
        or any(bool(flag.get("changed")) for flag in flags.values()),
    }


def _build_expansion_candidate_changes(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
) -> dict[str, Any]:
    baseline_expansion = dict(baseline_report.get("candidate_workflows_for_expansion", {}))
    candidate_expansion = dict(candidate_report.get("candidate_workflows_for_expansion", {}))
    criteria = _compare_value_mappings(
        dict(baseline_expansion.get("criteria", {})),
        dict(candidate_expansion.get("criteria", {})),
    )
    baseline_candidates = {
        str(entry.get("workflow_id") or ""): dict(entry)
        for entry in list(baseline_expansion.get("workflows", []))
        if str(entry.get("workflow_id") or "")
    }
    candidate_candidates = {
        str(entry.get("workflow_id") or ""): dict(entry)
        for entry in list(candidate_expansion.get("workflows", []))
        if str(entry.get("workflow_id") or "")
    }
    baseline_workflows = sorted(baseline_candidates)
    candidate_workflows = sorted(candidate_candidates)
    retained_metric_deltas: dict[str, dict[str, Any]] = {}
    for workflow_id in sorted(set(baseline_candidates) & set(candidate_candidates)):
        baseline_entry = baseline_candidates[workflow_id]
        candidate_entry = candidate_candidates[workflow_id]
        count_deltas = _compare_count_fields(
            baseline_entry,
            candidate_entry,
            _EXPANSION_CANDIDATE_COUNT_FIELDS,
        )
        ratio_deltas = _compare_ratio_fields(
            baseline_entry,
            candidate_entry,
            _EXPANSION_CANDIDATE_RATIO_FIELDS,
        )
        reuse_loss_category_deltas = _compare_counter_like_mappings(
            dict(baseline_entry.get("reuse_loss_categories", {})),
            dict(candidate_entry.get("reuse_loss_categories", {})),
        )
        changed = (
            _comparison_map_changed(count_deltas)
            or _comparison_map_changed(ratio_deltas)
            or _comparison_map_changed(reuse_loss_category_deltas)
        )
        retained_metric_deltas[workflow_id] = {
            "count_deltas": count_deltas,
            "ratio_deltas": ratio_deltas,
            "reuse_loss_category_deltas": reuse_loss_category_deltas,
            "changed": changed,
        }
    added = sorted(set(candidate_candidates) - set(baseline_candidates))
    removed = sorted(set(baseline_candidates) - set(candidate_candidates))
    return {
        "criteria": criteria,
        "baseline_workflows": baseline_workflows,
        "candidate_workflows": candidate_workflows,
        "added": added,
        "removed": removed,
        "retained_metric_deltas": retained_metric_deltas,
        "changed": (
            _comparison_map_changed(criteria)
            or bool(added)
            or bool(removed)
            or any(
                bool(entry.get("changed"))
                for entry in retained_metric_deltas.values()
            )
        ),
    }


def _build_workflow_metric_deltas(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    baseline_breakdown = dict(baseline_report.get("workflow_breakdown", {}))
    candidate_breakdown = dict(candidate_report.get("workflow_breakdown", {}))
    deltas: dict[str, dict[str, Any]] = {}
    for workflow_id in sorted(set(baseline_breakdown) | set(candidate_breakdown)):
        baseline_entry = dict(baseline_breakdown.get(workflow_id, {}))
        candidate_entry = dict(candidate_breakdown.get(workflow_id, {}))
        count_deltas = _compare_count_fields(
            baseline_entry,
            candidate_entry,
            _WORKFLOW_DIFF_COUNT_FIELDS,
        )
        ratio_deltas = _compare_ratio_fields(
            baseline_entry,
            candidate_entry,
            _RATIO_FIELDS,
        )
        reuse_loss_category_deltas = _compare_counter_like_mappings(
            dict(baseline_entry.get("reuse_loss_categories", {})),
            dict(candidate_entry.get("reuse_loss_categories", {})),
        )
        reason_code_distribution_deltas = _compare_counter_like_mappings(
            dict(baseline_entry.get("reason_code_counts", {})),
            dict(candidate_entry.get("reason_code_counts", {})),
        )
        candidate_rejection_reason_code_distribution_deltas = _compare_counter_like_mappings(
            dict(baseline_entry.get("candidate_rejection_reason_code_counts", {})),
            dict(candidate_entry.get("candidate_rejection_reason_code_counts", {})),
        )
        changed = (
            _comparison_map_changed(count_deltas)
            or _comparison_map_changed(ratio_deltas)
            or _comparison_map_changed(reuse_loss_category_deltas)
            or _comparison_map_changed(reason_code_distribution_deltas)
            or _comparison_map_changed(candidate_rejection_reason_code_distribution_deltas)
        )
        if workflow_id not in baseline_breakdown:
            status = "added"
        elif workflow_id not in candidate_breakdown:
            status = "removed"
        elif changed:
            status = "modified"
        else:
            status = "unchanged"
        deltas[workflow_id] = {
            "status": status,
            "count_deltas": count_deltas,
            "ratio_deltas": ratio_deltas,
            "reuse_loss_category_deltas": reuse_loss_category_deltas,
            "reason_code_distribution_deltas": reason_code_distribution_deltas,
            "candidate_rejection_reason_code_distribution_deltas": candidate_rejection_reason_code_distribution_deltas,
            "changed": changed,
        }
    return deltas


def build_inference_cache_snapshot_diff(
    *,
    baseline_snapshot: dict[str, Any],
    candidate_snapshot: dict[str, Any],
) -> dict[str, Any]:
    baseline_metadata = dict(baseline_snapshot.get("snapshot_metadata", {}))
    candidate_metadata = dict(candidate_snapshot.get("snapshot_metadata", {}))
    baseline_report = dict(baseline_snapshot.get("report", {}))
    candidate_report = dict(candidate_snapshot.get("report", {}))

    snapshot_metadata_comparison = _build_snapshot_metadata_comparison(
        baseline_metadata,
        candidate_metadata,
    )
    top_level_count_deltas = _compare_count_fields(
        baseline_report,
        candidate_report,
        _TOP_LEVEL_COUNT_FIELDS,
    )
    registry_summary_count_deltas = _compare_count_fields(
        dict(baseline_report.get("registry_summary", {})),
        dict(candidate_report.get("registry_summary", {})),
        _REGISTRY_COUNT_FIELDS,
    )
    registry_entries_by_workflow_deltas = _compare_counter_like_mappings(
        dict(baseline_report.get("registry_summary", {}).get("entries_by_workflow", {})),
        dict(candidate_report.get("registry_summary", {}).get("entries_by_workflow", {})),
    )
    ratio_deltas = _compare_ratio_fields(
        baseline_report,
        candidate_report,
        _RATIO_FIELDS,
    )
    reuse_loss_category_deltas = _compare_counter_like_mappings(
        dict(baseline_report.get("reuse_loss_categories", {})),
        dict(candidate_report.get("reuse_loss_categories", {})),
    )
    reason_code_distribution_deltas = _compare_counter_like_mappings(
        dict(baseline_report.get("reason_code_counts", {})),
        dict(candidate_report.get("reason_code_counts", {})),
    )
    candidate_rejection_reason_code_distribution_deltas = _compare_counter_like_mappings(
        dict(baseline_report.get("candidate_rejection_reason_code_counts", {})),
        dict(candidate_report.get("candidate_rejection_reason_code_counts", {})),
    )
    diagnostics_comparison = _build_diagnostic_flag_changes(
        baseline_report,
        candidate_report,
    )
    expansion_candidate_changes = _build_expansion_candidate_changes(
        baseline_report,
        candidate_report,
    )
    workflow_metric_deltas = _build_workflow_metric_deltas(
        baseline_report,
        candidate_report,
    )

    changed_sections = {
        "snapshot_metadata": bool(snapshot_metadata_comparison["changed"]),
        "top_level_counts": _comparison_map_changed(top_level_count_deltas),
        "registry_summary": _comparison_map_changed(registry_summary_count_deltas)
        or _comparison_map_changed(registry_entries_by_workflow_deltas),
        "ratios": _comparison_map_changed(ratio_deltas),
        "reuse_loss_categories": _comparison_map_changed(reuse_loss_category_deltas),
        "reason_code_distribution": _comparison_map_changed(reason_code_distribution_deltas),
        "candidate_rejection_reason_code_distribution": _comparison_map_changed(
            candidate_rejection_reason_code_distribution_deltas
        ),
        "diagnostics": bool(diagnostics_comparison["changed"]),
        "expansion_candidates": bool(expansion_candidate_changes["changed"]),
        "workflow_metrics": any(
            bool(entry.get("changed")) or entry.get("status") != "unchanged"
            for entry in workflow_metric_deltas.values()
        ),
    }

    return {
        "diff_version": INFERENCE_CACHE_ACTIVITY_DIFF_VERSION,
        "snapshot_metadata_comparison": snapshot_metadata_comparison,
        "top_level_count_deltas": top_level_count_deltas,
        "registry_summary_count_deltas": registry_summary_count_deltas,
        "registry_entries_by_workflow_deltas": registry_entries_by_workflow_deltas,
        "ratio_deltas": ratio_deltas,
        "reuse_loss_category_deltas": reuse_loss_category_deltas,
        "reason_code_distribution_deltas": reason_code_distribution_deltas,
        "candidate_rejection_reason_code_distribution_deltas": candidate_rejection_reason_code_distribution_deltas,
        "diagnostics_comparison": diagnostics_comparison,
        "expansion_candidate_changes": expansion_candidate_changes,
        "workflow_metric_deltas": workflow_metric_deltas,
        "changed_sections": changed_sections,
        "has_changes": any(changed_sections.values()),
    }


def compare_inference_cache_snapshots(
    *,
    baseline_snapshot_path: Path | str,
    candidate_snapshot_path: Path | str,
) -> dict[str, Any]:
    return build_inference_cache_snapshot_diff(
        baseline_snapshot=_load_json_object(baseline_snapshot_path),
        candidate_snapshot=_load_json_object(candidate_snapshot_path),
    )


def _format_changed_scalar_deltas(section: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for key in sorted(section):
        entry = section[key]
        if not bool(entry.get("changed")):
            continue
        if "delta" in entry:
            lines.append(
                "- "
                f"{key}: baseline={_format_scalar(entry.get('baseline'))}, "
                f"candidate={_format_scalar(entry.get('candidate'))}, "
                f"delta={_format_scalar(entry.get('delta'))}"
            )
        else:
            lines.append(
                "- "
                f"{key}: baseline={_format_scalar(entry.get('baseline'))}, "
                f"candidate={_format_scalar(entry.get('candidate'))}"
            )
    return lines


def format_inference_cache_snapshot_diff(diff: dict[str, Any]) -> str:
    metadata = dict(diff.get("snapshot_metadata_comparison", {}))
    diagnostics = dict(diff.get("diagnostics_comparison", {}))
    expansion = dict(diff.get("expansion_candidate_changes", {}))
    workflow_deltas = dict(diff.get("workflow_metric_deltas", {}))
    lines = [
        "Inference Cache Audit Snapshot Diff",
        f"diff_version: {_format_scalar(diff.get('diff_version'))}",
        f"has_changes: {_format_scalar(diff.get('has_changes'))}",
        "",
        "Changed Sections",
    ]
    changed_sections = dict(diff.get("changed_sections", {}))
    for section_name in sorted(changed_sections):
        lines.append(f"- {section_name}: {_format_scalar(changed_sections[section_name])}")

    lines.extend(["", "Snapshot Metadata Comparison"])
    metadata_lines = _format_changed_scalar_deltas(dict(metadata.get("fields", {})))
    metadata_lines.extend(_format_changed_scalar_deltas(dict(metadata.get("filters", {}))))
    metadata_lines.extend(_format_changed_scalar_deltas(dict(metadata.get("source_paths", {}))))
    lines.extend(metadata_lines or ["- none"])

    lines.extend(["", "Top-Level Count Deltas"])
    lines.extend(_format_changed_scalar_deltas(dict(diff.get("top_level_count_deltas", {}))) or ["- none"])

    lines.extend(["", "Ratio Deltas"])
    lines.extend(_format_changed_scalar_deltas(dict(diff.get("ratio_deltas", {}))) or ["- none"])

    lines.extend(["", "Reuse-Loss Category Deltas"])
    lines.extend(_format_changed_scalar_deltas(dict(diff.get("reuse_loss_category_deltas", {}))) or ["- none"])

    lines.extend(["", "Reason Code Distribution Deltas"])
    lines.extend(_format_changed_scalar_deltas(dict(diff.get("reason_code_distribution_deltas", {}))) or ["- none"])

    lines.extend(["", "Diagnostic Flag Changes"])
    diagnostic_lines: list[str] = []
    for flag_name in sorted(dict(diagnostics.get("flags", {}))):
        flag = diagnostics["flags"][flag_name]
        if not bool(flag.get("changed")):
            continue
        affected_workflows = dict(flag.get("affected_workflows", {}))
        diagnostic_lines.append(
            "- "
            f"{flag_name}: "
            f"triggered={_format_scalar(flag.get('triggered', {}).get('baseline'))}"
            f"->{_format_scalar(flag.get('triggered', {}).get('candidate'))}, "
            f"metric_value={_format_scalar(flag.get('metric_value', {}).get('baseline'))}"
            f"->{_format_scalar(flag.get('metric_value', {}).get('candidate'))}, "
            f"added_workflows={_format_sequence(tuple(affected_workflows.get('added', [])))}, "
            f"removed_workflows={_format_sequence(tuple(affected_workflows.get('removed', [])))}"
        )
    lines.extend(diagnostic_lines or ["- none"])

    lines.extend(["", "Expansion Candidate Changes"])
    expansion_lines: list[str] = []
    criteria_lines = _format_changed_scalar_deltas(dict(expansion.get("criteria", {})))
    expansion_lines.extend(criteria_lines)
    if expansion.get("added"):
        expansion_lines.append(f"- added: {_format_sequence(tuple(expansion.get('added', [])))}")
    if expansion.get("removed"):
        expansion_lines.append(f"- removed: {_format_sequence(tuple(expansion.get('removed', [])))}")
    retained = dict(expansion.get("retained_metric_deltas", {}))
    for workflow_id in sorted(retained):
        retained_entry = retained[workflow_id]
        if not bool(retained_entry.get("changed")):
            continue
        expansion_lines.append(
            "- "
            f"{workflow_id}: "
            f"count_changes={len(_format_changed_scalar_deltas(dict(retained_entry.get('count_deltas', {}))))}, "
            f"ratio_changes={len(_format_changed_scalar_deltas(dict(retained_entry.get('ratio_deltas', {}))))}, "
            f"reuse_loss_changes={len(_format_changed_scalar_deltas(dict(retained_entry.get('reuse_loss_category_deltas', {}))))}"
        )
    lines.extend(expansion_lines or ["- none"])

    lines.extend(["", "Workflow Metric Deltas"])
    workflow_lines: list[str] = []
    for workflow_id in sorted(workflow_deltas):
        workflow_entry = workflow_deltas[workflow_id]
        if workflow_entry.get("status") == "unchanged" and not bool(workflow_entry.get("changed")):
            continue
        count_changes = _format_changed_scalar_deltas(dict(workflow_entry.get("count_deltas", {})))
        ratio_changes = _format_changed_scalar_deltas(dict(workflow_entry.get("ratio_deltas", {})))
        reason_changes = _format_changed_scalar_deltas(
            dict(workflow_entry.get("reason_code_distribution_deltas", {}))
        )
        workflow_lines.append(
            "- "
            f"{workflow_id}: "
            f"status={_format_scalar(workflow_entry.get('status'))}, "
            f"count_changes={len(count_changes)}, "
            f"ratio_changes={len(ratio_changes)}, "
            f"reason_changes={len(reason_changes)}"
        )
    lines.extend(workflow_lines or ["- none"])
    return "\n".join(lines)


def render_inference_cache_snapshot_diff(
    *,
    baseline_snapshot_path: Path | str,
    candidate_snapshot_path: Path | str,
) -> str:
    return format_inference_cache_snapshot_diff(
        compare_inference_cache_snapshots(
            baseline_snapshot_path=baseline_snapshot_path,
            candidate_snapshot_path=candidate_snapshot_path,
        )
    )


def format_inference_cache_report(report: dict[str, Any]) -> str:
    source_paths = report.get("source_paths", {})
    filters = report.get("filters", {})
    registry_summary = report.get("registry_summary", {})
    diagnostics = report.get("diagnostics", {})
    diagnostic_flags = diagnostics.get("flags", {})
    expansion = report.get("candidate_workflows_for_expansion", {})
    workflow_breakdown = report.get("workflow_breakdown", {})
    reuse_loss_categories = report.get("reuse_loss_categories", {})

    lines: list[str] = [
        "Inference Cache Audit Report",
        f"report_version: {_format_scalar(report.get('report_version'))}",
        f"render_version: {INFERENCE_CACHE_ACTIVITY_RENDER_VERSION}",
        "",
        "Scope / Filters",
        f"- event_log_path: {_format_scalar(source_paths.get('event_log_path'))}",
        f"- registry_path: {_format_scalar(source_paths.get('registry_path'))}",
        f"- last_n_events: {_format_scalar(filters.get('last_n_events'))}",
        f"- last_n_hours: {_format_scalar(filters.get('last_n_hours'))}",
        f"- workflow_id: {_format_scalar(filters.get('workflow_id'))}",
        f"- artifact_id: {_format_scalar(filters.get('artifact_id'))}",
        f"- reference_time: {_format_scalar(filters.get('reference_time'))}",
        f"- window_start: {_format_scalar(filters.get('window_start'))}",
        f"- last_n_events_applies_to: {_format_scalar(filters.get('last_n_events_applies_to'))}",
        "",
        "Top-Level Counts",
    ]
    for field_name in _TOP_LEVEL_COUNT_FIELDS:
        lines.append(f"- {field_name}: {int(report.get(field_name, 0))}")
    for field_name in _REGISTRY_COUNT_FIELDS:
        lines.append(f"- registry_{field_name}: {int(registry_summary.get(field_name, 0))}")
    lines.append(f"- registry_entries_by_workflow: {_format_sorted_mapping(registry_summary.get('entries_by_workflow', {}))}")

    lines.extend(["", "Key Ratios"])
    for field_name in _RATIO_FIELDS:
        lines.append(f"- {field_name}: {_format_ratio(report.get(field_name))}")

    lines.extend(["", "Reuse-Loss Categories"])
    for field_name in _REUSE_LOSS_FIELDS:
        lines.append(f"- {field_name}: {int(reuse_loss_categories.get(field_name, 0))}")

    lines.extend(["", "Diagnostics Flags"])
    if diagnostic_flags:
        for flag_name in sorted(diagnostic_flags):
            flag = diagnostic_flags[flag_name]
            lines.append(
                "- "
                f"{flag_name}: "
                f"triggered={_format_scalar(flag.get('triggered'))}, "
                f"metric_name={_format_scalar(flag.get('metric_name'))}, "
                f"metric_value={_format_ratio(flag.get('metric_value')) if isinstance(flag.get('metric_value'), float) or flag.get('metric_value') is None else _format_scalar(flag.get('metric_value'))}, "
                f"threshold={_format_scalar(flag.get('threshold'))}, "
                f"comparison={_format_scalar(flag.get('comparison'))}, "
                f"affected_workflows={_format_sequence(tuple(flag.get('affected_workflows', [])))}, "
                f"supporting_counts={_format_sorted_mapping(flag.get('supporting_counts', {}))}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "Candidate Workflows For Expansion"])
    lines.append(
        f"- criteria: {_format_sorted_mapping(expansion.get('criteria', {}))}"
    )
    candidate_workflows = expansion.get("workflows", [])
    if candidate_workflows:
        for candidate in sorted(candidate_workflows, key=lambda item: str(item.get("workflow_id") or "")):
            lines.append(
                "- "
                f"{_format_scalar(candidate.get('workflow_id'))}: "
                f"semantic_reuse_attempted_count={int(candidate.get('semantic_reuse_attempted_count', 0))}, "
                f"validated_hit_rate={_format_ratio(candidate.get('validated_hit_rate'))}, "
                f"candidate_rejection_rate={_format_ratio(candidate.get('candidate_rejection_rate'))}, "
                f"policy_block_count={int(candidate.get('policy_block_count', 0))}, "
                f"reuse_loss={_format_reuse_loss_summary(candidate.get('reuse_loss_categories', {}))}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "Workflow Breakdown Summary"])
    if workflow_breakdown:
        for workflow_key in sorted(workflow_breakdown):
            summary = workflow_breakdown[workflow_key]
            lines.append(
                "- "
                f"{workflow_key}: "
                f"total_cache_related_events={int(summary.get('total_cache_related_events', 0))}, "
                f"semantic_reuse_attempted_count={int(summary.get('semantic_reuse_attempted_count', 0))}, "
                f"semantic_cache_hit_validated_count={int(summary.get('semantic_cache_hit_validated_count', 0))}, "
                f"semantic_cache_hit_rejected_count={int(summary.get('semantic_cache_hit_rejected_count', 0))}, "
                f"semantic_cache_miss_count={int(summary.get('semantic_cache_miss_count', 0))}, "
                f"policy_block_count={int(summary.get('policy_block_count', 0))}, "
                f"validated_hit_rate={_format_ratio(summary.get('validated_hit_rate'))}, "
                f"candidate_rejection_rate={_format_ratio(summary.get('candidate_rejection_rate'))}, "
                f"prefix_eligibility_ratio={_format_ratio(summary.get('prefix_eligibility_ratio'))}, "
                f"registry_entries_in_scope={int(summary.get('registry_entries_in_scope', 0))}, "
                f"reuse_loss={_format_reuse_loss_summary(summary.get('reuse_loss_categories', {}))}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def render_inference_cache_report(**kwargs: Any) -> str:
    return format_inference_cache_report(build_inference_cache_report(**kwargs))


def write_inference_cache_audit_snapshot(
    report: dict[str, Any],
    *,
    json_output_path: Path | str,
    rendered_output_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    generated_at: str | None = None,
    git_commit_hash: str | None = None,
    resolve_git_commit_hash: bool = True,
) -> dict[str, Any]:
    snapshot = _build_inference_cache_snapshot(
        report,
        repo_root=repo_root,
        generated_at=generated_at,
        git_commit_hash=git_commit_hash,
        resolve_git_commit_hash=resolve_git_commit_hash,
    )
    json_payload = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
    _write_text_file(json_output_path, json_payload)
    if rendered_output_path is not None:
        _write_text_file(rendered_output_path, _format_inference_cache_snapshot(snapshot))
    return snapshot


def export_inference_cache_report(
    *,
    json_output_path: Path | str,
    rendered_output_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    event_log_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    last_n_events: int | None = None,
    last_n_hours: float | int | None = None,
    workflow_id: str | None = None,
    artifact_id: str | None = None,
    now_utc: str | None = None,
    diagnostic_config: dict[str, Any] | None = None,
    expansion_config: dict[str, Any] | None = None,
    generated_at: str | None = None,
    git_commit_hash: str | None = None,
    resolve_git_commit_hash: bool = True,
) -> dict[str, Any]:
    report = build_inference_cache_report(
        repo_root=repo_root,
        event_log_path=event_log_path,
        registry_path=registry_path,
        last_n_events=last_n_events,
        last_n_hours=last_n_hours,
        workflow_id=workflow_id,
        artifact_id=artifact_id,
        now_utc=now_utc,
        diagnostic_config=diagnostic_config,
        expansion_config=expansion_config,
    )
    return write_inference_cache_audit_snapshot(
        report,
        json_output_path=json_output_path,
        rendered_output_path=rendered_output_path,
        repo_root=repo_root,
        generated_at=generated_at,
        git_commit_hash=git_commit_hash,
        resolve_git_commit_hash=resolve_git_commit_hash,
    )


def build_inference_cache_report(
    *,
    repo_root: Path | str | None = None,
    event_log_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    last_n_events: int | None = None,
    last_n_hours: float | int | None = None,
    workflow_id: str | None = None,
    artifact_id: str | None = None,
    now_utc: str | None = None,
    diagnostic_config: dict[str, Any] | None = None,
    expansion_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_diagnostic_config = _merge_config(_DEFAULT_DIAGNOSTIC_CONFIG, diagnostic_config)
    resolved_expansion_config = _merge_config(_DEFAULT_EXPANSION_CONFIG, expansion_config)
    root = _get_root(repo_root)
    resolved_event_log_path = Path(event_log_path) if event_log_path else (
        root / "data" / "state" / "event_log.jsonl"
    )
    resolved_registry_path = Path(registry_path) if registry_path else (
        root / "data" / "state" / "inference_cache_registry.jsonl"
    )

    all_events = read_events(event_log_path=resolved_event_log_path)
    all_registry_entries = _load_registry_entries(resolved_registry_path)

    prefiltered_events = [
        event
        for event in all_events
        if _event_in_scope(
            event,
            workflow_id=workflow_id,
            artifact_id=artifact_id,
            cutoff=None,
        )
    ]
    prefiltered_registry_entries = [
        entry
        for entry in all_registry_entries
        if _entry_in_scope(
            entry,
            workflow_id=workflow_id,
            artifact_id=artifact_id,
            cutoff=None,
        )
    ]

    reference_time = _derive_reference_time(
        events=prefiltered_events,
        registry_entries=prefiltered_registry_entries,
        now_utc=now_utc,
    )
    cutoff = None
    if last_n_hours is not None and reference_time is not None:
        cutoff = reference_time - timedelta(hours=float(last_n_hours))
    elif last_n_hours is not None and reference_time is None:
        cutoff = datetime.max.replace(tzinfo=timezone.utc)

    filtered_events = [
        event
        for event in prefiltered_events
        if _event_in_scope(
            event,
            workflow_id=workflow_id,
            artifact_id=artifact_id,
            cutoff=cutoff,
        )
    ]
    if last_n_events is not None:
        filtered_events = filtered_events[-int(last_n_events):]

    filtered_registry_entries = [
        entry
        for entry in prefiltered_registry_entries
        if _entry_in_scope(
            entry,
            workflow_id=workflow_id,
            artifact_id=artifact_id,
            cutoff=cutoff,
        )
    ]

    summary = _initial_summary()
    event_counts_by_type: Counter[str] = Counter()
    reason_code_counts: Counter[str] = Counter()
    candidate_rejection_reason_code_counts: Counter[str] = Counter()
    workflow_event_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    workflow_reason_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    workflow_candidate_rejection_reason_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    policy_block_counts_by_workflow: Counter[str] = Counter()

    for event in filtered_events:
        event_type = str(event.get("event_type") or "")
        workflow_key = _workflow_id(event)
        payload = _payload(event)
        reason_code = str(payload.get("reason_code") or "").strip()

        summary["total_cache_related_events"] += 1
        event_counts_by_type[event_type] += 1
        workflow_event_counts[workflow_key][event_type] += 1

        if event_type in _EVENT_COUNT_FIELDS:
            summary[_EVENT_COUNT_FIELDS[event_type]] += 1
        if event_type in _SEMANTIC_TERMINAL_EVENT_TYPES and bool(payload.get("semantic_reuse_attempted")):
            summary["semantic_reuse_attempted_count"] += 1
        if bool(payload.get("policy_blocked")):
            summary["policy_block_count"] += 1
            policy_block_counts_by_workflow[workflow_key] += 1

        if reason_code and event_type in _TERMINAL_REASON_EVENT_TYPES:
            reason_code_counts[reason_code] += 1
            workflow_reason_counts[workflow_key][reason_code] += 1
        if reason_code and event_type in _CANDIDATE_REJECTION_EVENT_TYPES:
            candidate_rejection_reason_code_counts[reason_code] += 1
            workflow_candidate_rejection_reason_counts[workflow_key][reason_code] += 1

    prefix_denominator = (
        summary["prefix_cache_eligible_count"]
        + summary["prefix_cache_ineligible_count"]
    )
    prefix_eligibility_ratio = _round_ratio(
        summary["prefix_cache_eligible_count"],
        prefix_denominator,
    )
    validated_hit_rate = _round_ratio(
        summary["semantic_cache_hit_validated_count"],
        summary["semantic_reuse_attempted_count"],
    )
    candidate_rejection_rate = _candidate_rejection_rate(
        summary["semantic_cache_hit_rejected_count"],
        summary["semantic_reuse_attempted_count"],
    )
    policy_blocking_ratio = _policy_blocking_ratio(
        summary["policy_block_count"],
        summary["semantic_reuse_attempted_count"],
    )
    reuse_loss_categories = _derive_reuse_loss_categories(reason_code_counts)

    registry_entries_by_workflow: Counter[str] = Counter()
    registry_active_entries = 0
    registry_expired_entries = 0
    registry_entries_with_unknown_freshness = 0
    for entry in filtered_registry_entries:
        workflow_key = str(entry.get("workflow_id") or "").strip() or _DEFAULT_WORKFLOW_ID
        registry_entries_by_workflow[workflow_key] += 1
        expires_at = _parse_utc(str(entry.get("expires_at") or ""))
        if reference_time is None or expires_at is None:
            registry_entries_with_unknown_freshness += 1
        elif expires_at < reference_time:
            registry_expired_entries += 1
        else:
            registry_active_entries += 1

    report = {
        "report_version": INFERENCE_CACHE_ACTIVITY_REPORT_VERSION,
        "source_paths": {
            "event_log_path": str(resolved_event_log_path),
            "registry_path": str(resolved_registry_path),
        },
        "filters": {
            "last_n_events": int(last_n_events) if last_n_events is not None else None,
            "last_n_hours": float(last_n_hours) if last_n_hours is not None else None,
            "workflow_id": workflow_id,
            "artifact_id": artifact_id,
            "reference_time": _isoformat_utc(reference_time),
            "window_start": _isoformat_utc(cutoff),
            "last_n_events_applies_to": "events_only" if last_n_events is not None else None,
        },
        "total_cache_related_events": summary["total_cache_related_events"],
        "prefix_cache_eligible_count": summary["prefix_cache_eligible_count"],
        "prefix_cache_ineligible_count": summary["prefix_cache_ineligible_count"],
        "semantic_reuse_attempted_count": summary["semantic_reuse_attempted_count"],
        "semantic_cache_hit_validated_count": summary["semantic_cache_hit_validated_count"],
        "semantic_cache_hit_rejected_count": summary["semantic_cache_hit_rejected_count"],
        "semantic_cache_miss_count": summary["semantic_cache_miss_count"],
        "cache_entry_written_count": summary["cache_entry_written_count"],
        "cache_entry_expired_count": summary["cache_entry_expired_count"],
        "cache_bypassed_by_policy_count": summary["cache_bypassed_by_policy_count"],
        "policy_block_count": summary["policy_block_count"],
        "validated_hit_rate": validated_hit_rate,
        "candidate_rejection_rate": candidate_rejection_rate,
        "policy_blocking_ratio": policy_blocking_ratio,
        "prefix_eligibility_ratio": prefix_eligibility_ratio,
        "event_counts_by_type": {
            event_type: event_counts_by_type.get(event_type, 0)
            for event_type in _CACHE_EVENT_TYPES
        },
        "reason_code_counts": _sorted_counter(reason_code_counts),
        "candidate_rejection_reason_code_counts": _sorted_counter(
            candidate_rejection_reason_code_counts
        ),
        "reuse_loss_categories": reuse_loss_categories,
        "policy_block_counts_by_workflow": _sorted_counter(policy_block_counts_by_workflow),
        "workflow_breakdown": _finalize_breakdown(
            workflow_event_counts,
            workflow_reason_counts,
            workflow_candidate_rejection_reason_counts,
            registry_entries_by_workflow,
            policy_block_counts_by_workflow,
        ),
        "registry_summary": {
            "entries_in_scope": len(filtered_registry_entries),
            "active_entries": registry_active_entries,
            "expired_entries": registry_expired_entries,
            "entries_with_unknown_freshness": registry_entries_with_unknown_freshness,
            "entries_by_workflow": _sorted_counter(registry_entries_by_workflow),
        },
    }
    report["diagnostics"] = _build_diagnostics(
        report_summary=report,
        workflow_breakdown=report["workflow_breakdown"],
        diagnostic_config=resolved_diagnostic_config,
    )
    report["candidate_workflows_for_expansion"] = _build_expansion_candidates(
        workflow_breakdown=report["workflow_breakdown"],
        expansion_config=resolved_expansion_config,
    )
    return report


def summarize_inference_cache_activity(**kwargs: Any) -> dict[str, Any]:
    return build_inference_cache_report(**kwargs)


def audit_inference_cache_activity(**kwargs: Any) -> dict[str, Any]:
    return build_inference_cache_report(**kwargs)
