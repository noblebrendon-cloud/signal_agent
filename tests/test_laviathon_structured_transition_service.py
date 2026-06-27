from __future__ import annotations

import socket
from pathlib import Path

import pytest

from shared.state_registry import get_state
from signal_agent.formal_governance import DecisionOutcome
from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger
from signal_agent.laviathon.schemas import TransitionProposal
from signal_agent.laviathon.structured_transition_service import (
    TransitionEvidence,
    TransitionGenerationContext,
    generate_and_propose_transition,
)
from signal_agent.structured_generation import FakeStructuredGenerator


class RecordingGenerator:
    def __init__(self, proposal: TransitionProposal) -> None:
        self._fake = FakeStructuredGenerator(proposal)
        self.prompt: str | None = None
        self.schema: type[TransitionProposal] | None = None

    def generate(
        self,
        prompt: str,
        schema: type[TransitionProposal],
        **_kwargs: object,
    ):
        self.prompt = prompt
        self.schema = schema
        return self._fake.generate(prompt, schema)


def _proposal(**overrides: object) -> TransitionProposal:
    payload: dict[str, object] = {
        "entity_id": "entity.alpha",
        "observed_state": "captured",
        "recommended_route": "admit",
        "evidence_ids": ["evidence.alpha"],
        "rationale": "The supplied evidence supports an admission proposal.",
        "uncertainty_notes": "The deterministic evaluator must still decide.",
        "requires_human_review": False,
    }
    payload.update(overrides)
    return TransitionProposal.model_validate(payload)


def _evidence() -> list[TransitionEvidence]:
    return [
        TransitionEvidence(
            evidence_id="evidence.alpha",
            summary="A bounded, trusted evidence summary supplied by the application.",
            source_type="laviathon_observation",
            observed_at="2026-06-23T00:00:00Z",
            association_method="explicit_entity_id",
            source_artifact_id="artifact.alpha",
        )
    ]


def _context() -> TransitionGenerationContext:
    return TransitionGenerationContext(
        entity_id="entity.alpha",
        current_state="captured",
        evidence=tuple(_evidence()),
        context_timestamp="2026-06-23T00:00:00Z",
        source_event_ids=("event.alpha",),
        source_observation_ids=("evidence.alpha",),
        association_methods=("explicit_entity_id",),
        source_artifact_ids=("artifact.alpha",),
    )


def _context_with_evidence(evidence: tuple[TransitionEvidence, ...]) -> TransitionGenerationContext:
    return TransitionGenerationContext(
        entity_id="entity.alpha",
        current_state="captured",
        evidence=evidence,
        context_timestamp="2026-06-23T00:00:00Z",
        source_event_ids=tuple(f"event.{index}" for index, _item in enumerate(evidence)),
        source_observation_ids=tuple(item.evidence_id for item in evidence),
        association_methods=tuple("explicit_entity_id" for _item in evidence),
        source_artifact_ids=tuple("" for _item in evidence),
    )


def test_service_passes_transition_proposal_schema_to_injected_generator(tmp_path: Path) -> None:
    generator = RecordingGenerator(_proposal())

    result = generate_and_propose_transition(
        generator=generator,
        context=_context(),
        ledger_path=tmp_path / "ledger.jsonl",
        timestamp="2026-06-23T00:00:00Z",
    )

    assert generator.schema is TransitionProposal
    assert generator.prompt is not None
    assert "entity.alpha" in generator.prompt
    assert "evidence.alpha" in generator.prompt
    assert "Use evidence_ids only from the supplied evidence list." in generator.prompt
    assert result.proposal == _proposal()


def test_service_records_generated_proposal_through_existing_ledger_path(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"

    result = generate_and_propose_transition(
        generator=RecordingGenerator(_proposal()),
        context=_context(),
        ledger_path=ledger_path,
        timestamp="2026-06-23T00:00:00Z",
    )

    entries = read_ledger_entries(ledger_path)
    assert entries[0]["event_type"] == "transition_proposed"
    assert entries[0]["proposal"] == result.proposal.model_dump(mode="json")
    assert entries[0]["generation_receipt"] == {
        "provider": "fake",
        "model": "fake",
        "schema_name": "TransitionProposal",
        "timestamp": result.generation_receipt.timestamp.isoformat(),
    }
    assert entries[0]["context_provenance"] == {
        "entity_id": "entity.alpha",
        "context_timestamp": "2026-06-23T00:00:00Z",
        "source_event_ids": ["event.alpha"],
        "source_observation_ids": ["evidence.alpha"],
        "association_methods": ["explicit_entity_id"],
        "source_artifact_ids": ["artifact.alpha"],
    }
    assert result.proposal_event == entries[0]
    assert verify_ledger(ledger_path)["clean"] is True


def test_deterministic_evaluator_not_generated_route_controls_disposition(tmp_path: Path) -> None:
    result = generate_and_propose_transition(
        generator=RecordingGenerator(_proposal(recommended_route="admit")),
        context=_context(),
        ledger_path=tmp_path / "ledger.jsonl",
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.proposal.recommended_route == "admit"
    assert result.deterministic_disposition.decision is DecisionOutcome.REJECT_MISSING_AUTHORITY
    assert result.deterministic_disposition.decision_reason == "missing_human_trigger"


def test_blocked_duplicate_route_is_still_deterministic_disposition(tmp_path: Path) -> None:
    result = generate_and_propose_transition(
        generator=RecordingGenerator(_proposal(recommended_route="blocked_duplicate")),
        context=_context(),
        ledger_path=tmp_path / "ledger.jsonl",
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.proposal.recommended_route == "blocked_duplicate"
    assert result.deterministic_disposition.decision is DecisionOutcome.BLOCK_DUPLICATE
    assert result.proposal_event["event_type"] == "transition_proposed"


def test_unknown_generated_evidence_cannot_create_final_state_change(tmp_path: Path) -> None:
    ledger_path = tmp_path / "governed_transition_ledger.jsonl"
    registry_path = tmp_path / "artifact_registry.jsonl"

    result = generate_and_propose_transition(
        generator=RecordingGenerator(_proposal(evidence_ids=["evidence.fabricated"])),
        context=_context(),
        ledger_path=ledger_path,
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.proposal.evidence_ids == ["evidence.fabricated"]
    assert result.deterministic_disposition.decision is DecisionOutcome.REJECT_MISSING_EVIDENCE
    assert get_state("entity.alpha", registry_path=registry_path) is None
    assert not registry_path.exists()


def test_service_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = generate_and_propose_transition(
        generator=RecordingGenerator(_proposal(recommended_route="manual_review")),
        context=_context(),
        ledger_path=tmp_path / "ledger.jsonl",
        timestamp="2026-06-23T00:00:00Z",
    )

    assert result.generation_receipt.provider == "fake"
    assert result.deterministic_disposition.decision is DecisionOutcome.MANUAL_REVIEW_REQUIRED


def test_service_rejects_excess_evidence_before_generator_invocation(tmp_path: Path) -> None:
    generator = RecordingGenerator(_proposal())
    evidence = tuple(
        TransitionEvidence(
            evidence_id=f"evidence.{index}",
            summary="bounded evidence",
            observed_at="2026-06-23T00:00:00Z",
            association_method="explicit_entity_id",
        )
        for index in range(21)
    )

    with pytest.raises(ValueError, match="too_many_evidence_items"):
        generate_and_propose_transition(
            generator=generator,
            context=_context_with_evidence(evidence),
            ledger_path=tmp_path / "ledger.jsonl",
            timestamp="2026-06-23T00:00:00Z",
        )

    assert generator.prompt is None


def test_service_rejects_excess_evidence_summary_before_generator_invocation(tmp_path: Path) -> None:
    generator = RecordingGenerator(_proposal())
    evidence = (
        TransitionEvidence(
            evidence_id="evidence.alpha",
            summary="x" * 501,
            observed_at="2026-06-23T00:00:00Z",
            association_method="explicit_entity_id",
        ),
    )

    with pytest.raises(ValueError, match="evidence_summary_too_long"):
        generate_and_propose_transition(
            generator=generator,
            context=_context_with_evidence(evidence),
            ledger_path=tmp_path / "ledger.jsonl",
            timestamp="2026-06-23T00:00:00Z",
        )

    assert generator.prompt is None
