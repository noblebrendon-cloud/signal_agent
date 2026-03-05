"""
OIL Intake — Event Normalizer

Rules:
- event_id, timestamp, service are REQUIRED → raises ValueError if absent.
- timestamp is parsed to UTC timezone-aware datetime (naive → assume UTC).
- delta: None or missing → 0.0 (guaranteed float on output).
- All other fields fill safe defaults.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from oil.models.schemas import Event


_REQUIRED = ("event_id", "timestamp", "service")

_AWARE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
]
_NAIVE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
]


def _parse_timestamp(raw: Any) -> datetime:
    """Parse *raw* to a timezone-aware UTC datetime.

    Accepts:
    - datetime objects (naive → coerce to UTC, aware → convert to UTC)
    - ISO-8601 strings with or without timezone offset
    Raises ValueError on unparseable input.
    """
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)

    if not isinstance(raw, str):
        raise ValueError(f"timestamp must be str or datetime, got {type(raw).__name__!r}")

    # Try timezone-aware formats first
    for fmt in _AWARE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).astimezone(timezone.utc)
        except ValueError:
            continue

    # Try naive formats, treat as UTC
    for fmt in _NAIVE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Last resort: fromisoformat (Python 3.11+ handles offsets; 3.7+ handles naive)
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise ValueError(f"Cannot parse timestamp: {raw!r}")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _infer_metric_kind(metric_name: str) -> str:
    """Infer metric_kind from metric_name via simple string rules.

    Returns one of: "latency", "error_rate", "saturation", "business_kpi", "".
    Case-insensitive. First match wins.
    """
    name = metric_name.lower()
    if any(k in name for k in ("latency", "p99", "p95", "p50", "response_time")):
        return "latency"
    if any(k in name for k in ("error", "5xx", "4xx", "fault", "exception")):
        return "error_rate"
    if any(k in name for k in ("cpu", "mem", "memory", "utilization", "saturation", "queue")):
        return "saturation"
    if any(k in name for k in ("revenue", "conversion", "checkout", "order", "sale")):
        return "business_kpi"
    return ""


def normalize_event(raw: dict[str, Any]) -> Event:
    """Normalize a raw telemetry dict into an Event.

    Required fields: event_id, timestamp, service.
    Missing required field → ValueError.
    Missing optional fields → safe defaults.
    delta=None → 0.0.
    metric_kind inferred from metric_name if not provided.
    change events: event_type="change", change_kind, change_id pass through directly.
    """
    for field in _REQUIRED:
        if not raw.get(field):
            raise ValueError(f"Missing required field: {field!r}")

    metric_name = str(raw.get("metric_name") or "")
    metric_kind = str(raw.get("metric_kind") or "") or _infer_metric_kind(metric_name)

    return Event(
        event_id=str(raw["event_id"]),
        timestamp=_parse_timestamp(raw["timestamp"]),
        service=str(raw["service"]),
        metric_name=metric_name,
        metric_value=_safe_float(raw.get("metric_value"), 0.0),
        delta=_safe_float(raw.get("delta"), 0.0),
        event_type=str(raw.get("event_type") or ""),
        source=str(raw.get("source") or ""),
        related_deployment=str(raw.get("related_deployment") or ""),
        business_tag=str(raw.get("business_tag") or ""),
        metric_kind=metric_kind,
        change_kind=str(raw.get("change_kind") or ""),
        change_id=str(raw.get("change_id") or ""),
    )


def normalize_events(raw_list: list[dict[str, Any]]) -> list[Event]:
    """Normalize a list of raw dicts. Raises on first invalid required-field."""
    return [normalize_event(r) for r in raw_list]

