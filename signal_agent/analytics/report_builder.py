from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_FORBIDDEN_REPO_OUTPUT_ROOTS = (
    "app",
    "config",
    "constraints",
    "formal_governance",
    "governance",
    "signal_agent",
)
_FORBIDDEN_DATA_CHILDREN = {"state"}


def render_self_observation_markdown(report: Mapping[str, Any]) -> str:
    metrics = _mapping(report.get("metrics"))
    lines = [
        "# Self-Observation Report",
        "",
        f"- schema_version: {_scalar(report.get('schema_version'))}",
        f"- repo_root: {_scalar(report.get('repo_root'))}",
        f"- primary_input_available: {_scalar(report.get('primary_input_available'))}",
        "",
        "## Source Files",
    ]
    for name, source in sorted(_mapping(report.get("source_files")).items()):
        source_map = _mapping(source)
        lines.append(
            "- "
            + name
            + ": "
            + ", ".join(
                [
                    f"exists={_scalar(source_map.get('exists'))}",
                    f"parsed={_scalar(source_map.get('parsed_line_count'))}",
                    f"malformed={_scalar(source_map.get('malformed_line_count'))}",
                    f"rows_in_scope={_scalar(source_map.get('rows_in_scope'))}",
                ]
            )
        )

    lines.extend(
        [
            "",
            "## Governance Metrics",
            f"- transition_counts_by_status: {_format_mapping(metrics.get('transition_counts_by_status'))}",
            f"- failed_transition_count: {_scalar(metrics.get('failed_transition_count'))}",
            f"- policy_denial_count: {_scalar(metrics.get('policy_denial_count'))}",
            f"- operator_run_counts_by_status: {_format_mapping(metrics.get('operator_run_counts_by_status'))}",
            f"- provider_retry_count: {_scalar(metrics.get('provider_retry_count'))}",
            f"- provider_fallback_count: {_scalar(metrics.get('provider_fallback_count'))}",
            f"- circuit_breaker_count: {_scalar(metrics.get('circuit_breaker_count'))}",
        ]
    )
    lines.extend(
        [
            "",
            "## Transition Classification Coverage",
            f"- rejected_transition_count: {_scalar(metrics.get('rejected_transition_count'))}",
            f"- explicitly_classified_rejection_count: {_scalar(metrics.get('explicitly_classified_rejection_count'))}",
            f"- legacy_fallback_rejection_count: {_scalar(metrics.get('legacy_fallback_rejection_count'))}",
            f"- legacy_unknown_rejection_count: {_scalar(metrics.get('legacy_unknown_rejection_count'))}",
            f"- classification_coverage_ratio: {_scalar(metrics.get('classification_coverage_ratio'))}",
            f"- rejection_evidence_quality_counts: {_format_mapping(metrics.get('rejection_evidence_quality_counts'))}",
            "- denial_reasons_by_evidence_quality:",
        ]
    )
    for quality, reasons in sorted(_mapping(metrics.get("denial_reasons_by_evidence_quality")).items()):
        lines.append(f"  - {quality}: {_format_mapping(reasons)}")
    lines.append("- denial_categories_by_source:")
    categories_by_source = _mapping(metrics.get("denial_categories_by_source"))
    if categories_by_source:
        for source, categories in sorted(categories_by_source.items()):
            lines.append(f"  - {source}: {_format_mapping(categories)}")
    else:
        lines.append("  - none")

    lines.extend(["", "## Cache Summary"])
    cache_summary = _mapping(metrics.get("cache_summary"))
    if cache_summary.get("available"):
        lines.extend(
            [
                f"- total_cache_related_events: {_scalar(cache_summary.get('total_cache_related_events'))}",
                f"- semantic_reuse_attempted_count: {_scalar(cache_summary.get('semantic_reuse_attempted_count'))}",
                f"- semantic_cache_hit_validated_count: {_scalar(cache_summary.get('semantic_cache_hit_validated_count'))}",
                f"- semantic_cache_miss_count: {_scalar(cache_summary.get('semantic_cache_miss_count'))}",
                f"- validated_hit_rate: {_scalar(cache_summary.get('validated_hit_rate'))}",
            ]
        )
    else:
        lines.append(f"- unavailable: {_scalar(cache_summary.get('reason'))}")

    lines.extend(["", "## Repeated Patterns"])
    repeated = _mapping(report.get("repeated_patterns"))
    for name, values in sorted(repeated.items()):
        lines.append(f"- {name}:")
        for item in _list(values)[:10]:
            lines.append(f"  - {_format_mapping(item)}")
        if not _list(values):
            lines.append("  - none")

    lines.extend(["", "## Subsystem Candidates"])
    candidates = _list(report.get("subsystem_candidates"))
    if not candidates:
        lines.append("- none")
    for candidate in candidates[:10]:
        candidate_map = _mapping(candidate)
        repeated_pattern = _mapping(candidate_map.get("repeated_pattern"))
        lines.append(
            "- "
            + f"candidate_id={_scalar(candidate_map.get('candidate_id'))}, "
            + f"name_guess={_scalar(candidate_map.get('name_guess'))}, "
            + f"confidence={_scalar(candidate_map.get('confidence'))}, "
            + f"pattern={_format_mapping(repeated_pattern)}"
        )
        involved = _list(candidate_map.get("involved_files_or_events"))
        if involved:
            lines.append(f"  - evidence_refs: {', '.join(_scalar(item) for item in involved[:5])}")
        recommended = candidate_map.get("recommended_next_action")
        if recommended:
            lines.append(f"  - recommended_next_action: {_scalar(recommended)}")

    lines.extend(["", "## Recommendations"])
    recommendations = _list(report.get("recommendations"))
    if not recommendations:
        lines.append("- none")
    for recommendation in recommendations:
        lines.append(f"- {_scalar(recommendation)}")

    lines.extend(["", "## Warnings"])
    warnings = _list(report.get("warnings"))
    if not warnings:
        lines.append("- none")
    for warning in warnings:
        lines.append(f"- {_scalar(warning)}")

    return "\n".join(lines) + "\n"


def write_self_observation_report(
    report: Mapping[str, Any],
    json_output: Path | str,
    markdown_output: Path | str | None = None,
) -> None:
    repo_root = Path(str(report.get("repo_root") or ".")).resolve()
    json_path = _validate_report_output_path(repo_root, json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if markdown_output is not None:
        markdown_path = _validate_report_output_path(repo_root, markdown_output)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_self_observation_markdown(report),
            encoding="utf-8",
        )


def _validate_report_output_path(repo_root: Path, output_path: Path | str) -> Path:
    candidate = Path(output_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError:
        return resolved

    parts = relative.parts
    if not parts:
        raise ValueError("report output path must name a file")
    first = parts[0]
    if first in _FORBIDDEN_REPO_OUTPUT_ROOTS:
        raise ValueError(f"report output path is inside forbidden canonical root: {first}")
    if first == "data" and len(parts) > 1 and parts[1] in _FORBIDDEN_DATA_CHILDREN:
        raise ValueError("report output path must not be inside data/state")
    return resolved


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_mapping(value: Any) -> str:
    mapping = _mapping(value)
    if not mapping:
        return "none"
    return ", ".join(
        f"{key}={_scalar(mapping[key])}"
        for key in sorted(mapping)
    )
