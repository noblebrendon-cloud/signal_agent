"""
OIL -- Memory Rotation CLI (v0.8)

Rotates append-only memory and outcome logs into monthly YYYYMM shards.

Usage:
  python -m oil.run_rotate_memory [--keep-months 6] [--prune-original]
  python -m oil.run_rotate_memory --index-path <path> --outcomes-path <path>

Behavior:
- Reads index.jsonl and outcomes.jsonl (if present).
- Routes each line to index_YYYYMM.jsonl / outcomes_YYYYMM.jsonl
  based on created_utc (YYYY-MM or YYYYMM prefix used for shard name).
- Shard files are append-only; each line deduped before appending:
    memory_index:  dedup by run_id
    outcomes:      dedup by (run_id, created_utc, outcome_kind)
- Original files remain unchanged UNLESS --prune-original is set.
- --keep-months N labels shards as hot (last N months from now) in report.
- Prints a deterministic rotation report (JSON to stdout).

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent
_MEMORY_DIR = _OIL_ROOT / "memory"
_DEFAULT_INDEX = _MEMORY_DIR / "index.jsonl"
_DEFAULT_OUTCOMES = _MEMORY_DIR / "outcomes.jsonl"


def _parse_yyyymm(ts: str) -> str:
    """Extract YYYYMM shard key from a created_utc or similar timestamp string.
    Falls back to 000000 for unparseable values (shard still written, just labeled)."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y%m%dT%H%M%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts[:len(fmt.replace("%", "XX"))], fmt)
            return dt.strftime("%Y%m")
        except (ValueError, TypeError):
            pass
    # try bare YYYY-MM prefix
    if len(ts) >= 7 and ts[4] == "-":
        yyyymm = ts[:7].replace("-", "")
        if yyyymm.isdigit():
            return yyyymm
    return "000000"


def _hot_months(keep_months: int) -> set[str]:
    """Return the set of YYYYMM strings for the last keep_months from now."""
    now = datetime.now(timezone.utc)
    result = set()
    for i in range(keep_months):
        month = (now.month - i - 1) % 12 + 1
        year = now.year - ((i + 1 - now.month) // 12 + (1 if (now.month - i - 1) < 0 else 0))
        # simpler: subtract i months
        d = now.replace(day=1) - timedelta(days=i * 28 + 1)
        result.add(d.strftime("%Y%m"))
    # always include current month
    result.add(now.strftime("%Y%m"))
    return result


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return lines


def _load_shard_seen_run_ids(shard_path: Path) -> set[str]:
    seen = set()
    for entry in _read_jsonl(shard_path):
        rid = entry.get("run_id", "")
        if rid:
            seen.add(rid)
    return seen


def _load_shard_seen_outcome_keys(shard_path: Path) -> set[tuple[str, str, str]]:
    seen = set()
    for entry in _read_jsonl(shard_path):
        key = (entry.get("run_id", ""), entry.get("created_utc", ""),
               entry.get("outcome_kind", ""))
        seen.add(key)
    return seen


def _atomic_append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def rotate(
    index_path: Path,
    outcomes_path: Path,
    memory_dir: Path,
    keep_months: int = 6,
    prune_original: bool = False,
) -> dict:
    """Rotate index and outcomes into monthly shards. Returns rotation report."""
    hot = _hot_months(keep_months)

    # ── Memory index rotation ─────────────────────────────────────────────
    index_entries = _read_jsonl(index_path)
    index_shard_counts: dict[str, int] = {}
    index_skipped = 0
    # Preload existing shard seen sets lazily
    index_shard_seen: dict[str, set] = {}

    for entry in index_entries:
        ts = entry.get("created_utc", "")
        shard_key = _parse_yyyymm(ts)
        shard_path = memory_dir / f"index_{shard_key}.jsonl"

        if shard_key not in index_shard_seen:
            index_shard_seen[shard_key] = _load_shard_seen_run_ids(shard_path)

        rid = entry.get("run_id", "")
        if rid and rid in index_shard_seen[shard_key]:
            index_skipped += 1
            continue

        _atomic_append(shard_path, json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        index_shard_counts[shard_key] = index_shard_counts.get(shard_key, 0) + 1
        if rid:
            index_shard_seen[shard_key].add(rid)

    # ── Outcomes rotation ─────────────────────────────────────────────────
    outcome_entries = _read_jsonl(outcomes_path)
    outcome_shard_counts: dict[str, int] = {}
    outcome_skipped = 0
    outcome_shard_seen: dict[str, set] = {}

    for entry in outcome_entries:
        ts = entry.get("created_utc", "")
        shard_key = _parse_yyyymm(ts)
        shard_path = memory_dir / f"outcomes_{shard_key}.jsonl"

        if shard_key not in outcome_shard_seen:
            outcome_shard_seen[shard_key] = _load_shard_seen_outcome_keys(shard_path)

        key = (entry.get("run_id", ""), entry.get("created_utc", ""),
               entry.get("outcome_kind", ""))
        if key in outcome_shard_seen[shard_key]:
            outcome_skipped += 1
            continue

        _atomic_append(shard_path, json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        outcome_shard_counts[shard_key] = outcome_shard_counts.get(shard_key, 0) + 1
        outcome_shard_seen[shard_key].add(key)

    # ── Prune originals (optional) ────────────────────────────────────────
    pruned = []
    if prune_original:
        for p in [index_path, outcomes_path]:
            if p.exists():
                p.unlink()
                pruned.append(str(p))

    # ── Report ────────────────────────────────────────────────────────────
    all_shards = sorted(set(list(index_shard_counts) + list(outcome_shard_counts)))
    shards_report = [
        {
            "yyyymm": s,
            "hot": s in hot,
            "index_written": index_shard_counts.get(s, 0),
            "outcomes_written": outcome_shard_counts.get(s, 0),
        }
        for s in all_shards
    ]
    return {
        "total_index_rotated":    sum(index_shard_counts.values()),
        "total_outcomes_rotated": sum(outcome_shard_counts.values()),
        "index_skipped":          index_skipped,
        "outcome_skipped":        outcome_skipped,
        "keep_months":            keep_months,
        "shards":                 shards_report,
        "pruned_originals":       pruned,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oil.run_rotate_memory",
        description="OIL -- rotate memory/outcome logs into monthly shards",
    )
    parser.add_argument("--keep-months",     type=int,  default=6)
    parser.add_argument("--prune-original",  action="store_true", default=False)
    parser.add_argument("--index-path",      default=str(_DEFAULT_INDEX))
    parser.add_argument("--outcomes-path",   default=str(_DEFAULT_OUTCOMES))
    parser.add_argument("--memory-dir",      default=str(_MEMORY_DIR))
    args = parser.parse_args(argv)

    try:
        report = rotate(
            index_path=Path(args.index_path),
            outcomes_path=Path(args.outcomes_path),
            memory_dir=Path(args.memory_dir),
            keep_months=args.keep_months,
            prune_original=args.prune_original,
        )
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
