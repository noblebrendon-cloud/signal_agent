from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .offline_harness import run_offline_verification_file, write_static_import_packet
from .runtime import GovernedAuthoringRuntime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Governed Authoring backend proof path.")
    parser.add_argument("source_packet", type=Path, help="Path to a source packet JSON file.")
    parser.add_argument(
        "--canonical-ledger",
        type=Path,
        default=None,
        help="Optional canonical governed-transition JSONL ledger path.",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=None,
        help="Optional path for writing only the output manifest JSON.",
    )
    return parser


def _verify_static_export_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m signal_agent.governed_authoring.cli verify-static-export",
        description="Run a static prototype export JSON file through the local offline verification harness.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to a static prototype export JSON file.")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path for writing the static-import-compatible result JSON file.",
    )
    parser.add_argument(
        "--canonical-ledger",
        type=Path,
        default=None,
        help="Optional temp/test canonical governed-transition JSONL ledger path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "verify-static-export":
        parser = _verify_static_export_parser()
        args = parser.parse_args(args_list[1:])
        if not args.input.exists():
            parser.error(f"static export input does not exist: {args.input}")
        result = run_offline_verification_file(
            args.input,
            canonical_ledger_path=args.canonical_ledger,
        )
        write_static_import_packet(args.output, result)
        print(json.dumps(result["static_import_packet"], indent=2, sort_keys=True))
        return 0

    args = _parser().parse_args(args_list)
    payload = json.loads(args.source_packet.read_text(encoding="utf-8"))
    runtime = GovernedAuthoringRuntime(canonical_ledger_path=args.canonical_ledger)
    result = runtime.run(payload)
    manifest = result.output_manifest.to_dict()

    if args.output_manifest is not None:
        args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.output_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
