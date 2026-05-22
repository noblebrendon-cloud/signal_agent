from __future__ import annotations

from pathlib import Path
from typing import Any

from app.reflective_pressure.store import (
    get_input_by_id,
    list_classifications,
    list_corrections,
    list_drafts,
    list_observations,
)


def build_review_packet(input_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    input_record = get_input_by_id(input_id, repo_root=repo_root)
    if input_record is None:
        raise ValueError(f"unknown_input:{input_id}")
    classifications = list_classifications(input_id=input_id, repo_root=repo_root)
    drafts = list_drafts(input_id=input_id, repo_root=repo_root)
    observations = list_observations(input_id=input_id, repo_root=repo_root)
    corrections = list_corrections(input_id=input_id, repo_root=repo_root)
    latest_classification = classifications[-1] if classifications else None
    return {
        "schema_version": "1.0",
        "input": input_record,
        "latest_classification": latest_classification,
        "corrections": corrections,
        "drafts": drafts,
        "observations": observations,
        "suggested_next_action": _suggest_next_action(latest_classification, drafts, observations, corrections),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _suggest_next_action(
    latest_classification: dict[str, Any] | None,
    drafts: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> str:
    if latest_classification is None:
        return "classify"
    if _is_high_risk(latest_classification):
        return "human_review_required"
    if not drafts:
        return "generate_draft"
    if not observations:
        return "record_observation_after_manual_posting"
    if _has_high_recognition(observations) and corrections:
        return "consider_golden_example"
    return "monitor"


def _is_high_risk(classification: dict[str, Any]) -> bool:
    return (
        int(classification.get("risk_of_tribal_escalation") or 0) >= 4
        or int(classification.get("moral_temperature") or 0) >= 4
    )


def _has_high_recognition(observations: list[dict[str, Any]]) -> bool:
    return any(float(row.get("recognition_events") or 0) >= 5 for row in observations)
