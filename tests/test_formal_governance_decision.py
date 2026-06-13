from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.formal_governance import DecisionOutcome, TransitionProposal, evaluate_transition
from signal_agent.formal_governance.ledger import build_ledger_entry


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "formal_governance"
FIXED_TIMESTAMP = "2026-06-13T00:00:00Z"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _proposal(name: str) -> TransitionProposal:
    return TransitionProposal.from_fixture(_fixture(name))


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("valid_promotion.json", DecisionOutcome.PROMOTE_TO_STATE),
        ("missing_lineage.json", DecisionOutcome.REJECT_INVALID_LINEAGE),
        ("missing_invariant.json", DecisionOutcome.REJECT_MISSING_INVARIANT),
        ("raw_artifact_self_promotion.json", DecisionOutcome.REJECT_RAW_ARTIFACT_SELF_PROMOTION),
        ("unresolved_tension_blocking.json", DecisionOutcome.DEFER_UNRESOLVED_TENSION),
        ("missing_evidence.json", DecisionOutcome.REJECT_MISSING_EVIDENCE),
        ("missing_human_authority.json", DecisionOutcome.REJECT_MISSING_AUTHORITY),
        ("generator_self_certification.json", DecisionOutcome.REJECT_SELF_CERTIFICATION),
        ("rollback_required_missing.json", DecisionOutcome.REJECT_MISSING_ROLLBACK),
    ],
)
def test_fixture_decision_outcomes_without_prior_ledger(
    fixture_name: str,
    expected: DecisionOutcome,
) -> None:
    proposal = _proposal(fixture_name)

    decision = evaluate_transition(proposal)

    assert decision.decision is expected
    assert decision.deterministic_decision_id.startswith("sha256:")
    assert decision.gate_results
    if expected is DecisionOutcome.PROMOTE_TO_STATE:
        assert all(not gate.is_blocking() for gate in decision.gate_results)
    else:
        assert decision.gate_results[-1].outcome is expected


def test_duplicate_transition_is_blocked_after_prior_promoted_decision() -> None:
    valid = _proposal("valid_promotion.json")
    valid_decision = evaluate_transition(valid)
    prior_entry = build_ledger_entry(
        proposal=valid,
        decision=valid_decision,
        timestamp=FIXED_TIMESTAMP,
        index=0,
        previous_hash="sha256:" + ("0" * 64),
    ).to_dict()
    duplicate = _proposal("duplicate_transition.json")

    duplicate_decision = evaluate_transition(duplicate, prior_entries=[prior_entry])

    assert duplicate_decision.decision is DecisionOutcome.BLOCK_DUPLICATE
    assert duplicate_decision.deterministic_decision_id == valid_decision.deterministic_decision_id
    assert duplicate_decision.gate_results[-1].reason_code == "duplicate_promoted_transition"


def test_nonblocking_tension_is_carried_but_does_not_defer_valid_promotion() -> None:
    proposal = _proposal("valid_promotion.json")

    decision = evaluate_transition(proposal)

    assert proposal.unresolved_tensions[0].blocking is False
    assert decision.decision is DecisionOutcome.PROMOTE_TO_STATE
    assert any(gate.gate_name == "unresolved_tension_gate" for gate in decision.gate_results)

