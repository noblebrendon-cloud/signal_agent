from __future__ import annotations

import json
from pathlib import Path

from signal_agent.formal_governance import TransitionProposal, evaluate_transition
from signal_agent.formal_governance.ledger import (
    LEDGER_ZERO_HASH,
    append_ledger_entry,
    read_ledger_entries,
    verify_ledger,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "formal_governance"


def _proposal(name: str) -> TransitionProposal:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return TransitionProposal.from_fixture(payload)


def test_ledger_entry_contains_required_formal_proof_fields(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    proposal = _proposal("valid_promotion.json")
    decision = evaluate_transition(proposal)

    entry = append_ledger_entry(
        ledger_path,
        proposal=proposal,
        decision=decision,
        timestamp="2026-06-13T00:00:00Z",
    )

    required = {
        "schema_version",
        "ledger_entry_id",
        "deterministic_decision_id",
        "timestamp",
        "origin_state",
        "proposed_state",
        "root_invariant",
        "invariant_path",
        "branch_vector",
        "artifact_references",
        "variant_references",
        "gate_results",
        "decision",
        "decision_reason",
        "human_authority_status",
        "unresolved_tensions",
        "rollback_path",
        "evidence_references",
        "content_hash",
        "previous_hash",
        "record_hash",
    }

    assert required <= set(entry)
    assert entry["previous_hash"] == LEDGER_ZERO_HASH
    assert entry["decision"] == "PROMOTE_TO_STATE"
    assert entry["human_authority_status"]["approved"] is True
    assert entry["content_hash"].startswith("sha256:")
    assert entry["record_hash"].startswith("sha256:")


def test_ledger_hash_chain_links_subsequent_entries(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    first = _proposal("valid_promotion.json")
    first_decision = evaluate_transition(first)
    first_entry = append_ledger_entry(
        ledger_path,
        proposal=first,
        decision=first_decision,
        timestamp="2026-06-13T00:00:00Z",
    )
    second = _proposal("missing_evidence.json")
    second_decision = evaluate_transition(second)
    second_entry = append_ledger_entry(
        ledger_path,
        proposal=second,
        decision=second_decision,
        timestamp="2026-06-13T00:00:01Z",
    )

    entries = read_ledger_entries(ledger_path)
    verification = verify_ledger(ledger_path)

    assert len(entries) == 2
    assert second_entry["previous_hash"] == first_entry["record_hash"]
    assert verification["clean"] is True
    assert verification["entry_count"] == 2


def test_deterministic_decision_id_is_separate_from_timestamped_ledger_entry_id(
    tmp_path: Path,
) -> None:
    proposal = _proposal("valid_promotion.json")
    decision_a = evaluate_transition(proposal)
    decision_b = evaluate_transition(proposal)
    ledger_a = tmp_path / "a.jsonl"
    ledger_b = tmp_path / "b.jsonl"

    entry_a = append_ledger_entry(
        ledger_a,
        proposal=proposal,
        decision=decision_a,
        timestamp="2026-06-13T00:00:00Z",
    )
    entry_b = append_ledger_entry(
        ledger_b,
        proposal=proposal,
        decision=decision_b,
        timestamp="2026-06-13T00:00:01Z",
    )

    assert decision_a.deterministic_decision_id == decision_b.deterministic_decision_id
    assert entry_a["deterministic_decision_id"] == entry_b["deterministic_decision_id"]
    assert entry_a["ledger_entry_id"] != entry_b["ledger_entry_id"]

