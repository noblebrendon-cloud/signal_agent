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

    return {
        "raw_count": raw_count,
        "promoted_count": promoted_count,
        "archived_count": archived_count,
        "last_capture_ts": last_capture_ts,
        "last_promotion_ts": last_promotion_ts,
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
