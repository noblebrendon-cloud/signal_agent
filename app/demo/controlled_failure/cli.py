from __future__ import annotations

import argparse
import json
from typing import Sequence

from .governed_runner import run_governed_demo
from .standard_runner import run_standard_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled failure demo")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Run the controlled failure demo")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 1

    standard = run_standard_demo()
    governed = run_governed_demo()

    print("=== STANDARD SYSTEM ===")
    print(f"status: {standard['status']}")
    print(f"message: {standard['message']}")
    print(f"hidden_problem: {standard['hidden_problem']}")
    print()
    print("=== GOVERNED SYSTEM ===")
    print(f"status: {governed['status']}")
    print(f"reason_code: {governed['reason_code']}")
    print(f"failed_step: {governed['failed_step']}")
    print(f"missing_fields: {json.dumps(governed['missing_fields'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
