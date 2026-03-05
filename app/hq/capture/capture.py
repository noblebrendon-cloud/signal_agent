"""
Volatile Capture Layer — fast, friction-free fragment intake.

Stores raw notes into data/capture/raw/ with JSONL telemetry.
NEVER touches artifact_registry.jsonl.
NO hashing, NO policy checks, NO constraint checks.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _get_root() -> Path:
    """Resolve repo root, supporting SIGNAL_AGENT_ROOT env override."""
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _get_capture_dir() -> Path:
    """Resolve capture base directory."""
    override = os.environ.get("CAPTURE_DIR")
    if override:
        return Path(override)
    return _get_root() / "data" / "capture"


def _safe_timestamp() -> str:
    """Windows-safe UTC timestamp: raw_YYYY-MM-DDTHH-MM-SS_mmmZ"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H-%M-%S") + f"_{now.microsecond // 1000:03d}Z"


def _build_frontmatter(
    input_type: str,
    source: Optional[str],
    timestamp_utc: str,
) -> str:
    """Build YAML frontmatter block."""
    src = source or "null"
    return (
        "---\n"
        f"timestamp_utc: {timestamp_utc}\n"
        f"input_type: {input_type}\n"
        f"source: {src}\n"
        "---\n"
    )


def _append_telemetry(
    capture_dir: Path,
    filename: str,
    input_type: str,
    source: Optional[str],
    content_length: int,
    timestamp_utc: str,
) -> None:
    """Append a JSONL telemetry record (best-effort atomic append)."""
    log_path = capture_dir / "capture_log.jsonl"
    record = {
        "timestamp_utc": timestamp_utc,
        "filename": filename,
        "input_type": input_type,
        "source": source,
        "length": content_length,
    }
    line = json.dumps(record, sort_keys=True) + "\n"
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def capture_add(
    text: Optional[str] = None,
    url: Optional[str] = None,
    file_path: Optional[str] = None,
    from_stdin: bool = False,
    capture_dir: Optional[Path] = None,
) -> dict:
    """
    Capture a raw fragment into data/capture/raw/.

    Returns dict with filename and path.
    """
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_safe = _safe_timestamp()

    # Determine input type and content
    if text is not None:
        input_type = "text"
        source = None
        content = text
    elif url is not None:
        input_type = "url"
        source = url
        # No network fetch — just record the URL as content
        content = url
    elif file_path is not None:
        input_type = "file"
        source = file_path
        fp = Path(file_path)
        if fp.exists():
            content = fp.read_text(encoding="utf-8", errors="replace")
        else:
            content = f"[file not found: {file_path}]"
    elif from_stdin:
        input_type = "stdin"
        source = None
        content = sys.stdin.read()
    else:
        input_type = "text"
        source = None
        content = "[empty capture — no input provided]"

    # Guard against empty content
    if not content or not content.strip():
        content = "[empty capture — blank input]"

    # Build file
    filename = f"raw_{ts_safe}.md"
    frontmatter = _build_frontmatter(input_type, source, now_utc)
    full_content = frontmatter + "\n" + content.rstrip() + "\n"

    out_path = raw_dir / filename
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(full_content)

    # Telemetry
    _append_telemetry(
        base, filename, input_type, source, len(content), now_utc
    )

    return {"filename": filename, "path": str(out_path)}


def capture_status(capture_dir: Optional[Path] = None) -> dict:
    """Return status dict with counts and last timestamps."""
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    promoted_dir = base / "promoted"
    archive_dir = base / "archive"

    raw_count = len(list(raw_dir.glob("raw_*.md"))) if raw_dir.exists() else 0
    promoted_count = len(list(promoted_dir.glob("bundle_*.md"))) if promoted_dir.exists() else 0
    archived_count = len(list(archive_dir.glob("raw_*.md"))) if archive_dir.exists() else 0
    expired_stage1_dir = base / "expired_stage1"
    expired_stage1_count = len(list(expired_stage1_dir.glob("raw_*.md"))) if expired_stage1_dir.exists() else 0
    
    expired_stage2_dir = base / "expired_stage2"
    expired_stage2_count = len(list(expired_stage2_dir.glob("raw_*.md"))) if expired_stage2_dir.exists() else 0
    
    # Fallback for legacy 'expired' dir
    if base.joinpath("expired").exists():
        expired_stage1_count += len(list(base.joinpath("expired").glob("raw_*.md")))

    # Raw file ages
    raw_oldest_age_days = None
    raw_newest_age_minutes = None
    raw_files = sorted(raw_dir.glob("raw_*.md")) if raw_dir.exists() else []
    
    if raw_files:
        now = datetime.now(timezone.utc)
        
        def parse_ts(name):
             # raw_2026-02-16T18-00-01_001Z.md
             try:
                 stem = name.replace("raw_", "").replace(".md", "")
                 if stem.endswith("Z"): stem = stem[:-1]
                 parts = stem.rsplit("_", 1)
                 iso = parts[0].replace("-", ":").replace("T", " ") # close enough for sorting? 
                 # Actually strictly:
                 # 2026-02-16T18-00-01
                 iso_clean = parts[0].replace("T", "T")
                 # YYYY-MM-DDTHH-MM-SS
                 # Reconstruct to YYYY-MM-DDTHH:MM:SS
                 dt_str = iso_clean[:10] + "T" + iso_clean[11:].replace("-", ":") + "+00:00"
                 return datetime.fromisoformat(dt_str)
             except:
                 return None

        # Oldest
        oldest_ts = parse_ts(raw_files[0].name)
        if oldest_ts:
            raw_oldest_age_days = round((now - oldest_ts).total_seconds() / 86400.0, 2)
            
        # Newest
        newest_ts = parse_ts(raw_files[-1].name)
        if newest_ts:
            raw_newest_age_minutes = round((now - newest_ts).total_seconds() / 60.0, 2)


    # Last timestamps from logs
    last_capture_ts = None
    capture_log = base / "capture_log.jsonl"
    if capture_log.exists():
        lines = capture_log.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1].strip():
            try:
                last_capture_ts = json.loads(lines[-1]).get("timestamp_utc")
            except (json.JSONDecodeError, IndexError):
                pass

    last_promotion_ts = None
    promo_log = base / "promotion_log.jsonl"
    if promo_log.exists():
        lines = promo_log.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1].strip():
            try:
                last_promotion_ts = json.loads(lines[-1]).get("timestamp_utc")
            except (json.JSONDecodeError, IndexError):
                pass

    last_decay_ts = None
    decay_log = base / "decay_log.jsonl"
    if decay_log.exists():
        lines = decay_log.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1].strip():
            try:
                last_decay_ts = json.loads(lines[-1]).get("timestamp_utc")
            except (json.JSONDecodeError, IndexError):
                pass

    last_instability_ts = None
    inst_log = base / "instability_log.jsonl"
    if inst_log.exists():
        lines = inst_log.read_text(encoding="utf-8").strip().split("\n")
        if lines and lines[-1].strip():
            try:
                last_instability_ts = json.loads(lines[-1]).get("timestamp_utc")
            except (json.JSONDecodeError, IndexError):
                pass

    # Instability flags last 24h
    instability_flags_last_24h = 0
    if inst_log.exists():
        try:
            # Read last few lines (simplified) or scan all?
            # Let's scan all for correctness, file shouldn't be too huge yet
            # For robust production, would tail. Here, read all.
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - 86400
            
            for line in inst_log.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip(): continue
                rec = json.loads(line)
                ts_str = rec.get("timestamp_utc")
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if dt.timestamp() >= cutoff:
                            instability_flags_last_24h += len(rec.get("flags", []))
                    except ValueError:
                        pass
        except Exception:
            pass

    # Router hash
    router_ruleset_hash = None
    promo_log = base / "promotion_log.jsonl" # Use promotion log? No, routing log.
    routing_log = base / "routing_log.jsonl"
    if routing_log.exists():
         lines = routing_log.read_text(encoding="utf-8").strip().split("\n")
         if lines and lines[-1].strip():
             try:
                 router_ruleset_hash = json.loads(lines[-1]).get("router_ruleset_hash")
             except:
                 pass

    return {
        "raw_count": raw_count,
        "promoted_count": promoted_count,
        "archived_count": archived_count,
        "expired_stage1_count": expired_stage1_count,
        "expired_stage2_count": expired_stage2_count,
        "raw_oldest_age_days": raw_oldest_age_days,
        "raw_newest_age_minutes": raw_newest_age_minutes,
        "instability_flags_last_24h": instability_flags_last_24h,
        "router_ruleset_hash": router_ruleset_hash,
        "last_capture_ts": last_capture_ts,
        "last_promotion_ts": last_promotion_ts,
        "last_decay_ts": last_decay_ts,
        "last_instability_ts": last_instability_ts,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    """CLI entrypoint for capture subcommands."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture",
        description="Volatile capture layer — fast fragment intake.",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # capture add
    add_p = sub.add_parser("add", help="Capture a raw fragment")
    add_p.add_argument("--text", default=None, help="Inline text to capture")
    add_p.add_argument("--url", default=None, help="URL to record (no fetch)")
    add_p.add_argument("--file", dest="file_path", default=None, help="File to capture")
    add_p.add_argument("--stdin", action="store_true", help="Read from stdin")

    # capture status
    sub.add_parser("status", help="Print capture status as JSON")

    args = parser.parse_args(argv)

    if args.subcommand == "add":
        result = capture_add(
            text=args.text,
            url=args.url,
            file_path=args.file_path,
            from_stdin=args.stdin,
        )
        print(f"[OK] {result['filename']} -> {result['path']}")
        return 0
    elif args.subcommand == "status":
        status = capture_status()
        print(json.dumps(status, indent=2))
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
