"""
CLI commands for Signal Pipelines — post composer.

Usage:
    brn signal.compose --lane <lane> --platform <platform> --limit <N> [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from app.hq.post_composer.compose import compose_queue_item
from app.hq.post_composer.queue_contract import (
    VALID_LANES, VALID_PLATFORMS, SocialQueueV1,
)

_QUEUE_ROOT = Path("data/social_queue")


def brn_signal_compose(
    lane: str,
    platform: str,
    limit: int = 10,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """
    CLI entry point for signal compose.
    Returns 0 on success, 1 on failure.
    """
    if lane not in VALID_LANES:
        print(f"ERROR: Invalid lane '{lane}'. Must be one of: {sorted(VALID_LANES)}", file=sys.stderr)
        return 1

    if platform not in VALID_PLATFORMS:
        print(f"ERROR: Invalid platform '{platform}'. Must be one of: {sorted(VALID_PLATFORMS)}", file=sys.stderr)
        return 1

    queue_dir = _QUEUE_ROOT / lane / platform
    if not queue_dir.exists():
        print(f"ERROR: Queue directory not found: {queue_dir}", file=sys.stderr)
        return 1

    # Scan for queue items, sorted lexicographically (oldest-first)
    queue_files = sorted(queue_dir.glob("*.json"))

    if not queue_files:
        print(f"No queue items found in {queue_dir}")
        return 0

    # Take first N (oldest-first)
    selected = queue_files[:limit]
    print(f"Processing {len(selected)} of {len(queue_files)} queue items "
          f"(lane={lane}, platform={platform})")

    failures = 0
    for qf in selected:
        try:
            if dry_run:
                # Validate only
                with open(qf, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                queue = SocialQueueV1.from_dict(raw)
                print(f"  [OK] {qf.name} -> queue_id={queue.queue_id} (dry-run)")
            else:
                result = compose_queue_item(str(qf), force=force)
                written = len(result.get("written_files", []))
                skipped = len(result.get("skipped_files", []))
                print(f"  [OK] {qf.name} -> {result['out_dir']} "
                      f"(written={written}, skipped={skipped})")
        except Exception as e:
            print(f"  [FAIL] {qf.name} -> FAILED: {e}", file=sys.stderr)
            failures += 1

    if failures > 0:
        print(f"\nFAILED: {failures} item(s) failed", file=sys.stderr)
        return 1

    print(f"\nSUCCESS: {len(selected)} item(s) composed")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="brn signal.compose",
        description="Compose social queue items into HTML/MD/manifest outputs."
    )
    parser.add_argument("--lane", required=True, choices=sorted(VALID_LANES),
                        help="Signal lane")
    parser.add_argument("--platform", required=True, choices=sorted(VALID_PLATFORMS),
                        help="Target platform")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max items to process (oldest-first)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing outputs even if different")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate queue items without generating outputs")

    args = parser.parse_args(argv)
    return brn_signal_compose(
        lane=args.lane,
        platform=args.platform,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
