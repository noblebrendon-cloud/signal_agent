from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from signal_agent.media_opportunities.models import (
    ALL_STATES,
    OPPORTUNITY_TYPES,
    RELATIONSHIP_CLASSIFICATIONS,
    VISIBILITIES,
)
from signal_agent.media_opportunities.service import MediaOpportunityError, MediaOpportunityService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m signal_agent.media_opportunities.cli",
        description="Private-first media opportunity and independent coverage pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-opportunity")
    create.add_argument("--type", choices=OPPORTUNITY_TYPES, required=True)
    create.add_argument("--invitation-text")
    create.add_argument("--invitation-file")
    create.add_argument("--url")
    create.add_argument("--source-ref")
    create.add_argument("--outlet")
    create.add_argument("--contact")
    create.add_argument("--deadline")
    create.add_argument("--topic")
    create.add_argument("--relationship", choices=RELATIONSHIP_CLASSIFICATIONS, default="unknown")
    create.add_argument("--visibility", choices=VISIBILITIES, default="private")
    create.add_argument("--next-action")
    create.add_argument("--notes")

    transition = sub.add_parser("transition")
    transition.add_argument("--opportunity-id", required=True)
    transition.add_argument("--state", choices=ALL_STATES, required=True)
    transition.add_argument("--reason")
    transition.add_argument("--next-action")
    transition.add_argument("--notes")

    approve = sub.add_parser("approve-public-reference")
    approve.add_argument("--opportunity-id", required=True)
    approve.add_argument("--published-url", required=True)
    approve.add_argument("--title", required=True)
    approve.add_argument("--outlet", required=True)
    approve.add_argument("--author")
    approve.add_argument("--date")
    approve.add_argument("--coverage-type", required=True)
    approve.add_argument("--description", required=True)
    approve.add_argument("--substantially-about", action="store_true")
    approve.add_argument("--verification-note")
    approve.add_argument("--evidence", action="append", default=[])
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--human-approved", action="store_true")
    approve.add_argument("--relationship", choices=RELATIONSHIP_CLASSIFICATIONS)
    approve.add_argument("--paid-placement", action="store_true")

    show = sub.add_parser("show-opportunity")
    show.add_argument("--opportunity-id")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = MediaOpportunityService()
    try:
        payload = _dispatch(service, args)
    except (MediaOpportunityError, ValueError, OSError) as exc:
        _print_json({"clean": False, "error": str(exc), "command": args.command})
        return 1
    _print_json(payload)
    return 0 if payload.get("clean") is True else 1


def _dispatch(service: MediaOpportunityService, args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create-opportunity":
        return service.create_opportunity(
            opportunity_type=args.type,
            original_request_text=_invitation_text(args),
            outlet_or_organization=args.outlet,
            contact_or_source_name=args.contact,
            originating_url_or_source_ref=args.url or args.source_ref,
            topic_or_subject=args.topic,
            deadline=args.deadline,
            relationship_classification=args.relationship,
            visibility=args.visibility,
            next_action=args.next_action,
            notes=args.notes,
        )
    if args.command == "transition":
        return service.transition_opportunity(
            args.opportunity_id,
            args.state,
            reason_code=args.reason,
            next_action=args.next_action,
            notes=args.notes,
        )
    if args.command == "approve-public-reference":
        return service.approve_public_reference(
            args.opportunity_id,
            published_url=args.published_url,
            title=args.title,
            outlet=args.outlet,
            author=args.author,
            published_date=args.date,
            coverage_type=args.coverage_type,
            short_description=args.description,
            substantially_about=args.substantially_about,
            verification_note=args.verification_note,
            evidence=args.evidence,
            approved_by=args.approved_by,
            human_approved=args.human_approved,
            relationship_classification=args.relationship,
            paid_placement=args.paid_placement,
        )
    if args.command == "show-opportunity":
        return service.summary(args.opportunity_id)
    raise ValueError(f"media_opportunity_unknown_command:{args.command}")


def _invitation_text(args: argparse.Namespace) -> str:
    if args.invitation_file:
        return Path(args.invitation_file).read_text(encoding="utf-8")
    if args.invitation_text is not None:
        return args.invitation_text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("media_opportunity_invitation_text_required")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    raise SystemExit(main())
