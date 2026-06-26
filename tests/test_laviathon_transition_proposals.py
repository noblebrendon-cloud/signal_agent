from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.state_registry import get_state
from signal_agent.formal_governance import DecisionOutcome
from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger
from signal_agent.laviathon.schemas import TransitionProposal
from signal_agent.laviathon.transition_proposals import propose_transition


def _proposal(**overrides: object) -> TransitionProposal:
    payload: dict[str, object] = {
        "entity_id": "entity.alpha",
        "observed_state": "captured",
        "recommended_route": "admit",
        "evidence_ids": ["evidence.alpha"],
        "rationale": "The observation has enough evidence to be considered for admission.",
        "uncertainty_notes": "",
        "requires_human_review": False,
    }
    payload.update(overrides)
    return TransitionProposal.model_validate(payload)


def test_transition_proposal_invalid_route_fails_validation() -> None:
    with pytest.raises(ValidationError):
        _proposal(recommended_route="promote")


def test_transition_proposal_requires_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        _proposal(evidence_ids=[])


def test_transition_proposal_records_transition_proposed_event(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    proposal = _proposal()

    result = propose_transition(
        proposal,
        ledger_path=ledger_path,
        known_evidence_ids={"evidence.alpha"},
        timestamp="2026-06-23T00:00:00Z",
    )

    entries = read_ledger_entries(ledger_path)
    assert entries[0]["event_type"] == "transition_proposed"
    assert entries[0]["proposal"]["entity_id"] == "entity.alpha"
    assert result.proposed_event == entries[0]
    assert verify_ledger(ledger_path)["clean"] is True


def test_transition_proposal_alone_cannot_mutate_derived_state(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    registry_path = tmp_path / "artifact_registry.jsonl"
    proposal = _proposal()

    result = propose_transition(
        proposal,
        ledger_path=ledger_path,
        known_evidence_ids={"evidence.alpha"},
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.decision.decision is DecisionOutcome.REJECT_MISSING_AUTHORITY
    assert get_state("entity.alpha", registry_path=registry_path) is None
    assert not registry_path.exists()


def test_unknown_evidence_ids_are_routed_by_deterministic_policy(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    proposal = _proposal(evidence_ids=["evidence.unknown"])

    result = propose_transition(
        proposal,
        ledger_path=ledger_path,
        known_evidence_ids=set(),
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.decision.decision is DecisionOutcome.REJECT_MISSING_EVIDENCE
    assert result.decision.decision_reason == "missing_evidence"
