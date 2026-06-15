from __future__ import annotations

import argparse
import json
from pathlib import Path

from .intent import IntentParser
from .planner import OperatorPlanner
from .registry import OperatorRegistry
from .response import OperatorResponse, build_operator_response
from .runtime import OperatorRuntime


def run_operator_command(
    command_text: str,
    *,
    repo_root: Path,
    runs_dir: Path | None = None,
    state_dir: Path | None = None,
    canonical_ledger_path: Path | None = None,
) -> OperatorResponse:
    registry = OperatorRegistry.load(repo_root)
    parser = IntentParser(registry)
    planner = OperatorPlanner(registry)
    runtime = OperatorRuntime(
        registry,
        runs_dir=runs_dir,
        state_dir=state_dir,
        canonical_ledger_path=canonical_ledger_path,
    )
    parsed_intent = parser.parse(command_text)
    plan = planner.plan(parsed_intent)
    result = runtime.execute(plan)
    return build_operator_response(plan, result, registry)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signal-operator",
        description="Repo-native internal operator surface for Signal Agent.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Single-turn operator message.",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Single-turn operator message. Equivalent to the positional message.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start a simple operator shell loop.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the structured response as JSON.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect. Defaults to the current directory.",
    )
    return parser


def _interactive_loop(repo_root: Path, *, emit_json: bool) -> int:
    print("internal_operator_agent v0")
    print("Type 'exit' or 'quit' to stop.")
    while True:
        try:
            command_text = input("operator> ").strip()
        except EOFError:
            print()
            return 0
        if not command_text:
            continue
        if command_text.lower() in {"exit", "quit"}:
            return 0
        response = run_operator_command(command_text, repo_root=repo_root)
        if emit_json:
            print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(response.to_text())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    command_text = args.command or args.message

    if args.interactive or command_text is None:
        return _interactive_loop(repo_root, emit_json=bool(args.json))

    response = run_operator_command(command_text, repo_root=repo_root)
    if args.json:
        print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(response.to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
