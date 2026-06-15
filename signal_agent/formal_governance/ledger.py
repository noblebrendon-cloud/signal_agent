from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import canonical_json, short_hash, stable_hash
from .models import LedgerEntry, PromotionDecision, TransitionProposal


LEDGER_ZERO_HASH = f"sha256:{'0' * 64}"
LEDGER_SCHEMA_VERSION = "governed_transition_ledger_entry.v1"


def read_ledger_entries(path: Path) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with open(ledger_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed ledger JSONL at line {line_number}: {exc.msg}") from exc
            if type(payload) is not dict:
                raise ValueError(f"Ledger record at line {line_number} is not an object.")
            entries.append(payload)
    return entries


def _record_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("record_hash", None)
    return stable_hash(payload)


def _entry_id(*, timestamp: str, index: int, deterministic_decision_id: str) -> str:
    suffix = short_hash(
        {
            "timestamp": timestamp,
            "index": index,
            "deterministic_decision_id": deterministic_decision_id,
        }
    )
    return f"ledger_entry.{index:06d}.{suffix}"


def _human_authority_status(proposal: TransitionProposal) -> dict[str, Any]:
    trigger = proposal.human_trigger
    if trigger is None:
        return {"present": False, "approved": False, "actor_type": "", "role": "", "scope": ""}
    return {
        "present": True,
        "approved": trigger.is_approved_human(),
        "actor_type": trigger.actor_type,
        "role": trigger.role,
        "scope": trigger.scope,
        "approval_status": trigger.approval_status,
        "self_certified": trigger.is_self_certifying(),
        "timestamp": trigger.timestamp,
    }


def build_ledger_entry(
    *,
    proposal: TransitionProposal,
    decision: PromotionDecision,
    timestamp: str,
    index: int,
    previous_hash: str,
    subsystem_refs: list[dict[str, Any]] | None = None,
) -> LedgerEntry:
    payload: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_entry_id": _entry_id(
            timestamp=timestamp,
            index=index,
            deterministic_decision_id=decision.deterministic_decision_id,
        ),
        "deterministic_decision_id": decision.deterministic_decision_id,
        "timestamp": timestamp,
        "origin_state": proposal.origin_state.to_dict(),
        "proposed_state": proposal.proposed_state.to_dict(),
        "root_invariant": proposal.root_invariant.to_dict(),
        "invariant_path": proposal.invariant_path.to_dict(),
        "branch_vector": proposal.branch_vector.to_dict(),
        "artifact_references": [dict(item) for item in proposal.artifact_pocket.artifact_refs],
        "variant_references": [dict(item) for item in proposal.variant_pocket.variant_refs],
        "gate_results": [gate.to_dict() for gate in decision.gate_results],
        "decision": decision.decision.value,
        "decision_reason": decision.decision_reason,
        "human_authority_status": _human_authority_status(proposal),
        "unresolved_tensions": [item.to_dict() for item in proposal.unresolved_tensions],
        "rollback_path": None if proposal.rollback_path is None else proposal.rollback_path.to_dict(),
        "evidence_references": [dict(item) for item in proposal.evidence_references],
        "subsystem_refs": [dict(item) for item in subsystem_refs or []],
        "content_hash": stable_hash(proposal.to_dict()),
        "previous_hash": previous_hash,
    }
    payload["record_hash"] = _record_hash(payload)
    return LedgerEntry(payload=payload)


def append_ledger_entry(
    path: Path,
    *,
    proposal: TransitionProposal,
    decision: PromotionDecision,
    timestamp: str,
    subsystem_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_ledger_entries(ledger_path)
    previous_hash = existing[-1].get("record_hash", LEDGER_ZERO_HASH) if existing else LEDGER_ZERO_HASH
    entry = build_ledger_entry(
        proposal=proposal,
        decision=decision,
        timestamp=timestamp,
        index=len(existing),
        previous_hash=previous_hash,
        subsystem_refs=subsystem_refs,
    ).to_dict()
    with open(ledger_path, "a", encoding="utf-8") as handle:
        handle.write(canonical_json(entry) + "\n")
    return entry


def verify_ledger(path: Path) -> dict[str, Any]:
    entries = read_ledger_entries(Path(path))
    issues: list[str] = []
    expected_previous = LEDGER_ZERO_HASH

    for index, entry in enumerate(entries):
        if entry.get("previous_hash") != expected_previous:
            issues.append(f"broken_previous_hash:{index}")
        expected_record_hash = _record_hash(entry)
        if entry.get("record_hash") != expected_record_hash:
            issues.append(f"record_hash_mismatch:{index}")
        expected_previous = str(entry.get("record_hash", expected_previous))

    return {
        "clean": not issues,
        "entry_count": len(entries),
        "issues": issues,
        "last_record_hash": expected_previous if entries else None,
    }
