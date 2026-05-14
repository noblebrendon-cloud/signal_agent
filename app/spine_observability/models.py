from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.retention.identity import normalize_token, sha256_hex, utc_now_iso
from app.retention.jsonl_store import stable_json_dumps


SCHEMA_VERSION = "1.0"

ALLOWED_PLATFORMS = (
    "linkedin",
    "x",
    "substack",
    "youtube_ai",
    "youtube_reflection",
    "tiktok_conceptual",
    "tiktok_reflective",
    "facebook",
    "threads",
    "instagram",
)


def spine_id_from_name(name: str) -> str:
    normalized = _required_text("name", name).lower()
    return f"spn_{sha256_hex(normalized)[:16]}"


def platform_account_id_from_material(
    *,
    spine_id: str,
    platform: str,
    account_label: str,
    content_lane: str,
) -> str:
    parts = (
        _required_text("spine_id", spine_id),
        _normalize_allowed_platform(platform),
        _required_text("account_label", account_label).lower(),
        _required_text("content_lane", content_lane).lower(),
    )
    return f"spa_{sha256_hex('|'.join(parts))[:16]}"


def snapshot_id_from_material(
    *,
    platform_account_id: str,
    captured_at: str,
    metric_window_start: str,
    metric_window_end: str,
    metrics: Mapping[str, Any],
    notes: str,
) -> str:
    payload = {
        "captured_at": _required_text("captured_at", captured_at),
        "metric_window_end": _required_text("metric_window_end", metric_window_end),
        "metric_window_start": _required_text("metric_window_start", metric_window_start),
        "metrics": _normalize_metrics(metrics),
        "notes": _optional_text(notes),
        "platform_account_id": _required_text("platform_account_id", platform_account_id),
    }
    return f"sms_{sha256_hex(stable_json_dumps(payload))[:16]}"


def build_spine_record(
    *,
    name: str,
    description: str,
    created_at: str | None = None,
    active: bool = True,
) -> dict:
    if not isinstance(active, bool):
        raise ValueError("invalid_active")
    created_at_value = _required_text("created_at", created_at or utc_now_iso())
    _parse_datetime("created_at", created_at_value)
    record = {
        "record_type": "spine",
        "schema_version": SCHEMA_VERSION,
        "spine_id": spine_id_from_name(name),
        "name": _required_text("name", name),
        "description": _optional_text(description),
        "created_at": created_at_value,
        "active": active,
    }
    validate_spine_record(record)
    return record


def build_platform_account_record(
    *,
    spine_id: str,
    platform: str,
    account_label: str,
    content_lane: str,
    created_at: str | None = None,
    active: bool = True,
) -> dict:
    if not isinstance(active, bool):
        raise ValueError("invalid_active")
    created_at_value = _required_text("created_at", created_at or utc_now_iso())
    _parse_datetime("created_at", created_at_value)
    platform_value = _normalize_allowed_platform(platform)
    record = {
        "record_type": "platform_account",
        "schema_version": SCHEMA_VERSION,
        "platform_account_id": platform_account_id_from_material(
            spine_id=spine_id,
            platform=platform_value,
            account_label=account_label,
            content_lane=content_lane,
        ),
        "spine_id": _required_text("spine_id", spine_id),
        "platform": platform_value,
        "account_label": _required_text("account_label", account_label),
        "content_lane": _required_text("content_lane", content_lane).lower(),
        "created_at": created_at_value,
        "active": active,
    }
    validate_platform_account_record(record)
    return record


def build_metric_snapshot_record(
    *,
    platform_account_id: str,
    captured_at: str,
    metric_window_start: str,
    metric_window_end: str,
    metrics: Mapping[str, Any],
    notes: str = "",
    source_type: str = "manual",
    external_action_allowed: bool = False,
) -> dict:
    if source_type != "manual":
        raise ValueError("unsupported_source_type")
    if external_action_allowed is not False:
        raise ValueError("external_action_not_allowed")

    captured_at_value = _required_text("captured_at", captured_at)
    window_start_value = _required_text("metric_window_start", metric_window_start)
    window_end_value = _required_text("metric_window_end", metric_window_end)
    captured_dt = _parse_datetime("captured_at", captured_at_value)
    window_start_dt = _parse_datetime("metric_window_start", window_start_value)
    window_end_dt = _parse_datetime("metric_window_end", window_end_value)
    if window_start_dt > window_end_dt:
        raise ValueError("metric_window_start_after_end")

    metrics_value = _normalize_metrics(metrics)
    notes_value = _optional_text(notes)
    record = {
        "record_type": "metric_snapshot",
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id_from_material(
            platform_account_id=platform_account_id,
            captured_at=captured_at_value,
            metric_window_start=window_start_value,
            metric_window_end=window_end_value,
            metrics=metrics_value,
            notes=notes_value,
        ),
        "platform_account_id": _required_text("platform_account_id", platform_account_id),
        "captured_at": captured_at_value,
        "metric_window_start": window_start_value,
        "metric_window_end": window_end_value,
        "metrics": metrics_value,
        "notes": notes_value,
        "source_type": "manual",
        "external_action_allowed": False,
    }
    validate_metric_snapshot_record(record)
    _ = captured_dt
    return record


def validate_spine_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, "spine")
    _require_schema(record)
    required = ("spine_id", "name", "description", "created_at", "active")
    _require_keys(record, required)
    _required_text("spine_id", record["spine_id"])
    _required_text("name", record["name"])
    _optional_text(record["description"])
    _parse_datetime("created_at", str(record["created_at"]))
    if not isinstance(record["active"], bool):
        raise ValueError("invalid_active")


def validate_platform_account_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, "platform_account")
    _require_schema(record)
    required = (
        "platform_account_id",
        "spine_id",
        "platform",
        "account_label",
        "content_lane",
        "created_at",
        "active",
    )
    _require_keys(record, required)
    _required_text("platform_account_id", record["platform_account_id"])
    _required_text("spine_id", record["spine_id"])
    _normalize_allowed_platform(str(record["platform"]))
    _required_text("account_label", record["account_label"])
    _required_text("content_lane", record["content_lane"])
    _parse_datetime("created_at", str(record["created_at"]))
    if not isinstance(record["active"], bool):
        raise ValueError("invalid_active")


def validate_metric_snapshot_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, "metric_snapshot")
    _require_schema(record)
    required = (
        "snapshot_id",
        "platform_account_id",
        "captured_at",
        "metric_window_start",
        "metric_window_end",
        "metrics",
        "notes",
        "source_type",
        "external_action_allowed",
    )
    _require_keys(record, required)
    _required_text("snapshot_id", record["snapshot_id"])
    _required_text("platform_account_id", record["platform_account_id"])
    _parse_datetime("captured_at", str(record["captured_at"]))
    start = _parse_datetime("metric_window_start", str(record["metric_window_start"]))
    end = _parse_datetime("metric_window_end", str(record["metric_window_end"]))
    if start > end:
        raise ValueError("metric_window_start_after_end")
    _normalize_metrics(record["metrics"])
    _optional_text(record["notes"])
    if record["source_type"] != "manual":
        raise ValueError("unsupported_source_type")
    if record["external_action_allowed"] is not False:
        raise ValueError("external_action_not_allowed")


def _require_record_type(record: Mapping[str, Any], expected: str) -> None:
    if record.get("record_type") != expected:
        raise ValueError(f"invalid_record_type:{record.get('record_type')}")


def _require_schema(record: Mapping[str, Any]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid_schema_version:{record.get('schema_version')}")


def _require_keys(record: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")


def _required_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"missing_{field}")
    return normalized


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    return value.strip()


def _normalize_allowed_platform(value: str) -> str:
    normalized = normalize_token(_required_text("platform", value))
    if normalized not in ALLOWED_PLATFORMS:
        raise ValueError(f"unsupported_platform:{normalized}")
    return normalized


def _normalize_metrics(metrics: Mapping[str, Any]) -> dict[str, int | float]:
    if not isinstance(metrics, Mapping):
        raise ValueError("invalid_metrics")
    normalized: dict[str, int | float] = {}
    for raw_key, raw_value in metrics.items():
        key = normalize_token(_required_text("metric_key", raw_key))
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"invalid_metric_value:{key}")
        normalized[key] = raw_value
    if not normalized:
        raise ValueError("missing_metrics")
    return dict(sorted(normalized.items()))


def _parse_datetime(field: str, value: str) -> datetime:
    raw = _required_text(field, value)
    candidate = raw
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        if len(candidate) == 10:
            parsed = datetime.fromisoformat(candidate).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"invalid_datetime:{field}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
