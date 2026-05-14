from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.retention.jsonl_store import append_record, iter_jsonl

from app.spine_observability.models import (
    build_metric_snapshot_record,
    build_platform_account_record,
    build_spine_record,
    validate_metric_snapshot_record,
    validate_platform_account_record,
    validate_spine_record,
)


SPINES_FILE = "spine_observability_spines.jsonl"
PLATFORMS_FILE = "spine_observability_platforms.jsonl"
METRIC_SNAPSHOTS_FILE = "spine_observability_metric_snapshots.jsonl"


def add_spine(
    *,
    name: str,
    description: str,
    created_at: str | None = None,
    active: bool = True,
    repo_root: Path | None = None,
) -> dict:
    record = build_spine_record(
        name=name,
        description=description,
        created_at=created_at,
        active=active,
    )
    if get_spine_by_id(record["spine_id"], repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_spine:{record['spine_id']}")
    return append_record(
        SPINES_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["created_at"],
    )


def list_spines(*, repo_root: Path | None = None) -> list[dict]:
    rows = iter_jsonl(SPINES_FILE, repo_root=repo_root)
    for row in rows:
        validate_spine_record(row)
    return sorted(rows, key=lambda row: (str(row["name"]).lower(), str(row["spine_id"])))


def get_spine_by_id(spine_id: str, *, repo_root: Path | None = None) -> dict | None:
    target = _required_lookup_value("spine_id", spine_id)
    for row in list_spines(repo_root=repo_root):
        if row["spine_id"] == target:
            return row
    return None


def get_spine_by_name(name: str, *, repo_root: Path | None = None) -> dict | None:
    target = _required_lookup_value("name", name).lower()
    for row in list_spines(repo_root=repo_root):
        if str(row["name"]).lower() == target:
            return row
    return None


def add_platform_account(
    *,
    spine_id: str,
    platform: str,
    account_label: str,
    content_lane: str,
    created_at: str | None = None,
    active: bool = True,
    repo_root: Path | None = None,
) -> dict:
    if get_spine_by_id(spine_id, repo_root=repo_root) is None:
        raise ValueError(f"unknown_spine:{spine_id}")
    record = build_platform_account_record(
        spine_id=spine_id,
        platform=platform,
        account_label=account_label,
        content_lane=content_lane,
        created_at=created_at,
        active=active,
    )
    if get_platform_account_by_id(record["platform_account_id"], repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_platform_account:{record['platform_account_id']}")
    return append_record(
        PLATFORMS_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["created_at"],
    )


def add_platform_account_by_spine_name(
    *,
    spine_name: str,
    platform: str,
    account_label: str,
    content_lane: str,
    created_at: str | None = None,
    active: bool = True,
    repo_root: Path | None = None,
) -> dict:
    spine = get_spine_by_name(spine_name, repo_root=repo_root)
    if spine is None:
        raise ValueError(f"unknown_spine_name:{spine_name}")
    return add_platform_account(
        spine_id=spine["spine_id"],
        platform=platform,
        account_label=account_label,
        content_lane=content_lane,
        created_at=created_at,
        active=active,
        repo_root=repo_root,
    )


def list_platform_accounts(*, repo_root: Path | None = None) -> list[dict]:
    rows = iter_jsonl(PLATFORMS_FILE, repo_root=repo_root)
    known_spines = {row["spine_id"] for row in list_spines(repo_root=repo_root)}
    for row in rows:
        validate_platform_account_record(row)
        if row["spine_id"] not in known_spines:
            raise ValueError(f"unknown_spine_reference:{row['spine_id']}")
    return sorted(
        rows,
        key=lambda row: (
            str(row["spine_id"]),
            str(row["platform"]),
            str(row["account_label"]).lower(),
            str(row["platform_account_id"]),
        ),
    )


def get_platform_account_by_id(
    platform_account_id: str,
    *,
    repo_root: Path | None = None,
) -> dict | None:
    target = _required_lookup_value("platform_account_id", platform_account_id)
    for row in list_platform_accounts(repo_root=repo_root):
        if row["platform_account_id"] == target:
            return row
    return None


def add_metric_snapshot(
    *,
    platform_account_id: str,
    captured_at: str,
    metric_window_start: str,
    metric_window_end: str,
    metrics: Mapping[str, Any],
    notes: str = "",
    source_type: str = "manual",
    external_action_allowed: bool = False,
    repo_root: Path | None = None,
) -> dict:
    if get_platform_account_by_id(platform_account_id, repo_root=repo_root) is None:
        raise ValueError(f"unknown_platform_account:{platform_account_id}")
    record = build_metric_snapshot_record(
        platform_account_id=platform_account_id,
        captured_at=captured_at,
        metric_window_start=metric_window_start,
        metric_window_end=metric_window_end,
        metrics=metrics,
        notes=notes,
        source_type=source_type,
        external_action_allowed=external_action_allowed,
    )
    if get_metric_snapshot_by_id(record["snapshot_id"], repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_metric_snapshot:{record['snapshot_id']}")
    return append_record(
        METRIC_SNAPSHOTS_FILE,
        record,
        repo_root=repo_root,
        recorded_at=record["captured_at"],
    )


def list_metric_snapshots(*, repo_root: Path | None = None) -> list[dict]:
    rows = iter_jsonl(METRIC_SNAPSHOTS_FILE, repo_root=repo_root)
    known_platforms = {
        row["platform_account_id"]
        for row in list_platform_accounts(repo_root=repo_root)
    }
    for row in rows:
        validate_metric_snapshot_record(row)
        if row["platform_account_id"] not in known_platforms:
            raise ValueError(f"unknown_platform_account_reference:{row['platform_account_id']}")
    return sorted(
        rows,
        key=lambda row: (
            str(row["platform_account_id"]),
            str(row["captured_at"]),
            str(row["snapshot_id"]),
        ),
    )


def get_metric_snapshot_by_id(
    snapshot_id: str,
    *,
    repo_root: Path | None = None,
) -> dict | None:
    target = _required_lookup_value("snapshot_id", snapshot_id)
    for row in list_metric_snapshots(repo_root=repo_root):
        if row["snapshot_id"] == target:
            return row
    return None


def _required_lookup_value(field: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing_{field}")
    return value.strip()

