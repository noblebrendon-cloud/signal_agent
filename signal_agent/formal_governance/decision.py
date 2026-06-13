from __future__ import annotations

from typing import Iterable

from .gates import (
    artifact_promotion_gate,
    branch_vector_gate,
    duplicate_gate,
    evidence_gate,
    human_authority_gate,
    invariant_gate,
    lineage_gate,
    rollback_gate,
    unresolved_tension_gate,
)
from .hashing import stable_hash
from .models import DecisionOutcome, GateResult, PromotionDecision, TransitionProposal


def _transition_identity_material(proposal: TransitionProposal) -> dict:
    branch = proposal.branch_vector
    return {
        "schema_version": "formal_transition_identity.v1",
        "requested_decision": proposal.requested_decision,
        "origin_state": proposal.origin_state.state_id,
        "proposed_state": proposal.proposed_state.state_id,
        "root_invariant_id": proposal.root_invariant.invariant_id,
        "invariant_path_id": proposal.invariant_path.path_id,
        "branch_id": branch.branch_id,
        "parent_branch_id": branch.parent_branch_id,
        "root_branch_id": branch.root_branch_id,
        "artifact_refs": sorted(proposal.artifact_pocket.artifact_ids()),
        "variant_refs": sorted(proposal.variant_pocket.variant_ids()),
    }


def deterministic_transition_id(proposal: TransitionProposal) -> str:
    """Stable transition identity, intentionally independent of timestamp."""

    return stable_hash(_transition_identity_material(proposal))


def _requested_outcome(proposal: TransitionProposal) -> DecisionOutcome:
    try:
        return DecisionOutcome(proposal.requested_decision)
    except ValueError:
        return DecisionOutcome.MANUAL_REVIEW_REQUIRED


def _decision_from_gate(
    proposal: TransitionProposal,
    deterministic_decision_id: str,
    gate_results: list[GateResult],
) -> PromotionDecision | None:
    latest = gate_results[-1]
    if not latest.is_blocking():
        return None

    outcome = latest.outcome or DecisionOutcome.MANUAL_REVIEW_REQUIRED
    return PromotionDecision(
        deterministic_decision_id=deterministic_decision_id,
        decision=outcome,
        decision_reason=latest.reason_code,
        gate_results=list(gate_results),
        proposal_id=proposal.proposal_id,
    )


def evaluate_transition(
    proposal: TransitionProposal,
    *,
    prior_entries: Iterable[dict] | None = None,
) -> PromotionDecision:
    """Evaluate a formal transition proposal through the V0 proof gates."""

    existing_entries = list(prior_entries or [])
    deterministic_id = deterministic_transition_id(proposal)
    gate_results: list[GateResult] = []

    for gate in (
        lineage_gate,
        invariant_gate,
        branch_vector_gate,
        artifact_promotion_gate,
        evidence_gate,
        unresolved_tension_gate,
        human_authority_gate,
        rollback_gate,
    ):
        gate_results.append(gate(proposal))
        blocked = _decision_from_gate(proposal, deterministic_id, gate_results)
        if blocked is not None:
            return blocked

    gate_results.append(duplicate_gate(proposal, deterministic_id, existing_entries))
    blocked = _decision_from_gate(proposal, deterministic_id, gate_results)
    if blocked is not None:
        return blocked

    requested = _requested_outcome(proposal)
    reason = "all_gates_passed"
    if requested is DecisionOutcome.MANUAL_REVIEW_REQUIRED:
        reason = "unrecognized_requested_decision"

    return PromotionDecision(
        deterministic_decision_id=deterministic_id,
        decision=requested,
        decision_reason=reason,
        gate_results=gate_results,
        proposal_id=proposal.proposal_id,
    )

