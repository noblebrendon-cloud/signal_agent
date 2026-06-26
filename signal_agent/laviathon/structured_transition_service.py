from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from signal_agent.formal_governance import PromotionDecision
from signal_agent.structured_generation import GenerationReceipt, StructuredGenerationError, StructuredGenerator

from .schemas import TransitionProposal
from .transition_context import (
    MAX_EVIDENCE_ITEMS,
    MAX_EVIDENCE_SUMMARY_CHARS,
    MAX_TEXT_CHARS,
    TransitionEvidence,
    TransitionGenerationContext,
    context_provenance,
)
from .transition_proposals import propose_transition


ALLOWED_ROUTES = ("admit", "blocked_duplicate", "manual_review")


@dataclass(frozen=True)
class StructuredTransitionResult:
    proposal: TransitionProposal
    generation_receipt: GenerationReceipt
    proposal_event: dict[str, object]
    deterministic_disposition: PromotionDecision


class StructuredTransitionServiceError(ValueError):
    """Raised when trusted inputs or generated proposal identity fail validation."""


def generate_and_propose_transition(
    *,
    generator: StructuredGenerator,
    context: TransitionGenerationContext,
    ledger_path: Path,
    timestamp: str | None = None,
) -> StructuredTransitionResult:
    prompt = build_transition_prompt(context=context)
    generated = generator.generate(prompt, TransitionProposal)
    proposal = generated.value
    _validate_generated_identity(
        proposal,
        entity_id=context.entity_id,
        current_state=context.current_state,
    )

    transition_result = propose_transition(
        proposal,
        ledger_path=ledger_path,
        known_evidence_ids=[item.evidence_id for item in context.evidence],
        generation_receipt=_receipt_metadata(generated.receipt),
        context_provenance=context_provenance(context),
        timestamp=timestamp,
    )
    return StructuredTransitionResult(
        proposal=proposal,
        generation_receipt=generated.receipt,
        proposal_event=transition_result.proposed_event,
        deterministic_disposition=transition_result.decision,
    )


def build_transition_prompt(
    *,
    context: TransitionGenerationContext,
) -> str:
    trusted_entity_id = _required_text("entity_id", context.entity_id, MAX_TEXT_CHARS)
    trusted_state = _required_text("current_state", context.current_state, MAX_TEXT_CHARS)
    trusted_timestamp = _required_text("context_timestamp", context.context_timestamp, MAX_TEXT_CHARS)
    trusted_evidence = _bounded_evidence(context.evidence)

    prompt_payload = {
        "entity_id": trusted_entity_id,
        "current_state": trusted_state,
        "context_timestamp": trusted_timestamp,
        "allowed_routes": list(ALLOWED_ROUTES),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "summary": item.summary,
                "source_type": item.source_type,
                "observed_at": item.observed_at,
                "association_method": item.association_method,
                "source_artifact_id": item.source_artifact_id,
            }
            for item in trusted_evidence
        ],
        "source_event_ids": _bounded_ids("source_event_id", context.source_event_ids),
        "source_observation_ids": _bounded_ids("source_observation_id", context.source_observation_ids),
        "association_methods": _bounded_ids("association_method", context.association_methods),
        "source_artifact_ids": _bounded_optional_ids("source_artifact_id", context.source_artifact_ids),
    }
    return "\n".join(
        (
            "Generate a validated Laviathon TransitionProposal.",
            "The output is a proposal only, not a command or final decision.",
            "The system will independently validate evidence and final disposition.",
            "Use only these recommended_route values: admit, blocked_duplicate, manual_review.",
            "Use evidence_ids only from the supplied evidence list.",
            "State uncertainty rather than inventing facts.",
            "Do not include secrets, full ledgers, unrelated documents, hidden policy text, or external context.",
            json.dumps(prompt_payload, ensure_ascii=True, sort_keys=True),
        )
    )


def _receipt_metadata(receipt: GenerationReceipt) -> dict[str, str]:
    return {
        "provider": receipt.provider,
        "model": receipt.model,
        "schema_name": receipt.schema_name,
        "timestamp": receipt.timestamp.isoformat(),
    }


def _validate_generated_identity(
    proposal: TransitionProposal,
    *,
    entity_id: str,
    current_state: str,
) -> None:
    if proposal.entity_id != entity_id:
        raise StructuredGenerationError("Generated proposal entity_id does not match trusted input.")
    if proposal.observed_state != current_state:
        raise StructuredGenerationError("Generated proposal observed_state does not match trusted input.")


def _bounded_evidence(evidence: Sequence[TransitionEvidence]) -> list[TransitionEvidence]:
    if not evidence:
        raise StructuredTransitionServiceError("missing_evidence")
    if len(evidence) > MAX_EVIDENCE_ITEMS:
        raise StructuredTransitionServiceError("too_many_evidence_items")

    bounded: list[TransitionEvidence] = []
    seen: set[str] = set()
    for item in evidence:
        evidence_id = _required_text("evidence_id", item.evidence_id, MAX_TEXT_CHARS)
        if evidence_id in seen:
            raise StructuredTransitionServiceError(f"duplicate_evidence_id:{evidence_id}")
        seen.add(evidence_id)
        bounded.append(
            TransitionEvidence(
                evidence_id=evidence_id,
                summary=_bounded_text("evidence_summary", item.summary, MAX_EVIDENCE_SUMMARY_CHARS),
                source_type=_required_text("evidence_source_type", item.source_type, MAX_TEXT_CHARS),
                observed_at=_required_text("evidence_observed_at", item.observed_at, MAX_TEXT_CHARS),
                association_method=_required_text(
                    "evidence_association_method",
                    item.association_method,
                    MAX_TEXT_CHARS,
                ),
                source_artifact_id=_bounded_optional_text(
                    "evidence_source_artifact_id",
                    item.source_artifact_id,
                    MAX_TEXT_CHARS,
                ),
            )
        )
    return bounded


def _bounded_ids(field: str, values: Sequence[str]) -> list[str]:
    if len(values) > MAX_EVIDENCE_ITEMS:
        raise StructuredTransitionServiceError(f"too_many_{field}s")
    return [_required_text(field, value, MAX_TEXT_CHARS) for value in values]


def _bounded_optional_ids(field: str, values: Sequence[str]) -> list[str]:
    if len(values) > MAX_EVIDENCE_ITEMS:
        raise StructuredTransitionServiceError(f"too_many_{field}s")
    return [_bounded_optional_text(field, value, MAX_TEXT_CHARS) for value in values]


def _required_text(field: str, value: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise StructuredTransitionServiceError(f"invalid_{field}")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise StructuredTransitionServiceError(f"missing_{field}")
    if len(normalized) > max_chars:
        raise StructuredTransitionServiceError(f"{field}_too_long")
    return normalized


def _bounded_text(field: str, value: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise StructuredTransitionServiceError(f"invalid_{field}")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise StructuredTransitionServiceError(f"missing_{field}")
    return normalized[:max_chars]


def _bounded_optional_text(field: str, value: str, max_chars: int) -> str:
    if not value:
        return ""
    return _bounded_text(field, value, max_chars)
