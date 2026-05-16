from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.retention.jsonl_store import append_record, iter_jsonl
from app.spine_observability.laviathon import normalize_observation


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
    normalized = normalize_observation(observation)
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


def _strip_store_metadata(row: Mapping[str, Any]) -> dict:
    return {
        key: value
        for key, value in row.items()
        if key not in STORE_METADATA_FIELDS
    }

