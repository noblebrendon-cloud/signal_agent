from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import AuditLogError
from .logstore import AuditVerificationResult, read_audit_events, verify_audit_chain


@dataclass(frozen=True)
class ReplayResult:
    clean: bool
    session_id: str
    event_count: int
    proposal_hashes: list[str]
    policy_hashes: list[str]
    decision_codes: list[str]
    latest_status: str | None
    issues: list[str]


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def summarize_review_chain(events: list[dict]) -> dict:
    """Summarize a session's review events into deterministic aggregates."""

    proposal_hashes = _unique_preserve_order(
        [str(event.get("proposal_hash")) for event in events if isinstance(event.get("proposal_hash"), str)]
    )
    policy_hashes = _unique_preserve_order(
        [str(event.get("policy_hash")) for event in events if isinstance(event.get("policy_hash"), str)]
    )
    decision_codes = _unique_preserve_order(
        [str(event.get("decision_code")) for event in events if isinstance(event.get("decision_code"), str)]
    )
    latest_status = None
    if events:
        latest_status_value = events[-1].get("status")
        latest_status = str(latest_status_value) if isinstance(latest_status_value, str) else None

    return {
        "event_count": len(events),
        "proposal_hashes": proposal_hashes,
        "policy_hashes": policy_hashes,
        "decision_codes": decision_codes,
        "latest_status": latest_status,
    }


def replay_session(path: Path, session_id: str) -> ReplayResult:
    """Replay a single session from a verified audit ledger."""

    verification = verify_audit_chain(path)
    if not verification.clean:
        return ReplayResult(
            clean=False,
            session_id=session_id,
            event_count=0,
            proposal_hashes=[],
            policy_hashes=[],
            decision_codes=[],
            latest_status=None,
            issues=list(verification.issues),
        )

    try:
        events = read_audit_events(path)
    except AuditLogError as exc:
        return ReplayResult(
            clean=False,
            session_id=session_id,
            event_count=0,
            proposal_hashes=[],
            policy_hashes=[],
            decision_codes=[],
            latest_status=None,
            issues=[str(exc)],
        )

    session_events = [
        event
        for event in events
        if isinstance(event.get("session_id"), str) and event.get("session_id") == session_id
    ]
    if not session_events:
        return ReplayResult(
            clean=False,
            session_id=session_id,
            event_count=0,
            proposal_hashes=[],
            policy_hashes=[],
            decision_codes=[],
            latest_status=None,
            issues=[f"session_not_found:{session_id}"],
        )

    summary = summarize_review_chain(session_events)
    return ReplayResult(
        clean=True,
        session_id=session_id,
        event_count=summary["event_count"],
        proposal_hashes=summary["proposal_hashes"],
        policy_hashes=summary["policy_hashes"],
        decision_codes=summary["decision_codes"],
        latest_status=summary["latest_status"],
        issues=[],
    )


def verify_log(path: Path) -> AuditVerificationResult:
    """Read-only verification wrapper for the governed-shell audit ledger."""

    return verify_audit_chain(path)
