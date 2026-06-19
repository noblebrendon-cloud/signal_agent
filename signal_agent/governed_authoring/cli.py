from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .command_router import (
    LocalAuthoringCommandRouter,
    RouterErrorRaised,
    router_error_from_path_policy,
)
from .offline_harness import run_offline_verification_file, write_static_import_packet
from .path_policy import PathPolicyError
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


def _router_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m signal_agent.governed_authoring.cli router",
        description="Run bounded local command-router workflows.",
    )
    subparsers = parser.add_subparsers(dest="router_command", required=True)

    verify = subparsers.add_parser(
        "verify-static-export",
        help="Verify a static export packet into an explicit local workspace.",
    )
    verify.add_argument("--input", required=True, type=Path, help="Static prototype export JSON file.")
    verify.add_argument("--workspace", required=True, type=Path, help="Explicit local workspace directory.")
    verify.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit result path under workspace results/.",
    )
    verify.add_argument(
        "--canonical-ledger",
        type=Path,
        default=None,
        help="Optional explicit canonical ledger path under workspace ledgers/.",
    )
    verify.add_argument(
        "--with-canonical-ledger",
        action="store_true",
        help="Require an explicit canonical ledger path.",
    )

    demo = subparsers.add_parser(
        "run-demo-bundle",
        help="Run the demo bundle into an explicit local workspace.",
    )
    demo.add_argument("--workspace", required=True, type=Path, help="Explicit local workspace directory.")
    demo.add_argument(
        "--canonical-ledger",
        type=Path,
        default=None,
        help="Optional explicit canonical ledger path under workspace ledgers/.",
    )
    demo.add_argument(
        "--with-canonical-ledger",
        action="store_true",
        help="Require an explicit canonical ledger path.",
    )

    inspect = subparsers.add_parser(
        "inspect-result-packet",
        help="Inspect a static-import-compatible result packet.",
    )
    inspect.add_argument("--input", required=True, type=Path, help="Static import result JSON file.")
    inspect.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Required only when writing an inspection report.",
    )
    inspect.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional explicit report path under workspace summaries/.",
    )

    validate = subparsers.add_parser(
        "validate-output-directory",
        help="Validate an explicit local workspace directory.",
    )
    validate.add_argument("--workspace", required=True, type=Path, help="Candidate local workspace directory.")

    summarize = subparsers.add_parser(
        "summarize-proof-output",
        help="Summarize result packets in an explicit local workspace.",
    )
    summarize.add_argument("--workspace", required=True, type=Path, help="Explicit local workspace directory.")
    summarize.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional explicit summary path under workspace summaries/.",
    )
    return parser


def _router_default_result_path(input_path: Path, workspace: Path) -> Path:
    return workspace / "results" / f"{input_path.stem}.result.json"


def _router_default_summary_path(workspace: Path) -> Path:
    return workspace / "summaries" / "proof_output_summary.md"


def _result_code_for_error(code: str, category: str) -> int:
    if code in {"MISSING_INPUT", "INVALID_JSON", "UNSUPPORTED_PACKET_SHAPE", "UNSUPPORTED_COMMAND"}:
        return 2
    if code == "AMBIGUOUS_PATH":
        return 7
    if category == "governance":
        return 4
    return 3


def _print_router_result(result: Any) -> None:
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def _print_router_error(error: dict[str, Any]) -> None:
    print(json.dumps(error, indent=2, sort_keys=True), file=sys.stderr)


def _run_router(args_list: Sequence[str]) -> int:
    parser = _router_parser()
    args = parser.parse_args(list(args_list))
    router = LocalAuthoringCommandRouter()
    try:
        if args.router_command == "verify-static-export":
            result_path = args.output or _router_default_result_path(args.input, args.workspace)
            result = router.verify_static_export(
                input_path=args.input,
                workspace_path=args.workspace,
                result_path=result_path,
                canonical_ledger_path=args.canonical_ledger,
                canonical_ledger_requested=args.with_canonical_ledger,
            )
        elif args.router_command == "run-demo-bundle":
            result = router.run_demo_bundle(
                workspace_path=args.workspace,
                canonical_ledger_path=args.canonical_ledger,
                canonical_ledger_requested=args.with_canonical_ledger,
            )
        elif args.router_command == "inspect-result-packet":
            result = router.inspect_result_packet(
                input_path=args.input,
                workspace_path=args.workspace,
                report_path=args.report,
            )
        elif args.router_command == "validate-output-directory":
            result = router.validate_output_directory(workspace_path=args.workspace)
        elif args.router_command == "summarize-proof-output":
            result = router.summarize_proof_output(
                workspace_path=args.workspace,
                summary_path=args.summary or _router_default_summary_path(args.workspace),
            )
        else:
            parser.error(f"unsupported router command: {args.router_command}")
    except RouterErrorRaised as exc:
        error = exc.error.to_dict()
        _print_router_error(error)
        return _result_code_for_error(exc.error.code, exc.error.category)
    except PathPolicyError as exc:
        error = router_error_from_path_policy(exc, command=args.router_command).to_dict()
        _print_router_error(error)
        return _result_code_for_error(str(error["code"]), str(error["category"]))

    _print_router_result(result)
    return result.result_code


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "router":
        return _run_router(args_list[1:])

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
