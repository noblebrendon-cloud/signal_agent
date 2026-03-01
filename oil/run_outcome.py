"""
OIL -- Incident Outcome Recorder (v0.7)

Appends an operator-annotated outcome to oil/memory/outcomes.jsonl.
If a case folder exists for the run_id, also syncs the outcome to
oil/cases/<run_id>/outcomes.jsonl (append-only, deduped by created_utc+kind).

Usage:
  python -m oil.run_outcome --run-id <run_id> --kind <kind> [--notes "text"]

  --kind must be one of: resolved, mitigated, false_positive, ignored

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent
_DEFAULT_OUTCOMES_PATH = _OIL_ROOT / "memory" / "outcomes.jsonl"
_DEFAULT_CASES_DIR = _OIL_ROOT / "cases"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oil.run_outcome",
        description="OIL -- record an incident outcome (append-only)",
    )
    parser.add_argument("--run-id", required=True, help="run_id from the incident artifact")
    parser.add_argument(
        "--kind",
        required=True,
        choices=["resolved", "mitigated", "false_positive", "ignored"],
        help="Outcome classification",
    )
    parser.add_argument("--notes", default="", help="Optional free-text notes")
    parser.add_argument(
        "--outcomes-path",
        default=str(_DEFAULT_OUTCOMES_PATH),
        help="Path to outcomes JSONL file (default: oil/memory/outcomes.jsonl)",
    )
    parser.add_argument(
        "--cases-dir",
        default=str(_DEFAULT_CASES_DIR),
        help="Cases directory (default: oil/cases/)",
    )
    args = parser.parse_args(argv)

    try:
        from oil.memory.outcomes import append_outcome
        from oil.cases.writer import _sync_case_outcomes

        append_outcome(
            run_id=args.run_id,
            outcome_kind=args.kind,
            notes=args.notes,
            outcomes_path=Path(args.outcomes_path),
        )
        print(f"Outcome recorded: run_id={args.run_id!r} kind={args.kind!r}")

        # v0.7: sync to case folder if it exists
        case_outcomes = Path(args.cases_dir) / args.run_id / "outcomes.jsonl"
        if case_outcomes.parent.exists():
            # Build the outcome entry that was just appended
            from datetime import datetime, timezone
            from oil.memory.outcomes import _utc_iso
            new_entry = {
                "run_id":       args.run_id,
                "outcome_kind": args.kind,
                "created_utc":  _utc_iso(),
                "notes":        args.notes,
            }
            _sync_case_outcomes(case_outcomes, [new_entry])
            print(f"Case outcomes updated: {case_outcomes}")

        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
