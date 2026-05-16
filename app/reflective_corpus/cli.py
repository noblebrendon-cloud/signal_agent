from __future__ import annotations

import argparse
import json
from typing import Any

from app.reflective_corpus.detection import detect_pressures, detect_theme_matches, suggest_essay_candidates
from app.reflective_corpus.reconcile import reconcile_reflective_corpus_state
from app.reflective_corpus.report import generate_corpus_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.reflective_corpus.cli",
        description="Local-only Reflective Corpus Engine CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser(
        "corpus-detect-themes",
        help="Detect deterministic theme matches for stored fragments",
    )
    detect.set_defaults(func=run_detect_themes)

    detect_pressures_parser = subparsers.add_parser(
        "corpus-detect-pressures",
        help="Detect deterministic contrast-pair pressures for stored fragments",
    )
    detect_pressures_parser.set_defaults(func=run_detect_pressures)

    suggest_essays = subparsers.add_parser(
        "corpus-suggest-essays",
        help="Suggest deterministic seed essay candidates from detected pressures",
    )
    suggest_essays.set_defaults(func=run_suggest_essays)

    reconcile = subparsers.add_parser(
        "corpus-reconcile",
        help="Reconcile reflective corpus ledgers",
    )
    reconcile.set_defaults(func=run_reconcile)

    report = subparsers.add_parser(
        "corpus-report",
        help="Write a deterministic reflective corpus markdown report",
    )
    report.set_defaults(func=run_report)

    return parser


def run_detect_themes(args: argparse.Namespace) -> int:
    del args
    _print_json(
        {
            "matches": detect_theme_matches(),
            "external_action_allowed": False,
        }
    )
    return 0


def run_detect_pressures(args: argparse.Namespace) -> int:
    del args
    _print_json(
        {
            "pressures": detect_pressures(),
            "external_action_allowed": False,
        }
    )
    return 0


def run_suggest_essays(args: argparse.Namespace) -> int:
    del args
    _print_json(
        {
            "candidates": suggest_essay_candidates(),
            "external_action_allowed": False,
        }
    )
    return 0


def run_reconcile(args: argparse.Namespace) -> int:
    del args
    report = reconcile_reflective_corpus_state()
    _print_json(report)
    return 0 if report["clean"] else 1


def run_report(args: argparse.Namespace) -> int:
    del args
    _print_json(generate_corpus_report())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, TypeError, ValueError) as exc:
        _print_json(
            {
                "clean": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "external_action_allowed": False,
            }
        )
        return 1


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
