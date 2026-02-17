"""
Decay Policy — auto-expire raw capture files after N days.

Moves expired files to data/capture/expired_stage1/ (Stage 1).
Moves stage1 files to data/capture/expired_stage2/ (Stage 2) after purge_days.
Never deletes.
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
    purge_days: int = 30,
    max_files: int = 2000,
    dry_run: bool = False,
    capture_dir: Optional[Path] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Two-stage decay policy.
    Stage 1: raw -> expired_stage1 (older than days)
    Stage 2: expired_stage1 -> expired_stage2 (older than purge_days)
    """
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    stage1_dir = base / "expired_stage1"
    stage2_dir = base / "expired_stage2"
    
    # Auto-migrate legacy 'expired' if it exists and stage1 doesn't
    legacy_expired = base / "expired"
    if legacy_expired.exists() and not stage1_dir.exists() and not dry_run:
        try:
            legacy_expired.rename(stage1_dir)
        except OSError:
            pass
            
    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)

    now = now_utc or datetime.now(timezone.utc)
    cutoff_stage1 = now - timedelta(days=days)
    cutoff_stage2 = now - timedelta(days=purge_days)

    # Load exempt files (only relevant for raw -> stage1)
    promoted = _load_promoted_files(base)
    archived = _load_archived_files(base)
    exempt = promoted | archived

    stage1_moved: List[str] = []
    stage2_moved: List[str] = []

    # ---------------------------------------------------------
    # Stage 1: raw -> expired_stage1
    # ---------------------------------------------------------
    if raw_dir.exists():
        raw_files = sorted(raw_dir.glob("raw_*.md"))[:max_files]
        for rf in raw_files:
            if rf.name in exempt:
                continue

            ts = _parse_file_timestamp(rf.name)
            is_expired = False
            
            if ts:
                if ts < cutoff_stage1:
                    is_expired = True
            else:
                # Fallback to mtime
                try:
                    mtime = datetime.fromtimestamp(rf.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff_stage1:
                        is_expired = True
                except OSError:
                    pass

            if is_expired:
                stage1_moved.append(rf.name)
                if not dry_run:
                    dest = stage1_dir / rf.name
                    if not dest.exists():
                        try:
                            shutil.move(str(rf), str(dest))
                        except OSError:
                            pass

    # ---------------------------------------------------------
    # Stage 2: expired_stage1 -> expired_stage2
    # ---------------------------------------------------------
    # Scan stage1 files
    stage1_files = sorted(stage1_dir.glob("raw_*.md"))[:max_files]
    for sf in stage1_files:
        ts = _parse_file_timestamp(sf.name)
        is_purged = False
        
        if ts:
            if ts < cutoff_stage2:
                is_purged = True
        else:
            try:
                mtime = datetime.fromtimestamp(sf.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff_stage2:
                    is_purged = True
            except OSError:
                pass

        if is_purged:
            stage2_moved.append(sf.name)
            if not dry_run:
                dest = stage2_dir / sf.name
                if not dest.exists():
                    try:
                        shutil.move(str(sf), str(dest))
                    except OSError:
                        pass

    # Log
    log_entry = {
        "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days,
        "purge_days": purge_days,
        "stage1_moved": stage1_moved,
        "stage2_moved": stage2_moved,
        "status": "dry_run" if dry_run else "ok",
        "error": None,
    }
    _append_decay_log(base, log_entry)

    return {
        "status": "dry_run" if dry_run else "ok",
        "days": days,
        "purge_days": purge_days,
        "stage1_count": len(stage1_moved),
        "stage2_count": len(stage2_moved),
        "stage1_moved": stage1_moved,
        "stage2_moved": stage2_moved,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    """CLI entrypoint for decay subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture.decay",
        description="Expire raw capture files (2-stage).",
    )
    parser.add_argument("--days", type=int, default=14, help="Stage 1 age threshold")
    parser.add_argument("--purge-days", type=int, default=30, help="Stage 2 age threshold")
    parser.add_argument("--max-files", type=int, default=2000, help="Max files to scan")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")

    args = parser.parse_args(argv)
    result = decay_run(
        days=args.days, 
        purge_days=args.purge_days, 
        max_files=args.max_files, 
        dry_run=args.dry_run
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
