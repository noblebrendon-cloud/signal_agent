"""
OIL Memory -- Append-Only Incident Store (v0.5)

v0.5 adds action fields to each JSONL line:
  action_category:       rollback | restart | scale | failover | hotfix |
                         vendor_escalation | investigate | unknown
  action_target_service: service the recommended action targets

JSONL line schema:
{
  "run_id":                "sha256[:16]",
  "fingerprint_id":        "sha256[:16]",
  "artifact_path":         "...absolute...",
  "created_utc":           "YYYY-MM-DDTHH:MM:SSZ",
  "origin_service":        "payment",
  "change_kind":           "deploy",
  "metric_kind":           "latency",
  "hop_distance_class":    "1",
  "impact_domain":         "transactions",
  "confidence":            0.98,
  "action_category":       "rollback",
  "action_target_service": "payment",
  "fallback_action_category": "investigate"
}

Similarity scoring:
  +2 same origin_service
  +2 same change_kind (non-empty)
  +1 same metric_kind (non-empty)
  +1 same hop_distance_class
  +1 same impact_domain (non-empty)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DEFAULT_INDEX = Path(__file__).resolve().parent / "index.jsonl"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_entry(
    fingerprint_id: str,
    artifact_path: str,
    origin_service: str,
    change_kind: str,
    metric_kind: str,
    hop_distance_class: str,
    impact_domain: str,
    confidence: float,
    index_path: Path | None = None,
    run_id: str = "",
    action_category: str = "",
    action_target_service: str = "",
    fallback_action_category: str = "",
) -> None:
    """Atomically append one entry to the JSONL index.

    v0.8: record_type="memory_index" and record_version="1" added for schema versioning.
    v0.6: fallback_action_category added (compound action support).
    v0.5: action_category and action_target_service added.
    v0.4.1: run_id for stable identity.
    Uses os.O_APPEND for atomic append; creates file if missing.
    """
    path = index_path or _DEFAULT_INDEX
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "record_type":              "memory_index",
        "record_version":           "1",
        "run_id":                   run_id,
        "fingerprint_id":           fingerprint_id,
        "artifact_path":            artifact_path,
        "created_utc":              _utc_iso(),
        "origin_service":           origin_service,
        "change_kind":              change_kind,
        "metric_kind":              metric_kind,
        "hop_distance_class":       hop_distance_class,
        "impact_domain":            impact_domain,
        "confidence":               confidence,
        "action_category":          action_category,
        "action_target_service":    action_target_service,
        "fallback_action_category": fallback_action_category,
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def load_index(index_path: Path | None = None) -> list[dict]:
    """Load entries from the JSONL index, deduping by run_id (keep first).

    v0.4.1: run_id deduplication eliminates double-append from a single
    CLI invocation. Entries without run_id are kept as-is (backward compat).
    Returns empty list if file does not exist. Skips malformed lines silently.
    """
    path = index_path or _DEFAULT_INDEX
    if not path.exists():
        return []

    entries: list[dict] = []
    seen_run_ids: set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        run_id = entry.get("run_id", "")
        if run_id:
            if run_id in seen_run_ids:
                continue          # duplicate: same CLI invocation written twice
            seen_run_ids.add(run_id)
        entries.append(entry)

    return entries


def _similarity_score(query: dict, candidate: dict) -> int:
    score = 0
    if candidate.get("origin_service") == query.get("origin_service"):
        score += 2
    q_ck = query.get("change_kind", "")
    c_ck = candidate.get("change_kind", "")
    if q_ck and c_ck and q_ck == c_ck:
        score += 2
    q_mk = query.get("metric_kind", "")
    c_mk = candidate.get("metric_kind", "")
    if q_mk and c_mk and q_mk == c_mk:
        score += 1
    if candidate.get("hop_distance_class") == query.get("hop_distance_class"):
        score += 1
    q_id = query.get("impact_domain", "")
    c_id = candidate.get("impact_domain", "")
    if q_id and c_id and q_id == c_id:
        score += 1
    return score


def find_similar(
    fingerprint_id: str,
    index: list[dict],
    top_n: int = 5,
    current_run_id: str = "",
    min_score: int = 5,
    lookback_days: int = 30,
    max_recent_lines: int = 5000,
) -> list[dict]:
    """Find top_n most similar past incidents.

    v0.4.1:
      - Self-excluded by run_id (not fingerprint+path).
      - Only scans the last max_recent_lines entries (scale guard).
      - Filters out entries older than lookback_days.
      - Only returns results with score >= min_score.
      - Dedupes results by run_id before returning.

    Sorted: similarity_score desc, then created_utc desc (deterministic tie-break).
    """
    # Scale guard: only look at most recent max_recent_lines
    window = index[-max_recent_lines:]

    # Lookback filter
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    window = [e for e in window if e.get("created_utc", "") >= cutoff]

    # Find the query vector (most recent entry with matching fingerprint_id)
    query_entries = [e for e in window if e.get("fingerprint_id") == fingerprint_id]
    if not query_entries:
        return []
    query = sorted(query_entries, key=lambda e: e.get("created_utc", ""), reverse=True)[0]

    # Score candidates
    seen_run_ids: set[str] = set()
    results: list[dict] = []

    for entry in window:
        # Self-exclusion by run_id
        entry_run_id = entry.get("run_id", "")
        if current_run_id and entry_run_id and entry_run_id == current_run_id:
            continue
        # Dedupe by run_id
        if entry_run_id:
            if entry_run_id in seen_run_ids:
                continue
            seen_run_ids.add(entry_run_id)

        score = _similarity_score(query, entry)
        if score >= min_score:
            results.append({**entry, "similarity_score": score})

    results.sort(key=lambda e: (-e["similarity_score"], e.get("created_utc", "")[::-1]))
    return results[:top_n]
