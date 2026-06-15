from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

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


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
