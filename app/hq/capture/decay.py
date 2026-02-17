"""
Decay Policy — auto-expire raw capture files after N days.

Moves expired files to data/capture/expired/ (never deletes).
Logs events to decay_log.jsonl.
NEVER touches artifact_registry.jsonl.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _get_capture_dir() -> Path:
    override = os.environ.get("CAPTURE_DIR")
    if override:
        return Path(override)
    return _get_root() / "data" / "capture"


def _load_promoted_files(capture_dir: Path) -> Set[str]:
    """Load set of filenames already promoted (from promotion_log.jsonl)."""
    promoted: Set[str] = set()
    log_path = capture_dir / "promotion_log.jsonl"
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                for f in entry.get("raw_files", []):
                    promoted.add(f)
        except (json.JSONDecodeError, OSError):
            pass
    return promoted


def _load_archived_files(capture_dir: Path) -> Set[str]:
    """Load set of filenames already archived."""
    archive_dir = capture_dir / "archive"
    if archive_dir.exists():
        return {f.name for f in archive_dir.glob("raw_*.md")}
    return set()


def _parse_file_timestamp(filename: str) -> Optional[datetime]:
    """Extract UTC timestamp from raw_YYYY-MM-DDTHH-MM-SS_mmmZ.md filename."""
    # raw_2026-02-16T18-00-01_001Z.md
    try:
        stem = filename.replace("raw_", "").replace(".md", "")
        # Remove milliseconds suffix: _001Z
        if stem.endswith("Z"):
            stem = stem[:-1]  # drop Z
        parts = stem.rsplit("_", 1)
        ts_part = parts[0]  # 2026-02-16T18-00-01
        # Convert back to ISO
        iso = ts_part.replace("T", "T").replace("-", "-")
        # The time part uses - instead of :
        # Format: YYYY-MM-DDTHH-MM-SS
        date_part = iso[:10]  # YYYY-MM-DD
        time_part = iso[11:]  # HH-MM-SS
        time_iso = time_part.replace("-", ":")
        full = f"{date_part}T{time_iso}+00:00"
        return datetime.fromisoformat(full)
    except (ValueError, IndexError):
        return None


def _append_decay_log(
    capture_dir: Path,
    entry: Dict[str, Any],
) -> None:
    """Append to decay_log.jsonl."""
    log_path = capture_dir / "decay_log.jsonl"
    line = json.dumps(entry, sort_keys=True) + "\n"
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def decay_run(
    days: int = 14,
    max_files: int = 2000,
    dry_run: bool = False,
    capture_dir: Optional[Path] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Expire raw capture files older than N days.

    Files that have been promoted or archived are exempt.
    Moves expired files to data/capture/expired/.
    """
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    expired_dir = base / "expired"
    expired_dir.mkdir(parents=True, exist_ok=True)

    if not raw_dir.exists():
        return {"status": "no_raw_dir", "expired_files": [], "days": days}

    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Load exempt files
    promoted = _load_promoted_files(base)
    archived = _load_archived_files(base)
    exempt = promoted | archived

    # Scan raw files (sorted for determinism)
    raw_files = sorted(raw_dir.glob("raw_*.md"))[:max_files]
    expired_files: List[str] = []

    for rf in raw_files:
        if rf.name in exempt:
            continue

        ts = _parse_file_timestamp(rf.name)
        if ts is None:
            # Can't parse timestamp — check file mtime as fallback
            try:
                mtime = datetime.fromtimestamp(rf.stat().st_mtime, tz=timezone.utc)
                if mtime >= cutoff:
                    continue
            except OSError:
                continue
        elif ts >= cutoff:
            continue

        expired_files.append(rf.name)

        if not dry_run:
            dest = expired_dir / rf.name
            if not dest.exists():
                try:
                    shutil.move(str(rf), str(dest))
                except OSError:
                    pass

    # Log
    log_entry = {
        "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days,
        "expired_files": expired_files,
        "status": "dry_run" if dry_run else "ok",
        "error": None,
    }
    _append_decay_log(base, log_entry)

    return {
        "status": "dry_run" if dry_run else "ok",
        "expired_files": expired_files,
        "days": days,
        "count": len(expired_files),
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    """CLI entrypoint for decay subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture.decay",
        description="Expire raw capture files older than N days.",
    )
    parser.add_argument("--days", type=int, default=14, help="Age threshold in days")
    parser.add_argument("--max-files", type=int, default=2000, help="Max files to scan")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")

    args = parser.parse_args(argv)
    result = decay_run(days=args.days, max_files=args.max_files, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
