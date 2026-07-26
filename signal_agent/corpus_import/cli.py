from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .hashing import canonical_json
from .milestone1 import run_milestone1


class CliUsageError(Exception):
    """Raised for operator-correctable argument errors."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _print_json(payload: dict) -> None:
    sys.stdout.write(canonical_json(payload) + "\n")


def _handle_validate(args: argparse.Namespace) -> int:
    result = run_milestone1(Path(args.source), Path(args.run_root))
    _print_json(result.receipt)
    return result.exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="signal-agent corpus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-chatgpt-export")
    validate.add_argument("--source", required=True)
    validate.add_argument("--run-root", required=True)
    validate.set_defaults(handler=_handle_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv[:1] == ["corpus"]:
        effective_argv = effective_argv[1:]

    parser = _build_parser()
    try:
        args = parser.parse_args(effective_argv)
        return int(args.handler(args))
    except CliUsageError as exc:
        _print_json(
            {
                "clean": False,
                "status": "error",
                "reason_code": "usage_error",
                "issues": [str(exc)],
                "publication_authorization": "none",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
