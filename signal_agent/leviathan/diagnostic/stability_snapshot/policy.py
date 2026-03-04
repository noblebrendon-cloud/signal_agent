"""Policy gate helpers for Leviathan stability snapshot invariants."""
from __future__ import annotations

import datetime
import json
import pathlib
from typing import Any, Dict, Optional

_MODULE_DIR = pathlib.Path(__file__).resolve().parent
_INVARIANT_PATH = _MODULE_DIR / "invariant_v1.json"

with open(_INVARIANT_PATH, "r", encoding="utf-8") as f:
    _INVARIANT_DECLARATION = json.load(f)

BANDS = _INVARIANT_DECLARATION["bands"]
SCORE_MIN, SCORE_MAX = _INVARIANT_DECLARATION["inputs"]["score_range_inclusive"]
OVERRIDES = _INVARIANT_DECLARATION["overrides"]
OVERRIDE_ALLOWLIST = set(OVERRIDES.get("override_allowlist", []))
REQUIRED_OVERRIDE_FIELDS = set(OVERRIDES["required_ledger_fields"])
EXPIRY_MAX_HOURS = int(OVERRIDES["expiry_max_hours"])

BLOCKED_OPERATIONS: dict[str, set[str]] = {}
KNOWN_OPERATIONS: set[str] = set()
for band in BANDS:
    name = band["name"]
    blocked = set(band["blocked_operations"])
    BLOCKED_OPERATIONS[name] = blocked
    KNOWN_OPERATIONS.update(blocked)


def _parse_utc_iso(value: str) -> datetime.datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(datetime.timezone.utc)


def get_band_for_score(score: int) -> str:
    """Return the configured band for the score."""
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("Score must be an integer")
    if score < SCORE_MIN or score > SCORE_MAX:
        raise ValueError(f"Score must be between {SCORE_MIN} and {SCORE_MAX}")

    for band in BANDS:
        low, high = band["range_inclusive"]
        if low <= score <= high:
            return band["name"]

    raise ValueError("Score does not map to any configured band")


def is_override_valid(
    override_metadata: Optional[Dict[str, Any]],
    current_utc: datetime.datetime,
    *,
    band: str | None = None,
    score: int | None = None,
    operation: str | None = None,
) -> bool:
    """Validate break-glass override metadata deterministically."""
    if not OVERRIDES.get("enabled", False):
        return False
    if not override_metadata:
        return False

    if current_utc.tzinfo is None:
        return False
    now_utc = current_utc.astimezone(datetime.timezone.utc)

    if not REQUIRED_OVERRIDE_FIELDS.issubset(override_metadata.keys()):
        return False

    try:
        issued_utc = _parse_utc_iso(str(override_metadata["utc_timestamp"]))
        expiry_utc = _parse_utc_iso(str(override_metadata["expiry_utc"]))
    except (ValueError, TypeError):
        return False

    if expiry_utc <= now_utc:
        return False
    if expiry_utc <= issued_utc:
        return False

    max_duration = datetime.timedelta(hours=EXPIRY_MAX_HOURS)
    if (expiry_utc - issued_utc) > max_duration:
        return False

    if band is not None:
        if band not in {"ORANGE", "RED"}:
            return False
        if override_metadata.get("band") != band:
            return False

    if score is not None:
        payload_score = override_metadata.get("score")
        if isinstance(payload_score, bool) or not isinstance(payload_score, int):
            return False
        if payload_score != score:
            return False

    if operation is not None:
        if operation not in OVERRIDE_ALLOWLIST:
            return False
        if override_metadata.get("operation") != operation:
            return False

    return True


def evaluate_operation(
    score: int,
    operation: str,
    override: Optional[Dict[str, Any]] = None,
    current_utc: Optional[datetime.datetime] = None,
) -> bool:
    """Return allow=True|False for operation under the configured invariant."""
    if not isinstance(operation, str) or not operation.strip():
        return False

    band = get_band_for_score(score)
    blocked_set = BLOCKED_OPERATIONS.get(band, set())

    if operation not in KNOWN_OPERATIONS:
        if band in {"ORANGE", "RED"}:
            return False
        return True

    if operation not in blocked_set:
        return True

    if override is not None and current_utc is not None:
        return is_override_valid(
            override,
            current_utc,
            band=band,
            score=score,
            operation=operation,
        )

    return False
