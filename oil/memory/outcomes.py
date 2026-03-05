"""
OIL Memory -- Append-Only Outcome Store (v0.7)

v0.7 additions:
  select_final_outcome(outcome_entries) -> outcome_entry
  Deterministic final-outcome policy: latest created_utc wins; ties broken
  by priority: resolved > mitigated > false_positive > ignored.

  load_outcomes() gains bounded scanning:
    lookback_days=30, max_recent_lines=5000
  Skips old entries and deduplicates exact duplicates (run_id+created_utc+kind).

outcome_entry:
{
  "run_id":       "...",
  "outcome_kind": "resolved|mitigated|false_positive|ignored",
  "created_utc":  "YYYY-MM-DDTHH:MM:SSZ",
  "notes":        ""
}

load_outcomes() returns dict[run_id, list[outcome_entry]] for join with index.
"""
from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

_VALID_KINDS = frozenset(["resolved", "mitigated", "false_positive", "ignored"])
_DEFAULT_OUTCOMES = Path(__file__).resolve().parent / "outcomes.jsonl"

# priority for tie-breaking (lower index = higher priority)
_KIND_PRIORITY: dict[str, int] = {
    "resolved":       0,
    "mitigated":      1,
    "false_positive": 2,
    "ignored":        3,
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(ts: str) -> datetime:
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' to timezone-aware UTC datetime."""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def select_final_outcome(outcome_entries: list[dict]) -> dict | None:
    """Return the single deterministic final outcome from a list.

    Rule:
      1. Choose entry with the latest created_utc.
      2. Tie-break by priority: resolved > mitigated > false_positive > ignored.

    Returns None if outcome_entries is empty.
    """
    if not outcome_entries:
        return None

    def _key(e: dict) -> tuple:
        ts = _parse_utc(e.get("created_utc", ""))
        priority = _KIND_PRIORITY.get(e.get("outcome_kind", ""), 99)
        return (ts, -priority)   # latest ts wins; lowest priority number wins on tie

    return max(outcome_entries, key=_key)


def append_outcome(
    run_id: str,
    outcome_kind: str,
    created_utc: str = "",
    notes: str = "",
    outcomes_path: Path | None = None,
) -> None:
    """Atomically append one outcome entry to the outcomes JSONL file.

    outcome_kind must be one of: resolved, mitigated, false_positive, ignored.
    created_utc defaults to current UTC if not supplied.
    Raises ValueError for invalid outcome_kind.
    """
    if outcome_kind not in _VALID_KINDS:
        raise ValueError(
            f"Invalid outcome_kind {outcome_kind!r}. "
            f"Must be one of: {sorted(_VALID_KINDS)}"
        )
    path = outcomes_path or _DEFAULT_OUTCOMES
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "record_type":  "outcome",
        "record_version": "1",
        "run_id":       run_id,
        "outcome_kind": outcome_kind,
        "created_utc":  created_utc or _utc_iso(),
        "notes":        notes,
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def load_outcomes(
    outcomes_path: Path | None = None,
    lookback_days: int = 30,
    max_recent_lines: int = 5000,
) -> dict[str, list[dict]]:
    """Load outcome entries keyed by run_id with bounded scanning (v0.7).

    - Scans only last max_recent_lines of the file.
    - Filters entries older than lookback_days.
    - Deduplicates by (run_id, created_utc, outcome_kind).
    - Returns {} if the file does not exist.
    """
    path = outcomes_path or _DEFAULT_OUTCOMES
    if not path.exists():
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    seen_keys: set[tuple[str, str, str]] = set()
    result: dict[str, list[dict]] = {}

    all_lines = path.read_text(encoding="utf-8").splitlines()
    recent_lines = list(deque(all_lines, maxlen=max_recent_lines))

    for line in recent_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        rid = entry.get("run_id", "")
        kind = entry.get("outcome_kind", "")
        ts_str = entry.get("created_utc", "")
        if not rid:
            continue

        # Lookback filter
        ts = _parse_utc(ts_str)
        if ts < cutoff:
            continue

        # Exact duplicate dedup
        dedup_key = (rid, ts_str, kind)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        result.setdefault(rid, []).append(entry)

    return result
