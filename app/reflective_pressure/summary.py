from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.reflective_pressure.store import (
    get_classification_by_id,
    list_classifications,
    list_corrections,
    list_drafts,
    list_golden_examples,
    list_inputs,
    list_observations,
)


def summarize_by_pressure_type(*, repo_root: Path | None = None) -> dict[str, Any]:
    classifications = list_classifications(repo_root=repo_root)
    observations = list_observations(repo_root=repo_root)
    drafts = list_drafts(repo_root=repo_root)
    draft_by_id = {row["draft_id"]: row for row in drafts}
    pressure_by_input = {row["input_id"]: row["pressure_type"] for row in classifications}
    counts = Counter(row["pressure_type"] for row in classifications)
    recognition_by_pressure: dict[str, float] = defaultdict(float)
    observation_count_by_pressure: Counter[str] = Counter()
    for observation in observations:
        pressure_type = pressure_by_input.get(observation["input_id"], "unknown")
        if observation["draft_id"] not in draft_by_id:
            continue
        observation_count_by_pressure[pressure_type] += 1
        recognition_by_pressure[pressure_type] += float(observation["recognition_events"])
    return {
        "schema_version": "1.0",
        "group_by": "pressure_type",
        "counts": _sorted_counter(counts),
        "observation_counts": _sorted_counter(observation_count_by_pressure),
        "recognition_events": _sorted_number_map(recognition_by_pressure),
    }


def summarize_by_platform(*, repo_root: Path | None = None) -> dict[str, Any]:
    inputs = list_inputs(repo_root=repo_root)
    observations = list_observations(repo_root=repo_root)
    platform_by_input = {row["input_id"]: row["source_platform"] for row in inputs}
    counts = Counter(row["source_platform"] for row in inputs)
    views_by_platform: dict[str, float] = defaultdict(float)
    comments_by_platform: dict[str, float] = defaultdict(float)
    for observation in observations:
        platform = platform_by_input.get(observation["input_id"], "unknown")
        views_by_platform[platform] += float(observation["views"])
        comments_by_platform[platform] += float(observation["comments"])
    return {
        "schema_version": "1.0",
        "group_by": "platform",
        "input_counts": _sorted_counter(counts),
        "views": _sorted_number_map(views_by_platform),
        "comments": _sorted_number_map(comments_by_platform),
    }


def summarize_by_spine(*, repo_root: Path | None = None) -> dict[str, Any]:
    inputs = list_inputs(repo_root=repo_root)
    drafts = list_drafts(repo_root=repo_root)
    input_counts = Counter(row["intended_spine"] for row in inputs)
    draft_counts = Counter(row["target_spine"] for row in drafts)
    return {
        "schema_version": "1.0",
        "group_by": "spine",
        "input_counts": _sorted_counter(input_counts),
        "draft_counts": _sorted_counter(draft_counts),
    }


def summarize_recognition_signals(*, repo_root: Path | None = None) -> dict[str, Any]:
    observations = list_observations(repo_root=repo_root)
    count = len(observations)
    return {
        "schema_version": "1.0",
        "summary": "recognition",
        "observation_count": count,
        "total_recognition_events": _sum(observations, "recognition_events"),
        "total_saves": _sum(observations, "saves"),
        "total_profile_clicks": _sum(observations, "profile_clicks"),
        "average_constructive_reply_ratio": _average(observations, "constructive_reply_ratio"),
        "average_self_insertion_density": _average(observations, "self_insertion_density"),
    }


def summarize_risk_signals(*, repo_root: Path | None = None) -> dict[str, Any]:
    classifications = list_classifications(repo_root=repo_root)
    observations = list_observations(repo_root=repo_root)
    high_risk = [
        row
        for row in classifications
        if int(row["risk_of_tribal_escalation"]) >= 4 or int(row["moral_temperature"]) >= 4
    ]
    contradiction_values = [float(row["contradiction_heat"]) for row in observations]
    return {
        "schema_version": "1.0",
        "summary": "risk",
        "classification_count": len(classifications),
        "high_risk_classification_count": len(high_risk),
        "average_risk_of_tribal_escalation": _average(classifications, "risk_of_tribal_escalation"),
        "average_moral_temperature": _average(classifications, "moral_temperature"),
        "average_contradiction_heat": _average(observations, "contradiction_heat"),
        "max_contradiction_heat": max(contradiction_values) if contradiction_values else 0,
    }


def summarize_recent_activity(limit: int = 20, *, repo_root: Path | None = None) -> dict[str, Any]:
    parsed_limit = int(limit)
    if parsed_limit < 0:
        raise ValueError("limit_must_be_non_negative")
    rows: list[dict[str, Any]] = []
    rows.extend(_activity_rows("input", "input_id", list_inputs(repo_root=repo_root)))
    rows.extend(_activity_rows("classification", "classification_id", list_classifications(repo_root=repo_root)))
    rows.extend(_activity_rows("draft", "draft_id", list_drafts(repo_root=repo_root)))
    rows.extend(_activity_rows("observation", "observation_id", list_observations(repo_root=repo_root)))
    rows = sorted(rows, key=lambda row: (str(row["created_at"]), str(row["record_id"])))
    if parsed_limit:
        rows = rows[-parsed_limit:]
    else:
        rows = []
    return {
        "schema_version": "1.0",
        "summary": "recent_activity",
        "limit": parsed_limit,
        "activity": rows,
    }


def summarize_corrections_by_pressure_type(*, repo_root: Path | None = None) -> dict[str, Any]:
    corrections = list_corrections(repo_root=repo_root)
    counts = Counter(row["corrected_pressure_type"] for row in corrections)
    by_corrected_by = Counter(row["corrected_by"] for row in corrections)
    return {
        "schema_version": "1.0",
        "summary": "corrections_by_pressure_type",
        "correction_count": len(corrections),
        "counts": _sorted_counter(counts),
        "corrected_by": _sorted_counter(by_corrected_by),
    }


def summarize_golden_examples(*, repo_root: Path | None = None) -> dict[str, Any]:
    examples = list_golden_examples(repo_root=repo_root)
    approved = [row for row in examples if row["approved_for_prompt_export"] is True]
    counts = Counter(row["pressure_type"] for row in examples)
    approved_counts = Counter(row["pressure_type"] for row in approved)
    return {
        "schema_version": "1.0",
        "summary": "golden_examples",
        "golden_count": len(examples),
        "approved_for_prompt_export_count": len(approved),
        "counts": _sorted_counter(counts),
        "approved_counts": _sorted_counter(approved_counts),
    }


def summarize_classification_vs_correction_drift(*, repo_root: Path | None = None) -> dict[str, Any]:
    corrections = [
        row
        for row in list_corrections(repo_root=repo_root)
        if row["target_record_type"] == "classification"
    ]
    pair_counts: Counter[str] = Counter()
    drifted_count = 0
    for correction in corrections:
        classification = get_classification_by_id(correction["target_record_id"], repo_root=repo_root)
        if classification is None:
            continue
        original = str(classification["pressure_type"])
        corrected = str(correction["corrected_pressure_type"])
        pair_counts[f"{original}->{corrected}"] += 1
        if original != corrected:
            drifted_count += 1
    return {
        "schema_version": "1.0",
        "summary": "classification_vs_correction_drift",
        "correction_count": len(corrections),
        "drifted_pressure_type_count": drifted_count,
        "pairs": _sorted_counter(pair_counts),
    }


def summarize_ready_for_prompt_export(*, repo_root: Path | None = None) -> dict[str, Any]:
    approved_examples = list_golden_examples(approved_only=True, repo_root=repo_root)
    counts = Counter(row["pressure_type"] for row in approved_examples)
    return {
        "schema_version": "1.0",
        "summary": "ready_for_prompt_export",
        "ready_count": len(approved_examples),
        "counts": _sorted_counter(counts),
        "golden_ids": [row["golden_id"] for row in approved_examples],
    }


def summarize_operational_next_actions(*, repo_root: Path | None = None) -> dict[str, Any]:
    inputs = list_inputs(repo_root=repo_root)
    classifications_by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    drafts_by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observations_by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    corrections_by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in list_classifications(repo_root=repo_root):
        classifications_by_input[row["input_id"]].append(row)
    for row in list_drafts(repo_root=repo_root):
        drafts_by_input[row["input_id"]].append(row)
    for row in list_observations(repo_root=repo_root):
        observations_by_input[row["input_id"]].append(row)
    for row in list_corrections(repo_root=repo_root):
        corrections_by_input[row["input_id"]].append(row)

    actions: Counter[str] = Counter()
    input_actions: list[dict[str, str]] = []
    for input_record in inputs:
        input_id = input_record["input_id"]
        latest_classification = (classifications_by_input.get(input_id) or [None])[-1]
        action = _next_action(
            latest_classification,
            drafts_by_input.get(input_id, []),
            observations_by_input.get(input_id, []),
            corrections_by_input.get(input_id, []),
        )
        actions[action] += 1
        input_actions.append({"input_id": input_id, "suggested_next_action": action})
    return {
        "schema_version": "1.0",
        "summary": "operational_next_actions",
        "counts": _sorted_counter(actions),
        "inputs": input_actions,
    }


def _activity_rows(kind: str, id_field: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "activity_type": kind,
            "record_id": row[id_field],
            "created_at": row["created_at"],
            "input_id": row.get("input_id"),
        }
        for row in rows
    ]


def _next_action(
    latest_classification: dict[str, Any] | None,
    drafts: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> str:
    if latest_classification is None:
        return "classify"
    if int(latest_classification["risk_of_tribal_escalation"]) >= 4 or int(latest_classification["moral_temperature"]) >= 4:
        return "human_review_required"
    if not drafts:
        return "generate_draft"
    if not observations:
        return "record_observation_after_manual_posting"
    if any(float(row["recognition_events"]) >= 5 for row in observations) and corrections:
        return "consider_golden_example"
    return "monitor"


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _sorted_number_map(values: dict[str, float]) -> dict[str, int | float]:
    return {key: _clean_number(values[key]) for key in sorted(values)}


def _sum(rows: list[dict[str, Any]], field: str) -> int | float:
    return _clean_number(sum(float(row[field]) for row in rows))


def _average(rows: list[dict[str, Any]], field: str) -> int | float:
    if not rows:
        return 0
    return _clean_number(sum(float(row[field]) for row in rows) / len(rows))


def _clean_number(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return round(float(value), 6)
