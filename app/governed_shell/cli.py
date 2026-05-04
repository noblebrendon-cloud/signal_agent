from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .confirm import check_confirmation
from .errors import (
    AuditLogError,
    ConfirmationError,
    ExecutionPlanError,
    GovernedShellError,
    PolicyDeniedError,
    ProposalLoadError,
    ProposalNormalizationError,
    ProposalPathError,
    ProposalSchemaError,
    ReplayVerificationError,
    SimulationError,
    SnapshotError,
)
from .execution_plan import build_execution_plan, verify_execution_plan, write_sealed_plan
from .executor import simulate_plan
from .logstore import build_review_event, append_audit_event, read_audit_events
from .normalize import normalize_and_hash_proposal
from .policy import evaluate_policy
from .proposal import dump_canonical_json, load_proposal
from .replay import replay_session, verify_log
from .schema_validate import validate_command_proposal


class CliUsageError(Exception):
    """Raised when CLI arguments or required inputs are missing."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _print_json(payload: dict) -> None:
    sys.stdout.write(dump_canonical_json(payload) + "\n")


def _error_payload(*, reason_code: str, issues: list[str], status: str = "error") -> dict:
    return {
        "clean": False,
        "issues": list(issues),
        "reason_code": reason_code,
        "status": status,
    }


def _success_payload(*, status: str, reason_code: str, **fields: object) -> dict:
    payload = {
        "clean": True,
        "issues": [],
        "reason_code": reason_code,
        "status": status,
    }
    payload.update(fields)
    return payload


def _session_id_for_proposal_hash(proposal_hash: str) -> str:
    return f"session.{proposal_hash.split(':', 1)[1][:12]}"


def _require_existing_path(path: Path, *, label: str) -> None:
    if not Path(path).exists():
        raise CliUsageError(f"{label} file does not exist: {path}")


def _load_json_object(path: Path, *, label: str) -> dict:
    _require_existing_path(path, label=label)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliUsageError(f"unable to read {label} file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GovernedShellError(
            f"malformed {label} JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if type(payload) is not dict:
        raise GovernedShellError(f"{label} JSON must decode to a top-level object.")
    return payload


def _proposal_stub(intent: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_stub_001",
        "created_at": "1970-01-01T00:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": intent,
            "justification": "Local operator stub only.",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "human",
            "proposal_only": True,
            "agent_family": "local",
            "agent_id": "cli_stub",
        },
        "path_refs": [
            {
                "path_ref_id": "target_dir",
                "root_id": "workspace",
                "relative_path": "docs/operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_list_target",
                "operation_type": "powershell_cmdlet",
                "cmdlet_id": "ps.get_child_items_v1",
                "parameters": [
                    {
                        "name": "target_path_ref",
                        "value_type": "path_ref",
                        "path_ref": "target_dir",
                    },
                    {
                        "name": "recurse",
                        "value_type": "boolean",
                        "boolean_value": False,
                    },
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "human_authored",
            "model_declared_risk_level": "low",
            "rationale": "Schema-compatible stub only.",
        },
    }


def _review_report(normalized, decision) -> dict:
    return {
        "clean": bool(decision.clean),
        "status": decision.decision,
        "reason_code": decision.reason_code,
        "issues": list(decision.issues),
        "proposal_id": str(normalized.proposal["proposal_id"]),
        "proposal_hash": normalized.proposal_hash,
        "session_id": _session_id_for_proposal_hash(normalized.proposal_hash),
        "policy_hash": decision.policy_hash,
        "matched_binding_id": decision.matched_binding_id,
        "effective_risk": decision.effective_risk,
        "confirmation_required": decision.confirmation_required,
        "confirmation_mode": decision.confirmation_mode,
        "declared_reads": list(decision.declared_reads),
        "declared_writes": list(decision.declared_writes),
        "network_allowed": decision.network_allowed,
        "privilege_escalation_allowed": decision.privilege_escalation_allowed,
    }


def _append_review_audit(audit_path: Path, normalized, decision) -> dict:
    event_index = 0 if not audit_path.exists() else len(read_audit_events(audit_path))
    status_map = {
        "allow": "allowed",
        "deny": "rejected",
        "require_confirmation": "require_confirmation",
    }
    event = build_review_event(
        session_id=_session_id_for_proposal_hash(normalized.proposal_hash),
        event_index=event_index,
        timestamp_utc=_utc_now_iso(),
        proposal_id=str(normalized.proposal["proposal_id"]),
        proposal_hash=normalized.proposal_hash,
        policy_hash=decision.policy_hash,
        risk_level=decision.effective_risk or "high",
        decision_code=decision.reason_code,
        status=status_map.get(decision.decision, "failed"),
        details={
            "decision": decision.decision,
            "issues": list(decision.issues),
            "matched_binding_id": decision.matched_binding_id,
        },
    )
    return append_audit_event(audit_path, event)


def _load_validate_normalize_review(proposal_path: Path):
    _require_existing_path(proposal_path, label="proposal")
    proposal = load_proposal(proposal_path)
    validation = validate_command_proposal(proposal)
    if not validation.clean:
        raise ProposalSchemaError(
            "Command proposal schema validation failed: "
            + "; ".join(validation.errors)
        )
    normalized = normalize_and_hash_proposal(proposal)
    decision = evaluate_policy(normalized)
    return proposal, normalized, decision


def _handle_propose_stub(args: argparse.Namespace) -> int:
    _print_json(_proposal_stub(args.intent))
    return 0


def _handle_policy_test(args: argparse.Namespace) -> int:
    _, normalized, decision = _load_validate_normalize_review(Path(args.proposal))
    report = _review_report(normalized, decision)
    _print_json(report)
    return 0 if decision.clean else 1


def _handle_review(args: argparse.Namespace) -> int:
    _, normalized, decision = _load_validate_normalize_review(Path(args.proposal))
    report = _review_report(normalized, decision)
    if args.audit is not None:
        audit_event = _append_review_audit(Path(args.audit), normalized, decision)
        report["audit_event_id"] = audit_event["event_id"]
    _print_json(report)
    return 0 if decision.clean else 1


def _handle_approve(args: argparse.Namespace) -> int:
    _, normalized, decision = _load_validate_normalize_review(Path(args.proposal))
    if not decision.clean or decision.decision == "deny":
        report = _review_report(normalized, decision)
        _print_json(report)
        return 1

    if args.proposal_hash is not None and args.proposal_hash != normalized.proposal_hash:
        _print_json(
            _error_payload(
                reason_code="confirmation_mismatch",
                status="deny",
                issues=["supplied_hash does not exactly match proposal_hash."],
            )
        )
        return 1

    confirmation = check_confirmation(
        normalized.proposal_hash,
        args.proposal_hash,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    if not confirmation.clean:
        _print_json(
            {
                "clean": False,
                "status": "deny",
                "reason_code": confirmation.reason_code,
                "issues": list(confirmation.issues),
                "proposal_hash": normalized.proposal_hash,
            }
        )
        return 1

    plan = build_execution_plan(normalized, decision, confirmation)
    out_path = Path(args.out)
    write_sealed_plan(out_path, plan)
    _print_json(
        _success_payload(
            status="plan_created",
            reason_code="approved",
            plan_hash=plan["plan_hash"],
            plan_id=plan["plan_id"],
            proposal_hash=plan["proposal_hash"],
            session_id=plan["session_id"],
            matched_binding_id=plan["matched_binding_id"],
            effective_risk=plan["effective_risk"],
            output_path=str(out_path),
        )
    )
    return 0


def _handle_simulate(args: argparse.Namespace) -> int:
    plan = _load_json_object(Path(args.plan), label="plan")
    verification = verify_execution_plan(plan)
    if not verification.clean:
        _print_json(
            {
                "clean": False,
                "status": "deny",
                "reason_code": "plan_invalid",
                "issues": list(verification.issues),
                "plan_hash": verification.plan_hash,
            }
        )
        return 1

    receipt = simulate_plan(
        plan,
        audit_path=Path(args.audit) if args.audit is not None else None,
        snapshot_dir=Path(args.snapshot_dir) if args.snapshot_dir is not None else None,
    )
    _print_json(
        _success_payload(
            status="simulated",
            reason_code="simulation_finished",
            receipt_hash=receipt["receipt_hash"],
            plan_hash=receipt["plan_hash"],
            proposal_hash=receipt["proposal_hash"],
            executed=receipt["executed"],
            matched_binding_id=receipt["matched_binding_id"],
            effective_risk=receipt["effective_risk"],
            observed_writes=receipt["observed_writes"],
            powershell_invoked=receipt["powershell_invoked"],
            network_accessed=receipt["network_accessed"],
        )
    )
    return 0


def _handle_verify_log(args: argparse.Namespace) -> int:
    result = verify_log(Path(args.audit))
    _print_json(
        {
            "clean": result.clean,
            "status": "verified" if result.clean else "failed",
            "reason_code": "allowed" if result.clean else "log_verification_failed",
            "issues": list(result.issues),
            "event_count": result.event_count,
            "first_event_id": result.first_event_id,
            "last_event_id": result.last_event_id,
            "last_record_hash": result.last_record_hash,
        }
    )
    return 0 if result.clean else 1


def _handle_replay(args: argparse.Namespace) -> int:
    result = replay_session(Path(args.audit), args.session_id)
    _print_json(
        {
            "clean": result.clean,
            "status": "replayed" if result.clean else "failed",
            "reason_code": "allowed" if result.clean else "replay_failed",
            "issues": list(result.issues),
            "session_id": result.session_id,
            "event_count": result.event_count,
            "proposal_hashes": list(result.proposal_hashes),
            "policy_hashes": list(result.policy_hashes),
            "decision_codes": list(result.decision_codes),
            "latest_status": result.latest_status,
        }
    )
    return 0 if result.clean else 1


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="python -m app.governed_shell.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    propose_stub = subparsers.add_parser("propose-stub")
    propose_stub.add_argument("--intent", required=True)
    propose_stub.set_defaults(handler=_handle_propose_stub)

    policy_test = subparsers.add_parser("policy-test")
    policy_test.add_argument("--proposal", required=True)
    policy_test.set_defaults(handler=_handle_policy_test)

    review = subparsers.add_parser("review")
    review.add_argument("--proposal", required=True)
    review.add_argument("--audit")
    review.set_defaults(handler=_handle_review)

    approve = subparsers.add_parser("approve")
    approve.add_argument("--proposal", required=True)
    approve.add_argument("--proposal-hash")
    approve.add_argument("--out", required=True)
    approve.set_defaults(handler=_handle_approve)

    simulate = subparsers.add_parser("simulate")
    simulate.add_argument("--plan", required=True)
    simulate.add_argument("--audit")
    simulate.add_argument("--snapshot-dir", required=True)
    simulate.set_defaults(handler=_handle_simulate)

    verify_log_parser = subparsers.add_parser("verify-log")
    verify_log_parser.add_argument("--audit", required=True)
    verify_log_parser.set_defaults(handler=_handle_verify_log)

    replay = subparsers.add_parser("replay")
    replay.add_argument("--audit", required=True)
    replay.add_argument("--session-id", required=True)
    replay.set_defaults(handler=_handle_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except CliUsageError as exc:
        _print_json(_error_payload(reason_code="usage_error", issues=[str(exc)]))
        return 2
    except (
        ProposalSchemaError,
        ProposalNormalizationError,
        ProposalPathError,
        PolicyDeniedError,
        ConfirmationError,
        ExecutionPlanError,
        ReplayVerificationError,
    ) as exc:
        _print_json(_error_payload(reason_code="governed_failure", issues=[str(exc)], status="deny"))
        return 1
    except ProposalLoadError as exc:
        _print_json(_error_payload(reason_code="proposal_load_failed", issues=[str(exc)], status="deny"))
        return 1
    except GovernedShellError as exc:
        _print_json(_error_payload(reason_code="internal_error", issues=[str(exc)]))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
