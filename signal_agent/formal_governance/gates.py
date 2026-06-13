from __future__ import annotations

from .models import DecisionOutcome, GateResult, GateStatus, TransitionProposal


def _pass(gate_name: str, reason_code: str = "passed") -> GateResult:
    return GateResult(
        gate_name=gate_name,
        status=GateStatus.PASS,
        reason_code=reason_code,
        message=f"{gate_name} passed.",
    )


def lineage_gate(proposal: TransitionProposal) -> GateResult:
    missing: list[str] = []
    if not proposal.origin_state.state_id:
        missing.append("origin_state")
    if not proposal.proposed_state.state_id:
        missing.append("proposed_state")
    if not proposal.branch_vector.branch_id:
        missing.append("branch_id")
    if not proposal.branch_vector.has_parent_or_root():
        missing.append("parent_or_root_lineage")

    if missing:
        return GateResult(
            gate_name="lineage_gate",
            status=GateStatus.FAIL,
            reason_code="missing_lineage",
            message="Missing lineage fields: " + ", ".join(missing),
            outcome=DecisionOutcome.REJECT_INVALID_LINEAGE,
        )
    return _pass("lineage_gate")


def invariant_gate(proposal: TransitionProposal) -> GateResult:
    if not proposal.root_invariant.invariant_id:
        return GateResult(
            gate_name="invariant_gate",
            status=GateStatus.FAIL,
            reason_code="missing_root_invariant",
            message="Transition proposal does not include a root invariant id.",
            outcome=DecisionOutcome.REJECT_MISSING_INVARIANT,
        )
    if not proposal.invariant_path.path_id or not proposal.invariant_path.binds(proposal.root_invariant):
        return GateResult(
            gate_name="invariant_gate",
            status=GateStatus.FAIL,
            reason_code="missing_invariant_path_binding",
            message="Invariant path is missing or does not bind to the root invariant.",
            outcome=DecisionOutcome.REJECT_MISSING_INVARIANT,
        )
    return _pass("invariant_gate")


def branch_vector_gate(proposal: TransitionProposal) -> GateResult:
    missing: list[str] = []
    branch = proposal.branch_vector
    if branch.origin_state != proposal.origin_state.state_id:
        missing.append("branch_origin_state_binding")
    if branch.proposed_state != proposal.proposed_state.state_id and not branch.target_intent:
        missing.append("target_state_or_intent")
    if not branch.divergence_reason:
        missing.append("divergence_reason")
    if branch.invariant_path_id != proposal.invariant_path.path_id:
        missing.append("invariant_path_id")
    if proposal.artifact_pocket.artifact_refs and not branch.artifact_refs:
        missing.append("artifact_refs")
    if proposal.variant_pocket.variant_refs and not branch.variant_refs:
        missing.append("variant_refs")

    if missing:
        return GateResult(
            gate_name="branch_vector_gate",
            status=GateStatus.FAIL,
            reason_code="invalid_branch_vector",
            message="Invalid branch vector fields: " + ", ".join(missing),
            outcome=DecisionOutcome.REJECT_INVALID_LINEAGE,
        )
    return _pass("branch_vector_gate")


def artifact_promotion_gate(proposal: TransitionProposal) -> GateResult:
    if proposal.is_state_promotion() and proposal.artifact_pocket.has_raw_artifacts():
        return GateResult(
            gate_name="artifact_promotion_gate",
            status=GateStatus.FAIL,
            reason_code="raw_artifact_self_promotion",
            message="Raw artifacts may be admitted, but may not directly promote to state.",
            outcome=DecisionOutcome.REJECT_RAW_ARTIFACT_SELF_PROMOTION,
        )
    return _pass("artifact_promotion_gate")


def evidence_gate(proposal: TransitionProposal) -> GateResult:
    requires_evidence = proposal.is_state_promotion() or bool(proposal.claim_assertions)
    if requires_evidence and not proposal.evidence_references:
        return GateResult(
            gate_name="evidence_gate",
            status=GateStatus.FAIL,
            reason_code="missing_evidence",
            message="Claims and promotion-supporting assertions require evidence references.",
            outcome=DecisionOutcome.REJECT_MISSING_EVIDENCE,
        )
    return _pass("evidence_gate")


def unresolved_tension_gate(proposal: TransitionProposal) -> GateResult:
    blocking = [item.tension_id for item in proposal.unresolved_tensions if item.blocking]
    if proposal.is_state_promotion() and blocking:
        return GateResult(
            gate_name="unresolved_tension_gate",
            status=GateStatus.DEFER,
            reason_code="blocking_unresolved_tension",
            message="Blocking unresolved tensions defer promotion: " + ", ".join(blocking),
            outcome=DecisionOutcome.DEFER_UNRESOLVED_TENSION,
        )
    return _pass("unresolved_tension_gate")


def human_authority_gate(proposal: TransitionProposal) -> GateResult:
    if not proposal.is_state_promotion():
        return _pass("human_authority_gate", reason_code="not_state_mutating")

    trigger = proposal.human_trigger
    if trigger is None:
        return GateResult(
            gate_name="human_authority_gate",
            status=GateStatus.FAIL,
            reason_code="missing_human_trigger",
            message="Promotion to state requires an approved human trigger.",
            outcome=DecisionOutcome.REJECT_MISSING_AUTHORITY,
        )
    if trigger.is_self_certifying():
        return GateResult(
            gate_name="human_authority_gate",
            status=GateStatus.FAIL,
            reason_code="self_certification",
            message="Generator or self-certified approval cannot satisfy human authority.",
            outcome=DecisionOutcome.REJECT_SELF_CERTIFICATION,
        )
    if not trigger.is_approved_human():
        return GateResult(
            gate_name="human_authority_gate",
            status=GateStatus.FAIL,
            reason_code="missing_authority",
            message="Human trigger is not approved or lacks role, scope, or timestamp.",
            outcome=DecisionOutcome.REJECT_MISSING_AUTHORITY,
        )
    return _pass("human_authority_gate")


def rollback_gate(proposal: TransitionProposal) -> GateResult:
    if not proposal.is_state_promotion():
        return _pass("rollback_gate", reason_code="not_state_mutating")

    if proposal.rollback_path is None or not proposal.rollback_path.satisfies_state_mutation():
        return GateResult(
            gate_name="rollback_gate",
            status=GateStatus.FAIL,
            reason_code="missing_rollback",
            message="State-mutating promotion requires a rollback path or a justified exemption.",
            outcome=DecisionOutcome.REJECT_MISSING_ROLLBACK,
        )
    return _pass("rollback_gate")


def duplicate_gate(
    proposal: TransitionProposal,
    deterministic_decision_id: str,
    prior_entries: list[dict],
) -> GateResult:
    if not proposal.is_state_promotion():
        return _pass("duplicate_gate", reason_code="not_state_mutating")

    for entry in prior_entries:
        if (
            entry.get("deterministic_decision_id") == deterministic_decision_id
            and entry.get("decision") == DecisionOutcome.PROMOTE_TO_STATE.value
        ):
            return GateResult(
                gate_name="duplicate_gate",
                status=GateStatus.BLOCK,
                reason_code="duplicate_promoted_transition",
                message="A promoted decision with the same deterministic transition identity already exists.",
                outcome=DecisionOutcome.BLOCK_DUPLICATE,
            )
    return _pass("duplicate_gate")

