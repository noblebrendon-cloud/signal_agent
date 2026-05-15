from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.letters_of_light.weekly_models import load_weekly_letter
from app.letters_of_light.weekly_render import write_weekly_artifacts
from app.letters_of_light.weekly_store import append_weekly_transition, register_weekly_letter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.letters_of_light.weekly_cli",
        description="Local-only weekly Letters of Light tools. No external sending.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a canonical weekly letter file")
    validate.add_argument("--letter", required=True, help="Path to the weekly letter markdown file")

    render = sub.add_parser("render", help="Render local-only Sunday preview artifacts")
    render.add_argument("--letter", required=True, help="Path to the weekly letter markdown file")
    render.add_argument("--out-dir", help="Output directory for rendered artifacts")

    register = sub.add_parser("register", help="Append the weekly letter record and initial draft transition")
    register.add_argument("--letter", required=True, help="Path to the weekly letter markdown file")
    register.add_argument("--actor-id", required=True, help="Human or local operator identifier")

    transition = sub.add_parser("transition", help="Append a valid weekly status transition")
    transition.add_argument("--letter-id", required=True)
    transition.add_argument("--from-state", required=True)
    transition.add_argument("--to-state", required=True)
    transition.add_argument("--actor-id", required=True)
    transition.add_argument("--reason-code", default="operator_transition")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            letter = load_weekly_letter(args.letter)
            print(json.dumps(_letter_summary(letter), indent=2, sort_keys=True))
            return 0
        if args.command == "render":
            letter = load_weekly_letter(args.letter)
            paths = write_weekly_artifacts(letter, out_dir=args.out_dir)
            print(json.dumps({"clean": True, "paths": paths}, indent=2, sort_keys=True))
            return 0
        if args.command == "register":
            letter = load_weekly_letter(args.letter)
            result = register_weekly_letter(letter, actor_id=args.actor_id)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "transition":
            from_state = None if args.from_state == "missing" else args.from_state
            result = append_weekly_transition(
                letter_id=args.letter_id,
                from_state=from_state,
                to_state=args.to_state,
                actor_id=args.actor_id,
                reason_code=args.reason_code,
            )
            print(json.dumps({"clean": True, "transition_record": result}, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"clean": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    parser.error(f"unsupported_command:{args.command}")
    return 2


def _letter_summary(letter) -> dict:
    return {
        "clean": True,
        "letter_id": letter.letter_id,
        "title": letter.title,
        "week_date": letter.week_date,
        "status": letter.status,
        "content_hash": letter.content_hash,
        "external_action_allowed": False,
        "send_externally": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
