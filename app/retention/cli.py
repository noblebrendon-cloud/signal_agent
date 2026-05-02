from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.retention.dispatch import plan_dispatch
from app.retention.dispatch_gate import evaluate_dispatch_ready
from app.retention.identity import get_repo_root
from app.retention.jsonl_store import append_record, ensure_required_state_files, preview_record
from app.retention.models import (
    ALLOWED_SOURCES,
    CLI_CONSENT_STATUSES,
    build_contact_seed_event,
    build_contact_snapshot,
)
from app.retention.outbound_authorization import authorize_send_preview, resolve_preview_path
from app.retention.reconcile import reconcile_state
from app.retention.send_queue import project_send_queue
from app.retention.sender_contract import preview_send_queue, resolve_queue_path
from app.retention.substack_csv import ingest_substack_csv
from app.retention.transitions import evaluate_transition, load_latest_contact_snapshot
from app.utils.io_contract import atomic_write_text


def _json_print(label: str, payload: dict | None) -> None:
    print(f"{label}:")
    if payload is None:
        print("null")
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.retention.cli",
        description="Minimal append-only retention CLI for contact seeding.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_contact = subparsers.add_parser("add-contact", help="Seed one contact as a canonical retention event")
    add_contact.add_argument("--source", required=True, choices=ALLOWED_SOURCES)
    add_contact.add_argument("--identifier-kind", required=True, choices=["email"])
    add_contact.add_argument("--identifier-value", required=True)
    add_contact.add_argument("--consent-status", required=True, choices=CLI_CONSENT_STATUSES)
    mode = add_contact.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    add_contact.add_argument(
        "--plan-dispatch",
        action="store_true",
        help="Append a planned dispatch record when a dispatch rule matches. No external send occurs.",
    )

    ingest_substack = subparsers.add_parser(
        "ingest-substack-csv",
        help="Ingest a Substack subscriber CSV export through the retention transition path",
    )
    ingest_substack.add_argument("--input", required=True, help="Path to a Substack subscriber CSV export")
    ingest_mode = ingest_substack.add_mutually_exclusive_group(required=True)
    ingest_mode.add_argument("--dry-run", action="store_true")
    ingest_mode.add_argument("--apply", action="store_true")
    ingest_substack.add_argument(
        "--plan-dispatch",
        action="store_true",
        help="Append planned dispatch records only when the retention planner allows them.",
    )

    reconcile = subparsers.add_parser("reconcile", help="Read-only reconciliation over retention ledgers")
    reconcile.add_argument("--state-root", required=True, help="State root containing the retention ledgers")

    dispatch_ready = subparsers.add_parser(
        "dispatch-ready",
        help="Read-only dispatch readiness gate over planned retention dispatch records",
    )
    dispatch_ready.add_argument("--state-root", required=True, help="State root containing the retention ledgers")

    project_send_queue_parser = subparsers.add_parser(
        "project-send-queue",
        help="Project eligible dispatch-ready records into a deterministic send queue preview",
    )
    project_send_queue_parser.add_argument(
        "--state-root",
        required=True,
        help="State root containing the retention ledgers",
    )
    project_send_queue_parser.add_argument(
        "--out",
        help="Optional JSON output file path for the projection preview. No ledgers are mutated.",
    )

    send_preview_parser = subparsers.add_parser(
        "send-preview",
        help="Validate a projected send queue through a local no-network sender adapter preview",
    )
    send_preview_parser.add_argument("--queue", required=True, help="Path to a send queue projection JSON file")
    send_preview_parser.add_argument("--adapter", required=True, help="Adapter name to validate against")
    send_preview_parser.add_argument(
        "--out",
        help="Optional JSON output file path for the local sender preview. No ledgers are mutated.",
    )

    authorize_send_parser = subparsers.add_parser(
        "authorize-send",
        help="Apply an explicit local operator authorization decision to a sender preview artifact",
    )
    authorize_send_parser.add_argument("--preview", required=True, help="Path to a sender preview JSON file")
    authorize_send_parser.add_argument("--operator-id", required=True, help="Explicit operator identifier")
    authorize_send_parser.add_argument("--decision", required=True, help="Authorization decision: approve or deny")
    authorize_send_parser.add_argument(
        "--out",
        help="Optional JSON output file path for the authorization result. No ledgers are mutated.",
    )
    return parser


def run_add_contact(args: argparse.Namespace) -> int:
    event = build_contact_seed_event(
        source=args.source,
        identifier_kind=args.identifier_kind,
        identifier_value=args.identifier_value,
        consent_status=args.consent_status,
    )
    previous_snapshot = load_latest_contact_snapshot(event["contact_id"])
    transition = evaluate_transition(event, previous_snapshot=previous_snapshot)
    contact_snapshot = build_contact_snapshot(
        previous_snapshot=previous_snapshot,
        event=event,
        transition=transition,
    )
    dispatch_plan = plan_dispatch(contact_snapshot, contact_id=event["contact_id"])

    if args.dry_run:
        event_out = preview_record("events.jsonl", event)
        transition_out = preview_record("transitions.jsonl", transition)
        contact_out = preview_record("contacts.jsonl", contact_snapshot) if contact_snapshot else None
        if dispatch_plan.get("decision") == "planned":
            dispatch_out = preview_record("content_dispatch.jsonl", dispatch_plan)
        else:
            dispatch_out = dispatch_plan

        _json_print("event", event_out)
        _json_print("transition", transition_out)
        _json_print("contact_snapshot", contact_out)
        _json_print("dispatch_plan", dispatch_out)
        return 0

    ensure_required_state_files()

    event_out = append_record("events.jsonl", event)
    transition_out = append_record("transitions.jsonl", transition)
    contact_out = append_record("contacts.jsonl", contact_snapshot) if contact_snapshot else None

    dispatch_out = dispatch_plan
    if args.plan_dispatch and dispatch_plan.get("decision") == "planned":
        dispatch_out = append_record("content_dispatch.jsonl", dispatch_plan)

    _json_print("event", event_out)
    _json_print("transition", transition_out)
    _json_print("contact_snapshot", contact_out)
    _json_print("dispatch_plan", dispatch_out)
    return 0


def run_reconcile(args: argparse.Namespace) -> int:
    report = reconcile_state(args.state_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["clean"] else 1


def run_dispatch_ready(args: argparse.Namespace) -> int:
    report = evaluate_dispatch_ready(args.state_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["clean"] else 1


def run_ingest_substack_csv(args: argparse.Namespace) -> int:
    report = ingest_substack_csv(
        args.input,
        apply=bool(args.apply),
        plan_dispatch_enabled=bool(args.plan_dispatch),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _resolve_output_path(path_value: str) -> Path:
    repo_root = get_repo_root()
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def _write_projection_output(output_path: Path, state_root: str, payload: str) -> None:
    resolved_output = output_path.resolve()
    resolved_state_root = Path(state_root).resolve()
    protected_paths = {
        (resolved_state_root / ledger_name).resolve()
        for ledger_name in (
            "contacts.jsonl",
            "events.jsonl",
            "transitions.jsonl",
            "content_dispatch.jsonl",
        )
    }
    protected_paths.update({path.with_suffix(path.suffix + ".lock") for path in protected_paths})
    if resolved_output in protected_paths:
        raise ValueError(f"projection_output_conflicts_with_retention_ledger:{resolved_output}")
    if resolved_output.name.endswith(".lock"):
        raise ValueError(f"projection_output_lock_sidecar_not_allowed:{resolved_output}")
    atomic_write_text(resolved_output, payload)


def _write_sender_preview_output(output_path: Path, queue_path: Path, payload: str) -> None:
    resolved_output = output_path.resolve()
    resolved_queue_path = queue_path.resolve()
    protected_paths = {resolved_queue_path}
    protected_paths.update(
        {
            (resolved_queue_path.parent / ledger_name).resolve()
            for ledger_name in (
                "contacts.jsonl",
                "events.jsonl",
                "transitions.jsonl",
                "content_dispatch.jsonl",
            )
        }
    )
    protected_paths.update({path.with_suffix(path.suffix + ".lock") for path in protected_paths})
    if resolved_output in protected_paths:
        raise ValueError(f"sender_preview_output_conflicts_with_protected_path:{resolved_output}")
    if resolved_output.name.endswith(".lock"):
        raise ValueError(f"sender_preview_output_lock_sidecar_not_allowed:{resolved_output}")
    atomic_write_text(resolved_output, payload)


def _write_authorization_output(output_path: Path, preview_path: Path, payload: str) -> None:
    resolved_output = output_path.resolve()
    resolved_preview_path = preview_path.resolve()
    protected_paths = {
        resolved_preview_path,
        (resolved_preview_path.parent / "send_queue_preview.json").resolve(),
    }
    protected_paths.update(
        {
            (resolved_preview_path.parent / ledger_name).resolve()
            for ledger_name in (
                "contacts.jsonl",
                "events.jsonl",
                "transitions.jsonl",
                "content_dispatch.jsonl",
            )
        }
    )
    protected_paths.update({path.with_suffix(path.suffix + ".lock") for path in protected_paths})
    if resolved_output in protected_paths:
        raise ValueError(f"authorization_output_conflicts_with_protected_path:{resolved_output}")
    if resolved_output.name.endswith(".lock"):
        raise ValueError(f"authorization_output_lock_sidecar_not_allowed:{resolved_output}")
    atomic_write_text(resolved_output, payload)


def run_project_send_queue(args: argparse.Namespace) -> int:
    report = project_send_queue(args.state_root)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        _write_projection_output(
            _resolve_output_path(args.out),
            report["source_state_root"],
            payload + "\n",
        )
    return 0 if report["clean"] else 1


def run_send_preview(args: argparse.Namespace) -> int:
    report = preview_send_queue(args.queue, adapter=args.adapter)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        _write_sender_preview_output(
            _resolve_output_path(args.out),
            resolve_queue_path(args.queue),
            payload + "\n",
        )
    return 0 if report["clean"] else 1


def run_authorize_send(args: argparse.Namespace) -> int:
    report = authorize_send_preview(
        args.preview,
        operator_id=args.operator_id,
        decision=args.decision,
    )
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        _write_authorization_output(
            _resolve_output_path(args.out),
            resolve_preview_path(args.preview),
            payload + "\n",
        )
    return 0 if report["clean"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "add-contact":
        return run_add_contact(args)
    if args.command == "ingest-substack-csv":
        return run_ingest_substack_csv(args)
    if args.command == "reconcile":
        return run_reconcile(args)
    if args.command == "dispatch-ready":
        return run_dispatch_ready(args)
    if args.command == "project-send-queue":
        return run_project_send_queue(args)
    if args.command == "send-preview":
        return run_send_preview(args)
    if args.command == "authorize-send":
        return run_authorize_send(args)
    parser.error(f"unsupported_command:{args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
