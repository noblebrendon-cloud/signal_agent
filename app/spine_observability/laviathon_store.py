from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.retention.identity import normalize_token
from app.retention.jsonl_store import append_record, iter_jsonl
from app.spine_observability.laviathon import ALLOWED_OBSERVATION_TYPES, normalize_observation


LAVIATHON_OBSERVATIONS_FILE = "laviathon_observations.jsonl"

STORE_METADATA_FIELDS = (
    "recorded_at",
    "prev_hash",
    "record_hash",
)


def append_laviathon_observation(
    observation: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict:
    normalized = normalize_observation(observation, require_entity_id=True)
    return append_record(
        LAVIATHON_OBSERVATIONS_FILE,
        normalized,
        repo_root=repo_root,
        recorded_at=normalized["created_at"],
    )


def list_laviathon_observations(*, repo_root: Path | None = None) -> list[dict]:
    rows = iter_jsonl(LAVIATHON_OBSERVATIONS_FILE, repo_root=repo_root)
    for row in rows:
        normalize_observation(_strip_store_metadata(row))
    return rows


def list_review_candidates(
    *,
    include_all_statuses: bool = False,
    observation_type: str | None = None,
    repo_root: Path | None = None,
) -> list[dict]:
    if not isinstance(include_all_statuses, bool):
        raise ValueError("invalid_include_all_statuses")
    type_filter = _normalize_observation_type_filter(observation_type)
    rows = []
    for row in list_laviathon_observations(repo_root=repo_root):
        if row["requires_human_review"] is not True:
            continue
        if not include_all_statuses and row["review_status"] != "pending":
            continue
        if type_filter is not None and row["observation_type"] != type_filter:
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: (row["created_at"], row["observation_id"]))


def _strip_store_metadata(row: Mapping[str, Any]) -> dict:
    return {
        key: value
        for key, value in row.items()
        if key not in STORE_METADATA_FIELDS
    }


def _normalize_observation_type_filter(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_observation_type")
    normalized = normalize_token(value)
    if normalized not in ALLOWED_OBSERVATION_TYPES:
        raise ValueError(f"invalid_observation_type:{normalized}")
    return normalized
