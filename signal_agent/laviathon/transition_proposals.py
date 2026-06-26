from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Mapping

from signal_agent.formal_governance import (
    ArtifactPocket,
    BranchVector,
    DecisionOutcome,
    Invariant,
    InvariantPath,
    PromotionDecision,
    RollbackPath,
    State,
    TransitionProposal as FormalTransitionProposal,
    UnresolvedTension,
    VariantPocket,
    append_canonical_ledger_entry,
    evaluate_transition,
)
from signal_agent.formal_governance.canonical_ledger import utc_timestamp
from signal_agent.formal_governance.hashing import canonical_json, short_hash, stable_hash
from signal_agent.formal_governance.ledger import LEDGER_SCHEMA_VERSION, LEDGER_ZERO_HASH, read_ledger_entries

from .schemas import TransitionProposal


LAVIATHON_PROPOSAL_INVARIANT_ID = "invariant.laviathon_transition_proposal_boundary"
LAVIATHON_PROPOSAL_PATH_ID = "laviathon.transition_proposal.v1"


@dataclass(frozen=True)
class TransitionProposalResult:
    proposal: TransitionProposal
    formal_proposal: FormalTransitionProposal
    proposed_event: dict[str, object]
    decision: PromotionDecision
    decision_entry: dict[str, object]


def _route_to_decision(route: str) -> DecisionOutcome:
    if route == "admit":
        return DecisionOutcome.PROMOTE_TO_STATE
    if route == "blocked_duplicate":
        return DecisionOutcome.BLOCK_DUPLICATE
    return DecisionOutcome.MANUAL_REVIEW_REQUIRED


def _route_to_state(route: str) -> str:
    if route == "admit":
        return "admitted"
    if route == "blocked_duplicate":
        return "blocked_duplicate"
    return "manual_review"


def _known_and_unknown_evidence(
    proposal: TransitionProposal,
    known_evidence_ids: Collection[str] | None,
) -> tuple[list[str], list[str]]:
    if known_evidence_ids is None:
        return (list(proposal.evidence_ids), [])
    known = set(known_evidence_ids)
    accepted = [evidence_id for evidence_id in proposal.evidence_ids if evidence_id in known]
    unknown = [evidence_id for evidence_id in proposal.evidence_ids if evidence_id not in known]
    return (accepted, unknown)


def formalize_laviathon_proposal(
    proposal: TransitionProposal,
    *,
    known_evidence_ids: Collection[str] | None = None,
) -> FormalTransitionProposal:
    accepted_evidence, unknown_evidence = _known_and_unknown_evidence(proposal, known_evidence_ids)
    proposed_state = _route_to_state(proposal.recommended_route)
    formal_proposal_id = f"laviathon.proposal.{short_hash(proposal.model_dump(mode='json'))}"
    artifact_ref = {
        "artifact_id": proposal.entity_id,
        "artifact_type": "laviathon_entity",
        "source_status": proposal.observed_state,
        "evidence_refs": list(proposal.evidence_ids),
    }

    tensions: list[UnresolvedTension] = []
    if unknown_evidence:
        tensions.append(
            UnresolvedTension(
                tension_id=f"unknown_evidence.{short_hash(unknown_evidence)}",
                description="Unknown evidence ids: " + ", ".join(unknown_evidence),
                blocking=True,
                severity="high",
            )
        )

    if proposal.requires_human_review:
        tensions.append(
            UnresolvedTension(
                tension_id=f"human_review_required.{short_hash(proposal.entity_id)}",
                description="Proposal explicitly requires human review before any state mutation.",
                blocking=True,
                severity="medium",
            )
        )

    return FormalTransitionProposal(
        proposal_id=formal_proposal_id,
        requested_decision=_route_to_decision(proposal.recommended_route).value,
        origin_state=State(
            state_id=proposal.observed_state,
            label=proposal.observed_state,
            kind="laviathon_lifecycle",
        ),
        proposed_state=State(
            state_id=proposed_state,
            label=proposed_state,
            kind="laviathon_lifecycle",
        ),
        root_invariant=Invariant(
            invariant_id=LAVIATHON_PROPOSAL_INVARIANT_ID,
            statement="Structured Laviathon transition proposals may recommend routes but cannot commit lifecycle state.",
            version="v1",
        ),
        invariant_path=InvariantPath(
            path_id=LAVIATHON_PROPOSAL_PATH_ID,
            root_invariant_id=LAVIATHON_PROPOSAL_INVARIANT_ID,
            state_sequence=[proposal.observed_state, proposed_state],
        ),
        branch_vector=BranchVector(
            branch_id=f"laviathon.{proposal.entity_id}.{proposal.recommended_route}",
            origin_state=proposal.observed_state,
            proposed_state=proposed_state,
            target_intent=proposal.recommended_route,
            root_branch_id=f"laviathon.{proposal.entity_id}",
            divergence_reason=proposal.rationale,
            invariant_path_id=LAVIATHON_PROPOSAL_PATH_ID,
            artifact_refs=[proposal.entity_id],
        ),
        artifact_pocket=ArtifactPocket(
            pocket_id=f"laviathon_artifacts.{proposal.entity_id}",
            admission_status=proposal.observed_state,
            artifact_refs=[artifact_ref],
        ),
        variant_pocket=VariantPocket(pocket_id=f"laviathon_variants.{proposal.entity_id}", variant_refs=[]),
        human_trigger=None,
        rollback_path=RollbackPath(
            rollback_id=f"rollback.laviathon.{proposal.entity_id}",
            strategy="append_only_proposal_reversal",
            path_ref=proposal.entity_id,
            not_required=True,
            reason="A Laviathon proposal is non-mutating and only records a recommendation for deterministic review.",
        ),
        unresolved_tensions=tensions,
        evidence_references=[
            {
                "evidence_id": evidence_id,
                "ref": evidence_id,
                "evidence_type": "laviathon_transition_proposal_evidence",
            }
            for evidence_id in accepted_evidence
        ],
        claim_assertions=[
            {
                "claim_id": f"laviathon.route.{proposal.entity_id}",
                "statement": proposal.rationale,
                "recommended_route": proposal.recommended_route,
            }
        ],
    )


def _record_hash(entry: dict[str, object]) -> str:
    payload = dict(entry)
    payload.pop("record_hash", None)
    return stable_hash(payload)


def append_transition_proposed_event(
    path: Path,
    *,
    proposal: TransitionProposal,
    generation_receipt: Mapping[str, object] | None = None,
    context_provenance: Mapping[str, object] | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_ledger_entries(ledger_path)
    previous_hash = str(existing[-1].get("record_hash", LEDGER_ZERO_HASH)) if existing else LEDGER_ZERO_HASH
    event_timestamp = timestamp or utc_timestamp()
    index = len(existing)
    proposal_payload = proposal.model_dump(mode="json")
    hash_material: object = proposal_payload
    if generation_receipt is not None or context_provenance is not None:
        hash_material = {
            "proposal": proposal_payload,
            "generation_receipt": None if generation_receipt is None else dict(generation_receipt),
            "context_provenance": None if context_provenance is None else dict(context_provenance),
        }

    payload: dict[str, object] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_entry_id": f"transition_proposed.{index:06d}.{short_hash({'timestamp': event_timestamp, 'proposal': proposal_payload, 'generation_receipt': generation_receipt, 'context_provenance': context_provenance})}",
        "event_type": "transition_proposed",
        "timestamp": event_timestamp,
        "proposal": proposal_payload,
        "content_hash": stable_hash(hash_material),
        "previous_hash": previous_hash,
    }
    if generation_receipt is not None:
        payload["generation_receipt"] = dict(generation_receipt)
    if context_provenance is not None:
        payload["context_provenance"] = dict(context_provenance)
    payload["record_hash"] = _record_hash(payload)

    with open(ledger_path, "a", encoding="utf-8") as handle:
        handle.write(canonical_json(payload) + "\n")

    return payload


def propose_transition(
    proposal: TransitionProposal,
    *,
    ledger_path: Path,
    known_evidence_ids: Collection[str] | None = None,
    generation_receipt: Mapping[str, object] | None = None,
    context_provenance: Mapping[str, object] | None = None,
    timestamp: str | None = None,
) -> TransitionProposalResult:
    proposed_event = append_transition_proposed_event(
        Path(ledger_path),
        proposal=proposal,
        generation_receipt=generation_receipt,
        context_provenance=context_provenance,
        timestamp=timestamp,
    )
    formal_proposal = formalize_laviathon_proposal(
        proposal,
        known_evidence_ids=known_evidence_ids,
    )
    decision = evaluate_transition(
        formal_proposal,
        prior_entries=read_ledger_entries(Path(ledger_path)),
    )
    decision_entry = append_canonical_ledger_entry(
        Path(ledger_path),
        proposal=formal_proposal,
        decision=decision,
        subsystem_refs=[
            {
                "subsystem": "laviathon",
                "ref_type": "transition_proposal",
                "event_type": "transition_proposed",
                "ledger_entry_id": str(proposed_event["ledger_entry_id"]),
            }
        ],
        timestamp=timestamp,
    )
    return TransitionProposalResult(
        proposal=proposal,
        formal_proposal=formal_proposal,
        proposed_event=proposed_event,
        decision=decision,
        decision_entry=decision_entry,
    )
