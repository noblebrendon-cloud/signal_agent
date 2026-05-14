from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.retention.identity import utc_now_iso

from app.spine_observability.store import (
    list_metric_snapshots,
    list_platform_accounts,
    list_spines,
)


def build_spine_summary(
    *,
    under_tracked_days: int = 7,
    as_of: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    effective_as_of = _canonical_as_of(as_of)
    spines = list_spines(repo_root=repo_root)
    platforms = list_platform_accounts(repo_root=repo_root)
    metrics = list_metric_snapshots(repo_root=repo_root)
    under_tracked = find_under_tracked_platforms(
        days=under_tracked_days,
        as_of=effective_as_of,
        repo_root=repo_root,
    )
    under_tracked_ids = {
        row["platform_account_id"]: row
        for row in under_tracked
    }
    latest_by_platform = _latest_snapshot_by_platform(metrics)

    grouped_spines: list[dict] = []
    for spine in spines:
        spine_platforms: list[dict] = []
        for platform in platforms:
            if platform["spine_id"] != spine["spine_id"]:
                continue
            latest_snapshot = latest_by_platform.get(platform["platform_account_id"])
            under_tracked_record = under_tracked_ids.get(platform["platform_account_id"])
            spine_platforms.append(
                {
                    "platform_account_id": platform["platform_account_id"],
                    "platform": platform["platform"],
                    "account_label": platform["account_label"],
                    "content_lane": platform["content_lane"],
                    "active": platform["active"],
                    "latest_snapshot": latest_snapshot,
                    "under_tracked": under_tracked_record is not None,
                    "under_tracked_reason": (
                        under_tracked_record["reason"] if under_tracked_record else None
                    ),
                }
            )
        grouped_spines.append(
            {
                "spine_id": spine["spine_id"],
                "name": spine["name"],
                "description": spine["description"],
                "active": spine["active"],
                "platforms": spine_platforms,
            }
        )

    return {
        "schema_version": "1.0",
        "as_of": effective_as_of,
        "under_tracked_days": int(under_tracked_days),
        "spines": grouped_spines,
        "under_tracked_platforms": under_tracked,
    }


def find_under_tracked_platforms(
    *,
    days: int = 7,
    as_of: str | None = None,
    repo_root: Path | None = None,
) -> list[dict]:
    if int(days) < 0:
        raise ValueError("under_tracked_days_must_be_non_negative")
    spines = {row["spine_id"]: row for row in list_spines(repo_root=repo_root)}
    platforms = list_platform_accounts(repo_root=repo_root)
    metrics = list_metric_snapshots(repo_root=repo_root)
    latest_by_platform = _latest_snapshot_by_platform(metrics)
    cutoff = _parse_datetime(_canonical_as_of(as_of)) - timedelta(days=int(days))

    results: list[dict] = []
    for platform in platforms:
        spine = spines.get(platform["spine_id"])
        if spine is None:
            raise ValueError(f"unknown_spine_reference:{platform['spine_id']}")
        if not spine["active"] or not platform["active"]:
            continue
        latest = latest_by_platform.get(platform["platform_account_id"])
        if latest is None:
            results.append(_under_tracked_row(platform, spine, "missing_snapshot", None))
            continue
        latest_captured = _parse_datetime(latest["captured_at"])
        if latest_captured < cutoff:
            results.append(
                _under_tracked_row(
                    platform,
                    spine,
                    "stale_snapshot",
                    latest["captured_at"],
                )
            )
    return sorted(
        results,
        key=lambda row: (
            str(row["spine_name"]).lower(),
            str(row["platform"]),
            str(row["account_label"]).lower(),
            str(row["platform_account_id"]),
        ),
    )


def render_summary_text(summary: dict) -> str:
    lines = [
        f"Spine summary as of {summary['as_of']} (under-tracked window: {summary['under_tracked_days']} days)"
    ]
    for spine in summary["spines"]:
        lines.append(f"- {spine['name']} ({spine['spine_id']})")
        if not spine["platforms"]:
            lines.append("  platforms: none")
            continue
        for platform in spine["platforms"]:
            latest = platform["latest_snapshot"]
            latest_text = latest["captured_at"] if latest else "none"
            status = "under-tracked" if platform["under_tracked"] else "tracked"
            lines.append(
                "  - "
                f"{platform['platform']}:{platform['account_label']} "
                f"[{platform['content_lane']}] latest={latest_text} status={status}"
            )
    return "\n".join(lines) + "\n"


def render_under_tracked_text(report: dict) -> str:
    rows = report["under_tracked_platforms"]
    lines = [
        f"Under-tracked platforms as of {report['as_of']} (window: {report['days']} days)"
    ]
    if not rows:
        lines.append("none")
        return "\n".join(lines) + "\n"
    for row in rows:
        latest = row["latest_captured_at"] or "none"
        lines.append(
            "- "
            f"{row['spine_name']} / {row['platform']}:{row['account_label']} "
            f"reason={row['reason']} latest={latest}"
        )
    return "\n".join(lines) + "\n"


def build_under_tracked_report(
    *,
    days: int = 7,
    as_of: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    effective_as_of = _canonical_as_of(as_of)
    return {
        "schema_version": "1.0",
        "as_of": effective_as_of,
        "days": int(days),
        "under_tracked_platforms": find_under_tracked_platforms(
            days=days,
            as_of=effective_as_of,
            repo_root=repo_root,
        ),
    }


def _latest_snapshot_by_platform(metrics: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for snapshot in metrics:
        platform_account_id = snapshot["platform_account_id"]
        current = latest.get(platform_account_id)
        if current is None or _snapshot_sort_key(snapshot) > _snapshot_sort_key(current):
            latest[platform_account_id] = snapshot
    return latest


def _snapshot_sort_key(snapshot: dict) -> tuple[datetime, str]:
    return (_parse_datetime(snapshot["captured_at"]), str(snapshot["snapshot_id"]))


def _under_tracked_row(
    platform: dict,
    spine: dict,
    reason: str,
    latest_captured_at: str | None,
) -> dict:
    return {
        "spine_id": spine["spine_id"],
        "spine_name": spine["name"],
        "platform_account_id": platform["platform_account_id"],
        "platform": platform["platform"],
        "account_label": platform["account_label"],
        "content_lane": platform["content_lane"],
        "reason": reason,
        "latest_captured_at": latest_captured_at,
    }


def _canonical_as_of(as_of: str | None) -> str:
    value = as_of or utc_now_iso()
    parsed = _parse_datetime(value)
    return parsed.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("missing_datetime")
    candidate = raw
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        if len(candidate) == 10:
            parsed = datetime.fromisoformat(candidate).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"invalid_datetime:{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
