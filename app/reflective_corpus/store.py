from __future__ import annotations

from pathlib import Path
from typing import Any

from app.reflective_corpus.models import (
    ESSAY_CANDIDATE_RECORD_TYPE,
    ESSAY_CANDIDATE_STATUSES,
    FRAGMENT_RECORD_TYPE,
    PRESSURE_RECORD_TYPE,
    THEME_RECORD_TYPE,
    THEME_STATUSES,
    validate_essay_candidate_record,
    validate_fragment_record,
    validate_pressure_record,
    validate_theme_record,
)
from app.retention.jsonl_store import append_record, iter_jsonl


FRAGMENTS_FILE = "reflective_fragments.jsonl"
THEMES_FILE = "reflective_themes.jsonl"
PRESSURES_FILE = "reflective_pressures.jsonl"
ESSAY_CANDIDATES_FILE = "essay_candidates.jsonl"


def append_fragment(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_fragment_record(record)
    if get_fragment_by_id(str(record["fragment_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_fragment:{record['fragment_id']}")
    return append_record(
        FRAGMENTS_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["captured_at"],
    )


def append_theme(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_theme_record(record)
    if get_theme_by_id(str(record["theme_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_theme:{record['theme_id']}")
    return append_record(
        THEMES_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["created_at"],
    )


def append_pressure(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_pressure_record(record)
    _validate_fragment_references(record["fragment_ids"], repo_root=repo_root)
    _validate_theme_references(record["related_theme_ids"], repo_root=repo_root)
    if get_pressure_by_id(str(record["pressure_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_pressure:{record['pressure_id']}")
    return append_record(
        PRESSURES_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["detected_at"],
    )


def append_essay_candidate(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_essay_candidate_record(record)
    _validate_pressure_references(record["pressure_ids"], repo_root=repo_root)
    _validate_fragment_references(record["fragment_ids"], repo_root=repo_root)
    _validate_theme_references(record["theme_ids"], repo_root=repo_root)
    if get_essay_candidate_by_id(str(record["candidate_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_essay_candidate:{record['candidate_id']}")
    return append_record(
        ESSAY_CANDIDATES_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["created_at"],
    )


def list_fragments(limit: int | None = None, *, repo_root: Path | None = None) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(FRAGMENTS_FILE, repo_root=repo_root)
        if row.get("record_type") == FRAGMENT_RECORD_TYPE
    ]
    for row in rows:
        validate_fragment_record(row)
    return _apply_limit(_sort_rows(rows, "captured_at", "fragment_id"), limit)


def list_themes(
    status: str | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(THEMES_FILE, repo_root=repo_root)
        if row.get("record_type") == THEME_RECORD_TYPE
    ]
    for row in rows:
        validate_theme_record(row)
    if status is not None:
        target = _normalize_status_filter(status)
        rows = [row for row in rows if row["status"] == target]
    return sorted(rows, key=lambda row: (str(row["name"]).lower(), str(row["theme_id"])))


def list_pressures(limit: int | None = None, *, repo_root: Path | None = None) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(PRESSURES_FILE, repo_root=repo_root)
        if row.get("record_type") == PRESSURE_RECORD_TYPE
    ]
    for row in rows:
        validate_pressure_record(row)
    return _apply_limit(_sort_rows(rows, "detected_at", "pressure_id"), limit)


def list_essay_candidates(
    status: str | None = None,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(ESSAY_CANDIDATES_FILE, repo_root=repo_root)
        if row.get("record_type") == ESSAY_CANDIDATE_RECORD_TYPE
    ]
    for row in rows:
        validate_essay_candidate_record(row)
    if status is not None:
        target = _normalize_candidate_status_filter(status)
        rows = [row for row in rows if row["status"] == target]
    return _apply_limit(_sort_rows(rows, "created_at", "candidate_id"), limit)


def get_fragment_by_id(fragment_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_fragments(repo_root=repo_root), "fragment_id", fragment_id)


def get_theme_by_id(theme_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_themes(repo_root=repo_root), "theme_id", theme_id)


def get_theme_by_name(name: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    target = str(name or "").strip().lower()
    for row in list_themes(repo_root=repo_root):
        if str(row["name"]).strip().lower() == target:
            return row
    return None


def get_pressure_by_id(pressure_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_pressures(repo_root=repo_root), "pressure_id", pressure_id)


def get_essay_candidate_by_id(candidate_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_essay_candidates(repo_root=repo_root), "candidate_id", candidate_id)


def _validate_fragment_references(fragment_ids: list[str], *, repo_root: Path | None = None) -> None:
    for fragment_id in fragment_ids:
        if get_fragment_by_id(fragment_id, repo_root=repo_root) is None:
            raise ValueError(f"unknown_fragment:{fragment_id}")


def _validate_theme_references(theme_ids: list[str], *, repo_root: Path | None = None) -> None:
    for theme_id in theme_ids:
        if get_theme_by_id(theme_id, repo_root=repo_root) is None:
            raise ValueError(f"unknown_theme:{theme_id}")


def _validate_pressure_references(pressure_ids: list[str], *, repo_root: Path | None = None) -> None:
    for pressure_id in pressure_ids:
        if get_pressure_by_id(pressure_id, repo_root=repo_root) is None:
            raise ValueError(f"unknown_pressure:{pressure_id}")


def _find_latest(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any] | None:
    target = str(value or "").strip()
    matched = None
    for row in rows:
        if row.get(field) == target:
            matched = row
    return matched


def _sort_rows(rows: list[dict[str, Any]], date_field: str, id_field: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (str(row.get(date_field) or ""), str(row.get(id_field) or "")))


def _apply_limit(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return rows
    parsed = int(limit)
    if parsed < 0:
        raise ValueError("limit_must_be_non_negative")
    if parsed == 0:
        return []
    return rows[-parsed:]


def _normalize_status_filter(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized not in THEME_STATUSES:
        raise ValueError(f"unsupported_theme_status:{status}")
    return normalized


def _normalize_candidate_status_filter(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized not in ESSAY_CANDIDATE_STATUSES:
        raise ValueError(f"unsupported_candidate_status:{status}")
    return normalized
