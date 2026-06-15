from __future__ import annotations

from pathlib import Path
from typing import Any

from signal_agent.formal_governance.models import (
    DecisionOutcome,
    GateResult,
    GateStatus,
)

from .adapters import append_authoring_decision_entry, authoring_decision
from .models import (
    DraftCandidate,
    GovernedAuthoringResult,
    OutputManifest,
    ReviewDecision,
    SourcePacket,
)


def _gate(
    *,
    name: str,
    status: GateStatus,
    reason_code: str,
    message: str,
    outcome: DecisionOutcome | None = None,
) -> GateResult:
    return GateResult(
        gate_name=name,
        status=status,
        reason_code=reason_code,
        message=message,
        outcome=outcome,
    )


class GovernedAuthoringRuntime:
    """
    Narrow Governed Authoring backend proof path.

    The runtime is intentionally pure except for an optional canonical ledger
    append when canonical_ledger_path is provided.
    """

    def __init__(self, *, canonical_ledger_path: Path | None = None) -> None:
        self.canonical_ledger_path = Path(canonical_ledger_path) if canonical_ledger_path is not None else None

    def run(self, packet: SourcePacket | dict[str, Any]) -> GovernedAuthoringResult:
        source_packet = packet if isinstance(packet, SourcePacket) else SourcePacket.from_dict(packet)
        draft_candidate: DraftCandidate | None = None
        review_decision = source_packet.review_decision
        gate_results: list[GateResult] = []

        if not source_packet.has_source_material():
            gate_results.append(
                _gate(
                    name="source_packet_gate",
                    status=GateStatus.FAIL,
                    reason_code="missing_source_material",
                    message="Source packet does not include usable source material.",
                    outcome=DecisionOutcome.REJECT_MISSING_SOURCE,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=None,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="rejected",
                outcome=DecisionOutcome.REJECT_MISSING_SOURCE,
                reason="missing_source_material",
                messages=["Source material is required before authoring can proceed."],
            )

        gate_results.append(
            _gate(
                name="source_packet_gate",
                status=GateStatus.PASS,
                reason_code="source_packet_admitted",
                message="Source packet includes usable source material.",
                outcome=DecisionOutcome.ADMIT_SOURCE_PACKET,
            )
        )
        draft_candidate = DraftCandidate.from_source_packet(source_packet)

        if source_packet.is_provisional_request() and not source_packet.is_publication_ready_request():
            gate_results.append(
                _gate(
                    name="claim_evidence_gate",
                    status=GateStatus.PASS,
                    reason_code="provisional_unverified_draft_allowed",
                    message="Draft candidate may remain provisional or unverified without publication-ready evidence.",
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="provisional",
                outcome=DecisionOutcome.EMIT_PROVISIONAL_DRAFT,
                reason="provisional_unverified_draft_allowed",
                messages=["Output manifest is provisional and is not approved for publication."],
            )

        if not draft_candidate.evidence_refs:
            gate_results.append(
                _gate(
                    name="claim_evidence_gate",
                    status=GateStatus.FAIL,
                    reason_code="missing_evidence_refs",
                    message="Publication-ready Governed Authoring output requires evidence references.",
                    outcome=DecisionOutcome.REJECT_MISSING_EVIDENCE,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="rejected",
                outcome=DecisionOutcome.REJECT_MISSING_EVIDENCE,
                reason="missing_evidence_refs",
                messages=["Publication-ready output requires non-empty evidence_refs."],
            )

        gate_results.append(
            _gate(
                name="claim_evidence_gate",
                status=GateStatus.PASS,
                reason_code="evidence_refs_present",
                message="Draft candidate has evidence references.",
            )
        )

        blocking_tensions = [item.tension_id for item in source_packet.unresolved_tensions if item.blocking]
        if blocking_tensions:
            gate_results.append(
                _gate(
                    name="unresolved_tension_gate",
                    status=GateStatus.DEFER,
                    reason_code="blocking_unresolved_tension",
                    message="Blocking unresolved tensions defer approval: " + ", ".join(blocking_tensions),
                    outcome=DecisionOutcome.DEFER_UNRESOLVED_TENSION,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="deferred",
                outcome=DecisionOutcome.DEFER_UNRESOLVED_TENSION,
                reason="blocking_unresolved_tension",
                messages=["Blocking unresolved tensions must be resolved before approval."],
            )

        gate_results.append(
            _gate(
                name="unresolved_tension_gate",
                status=GateStatus.PASS,
                reason_code="no_blocking_unresolved_tension",
                message="No blocking unresolved tensions are present.",
            )
        )

        if review_decision is None:
            gate_results.append(
                _gate(
                    name="human_review_gate",
                    status=GateStatus.FAIL,
                    reason_code="missing_human_review",
                    message="Approved output requires an explicit human review decision.",
                    outcome=DecisionOutcome.REJECT_MISSING_HUMAN_REVIEW,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=None,
                gate_results=gate_results,
                output_status="rejected",
                outcome=DecisionOutcome.REJECT_MISSING_HUMAN_REVIEW,
                reason="missing_human_review",
                messages=["Approved output requires human review authority."],
            )

        if review_decision.is_self_approval():
            gate_results.append(
                _gate(
                    name="human_review_gate",
                    status=GateStatus.FAIL,
                    reason_code="generator_self_approval",
                    message="Generator, model, agent, or self-certified review cannot approve output.",
                    outcome=DecisionOutcome.REJECT_SELF_APPROVAL,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="rejected",
                outcome=DecisionOutcome.REJECT_SELF_APPROVAL,
                reason="generator_self_approval",
                messages=["Generated or self-certified approval cannot satisfy human authority."],
            )

        if not review_decision.is_approved_human():
            gate_results.append(
                _gate(
                    name="human_review_gate",
                    status=GateStatus.FAIL,
                    reason_code="human_review_not_approved",
                    message="Review decision is not an approved human review with role, scope, and timestamp.",
                    outcome=DecisionOutcome.REJECT_MISSING_HUMAN_REVIEW,
                )
            )
            return self._finish(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                gate_results=gate_results,
                output_status="rejected",
                outcome=DecisionOutcome.REJECT_MISSING_HUMAN_REVIEW,
                reason="human_review_not_approved",
                messages=["Review decision did not satisfy approved human authority."],
            )

        gate_results.append(
            _gate(
                name="human_review_gate",
                status=GateStatus.PASS,
                reason_code="approved_human_review_present",
                message="Approved human review authority is present.",
            )
        )
        gate_results.append(
            _gate(
                name="output_manifest_gate",
                status=GateStatus.PASS,
                reason_code="approved_output_ready",
                message="Output manifest can be marked approved.",
                outcome=DecisionOutcome.APPROVE_OUTPUT,
            )
        )
        return self._finish(
            source_packet=source_packet,
            draft_candidate=draft_candidate,
            review_decision=review_decision,
            gate_results=gate_results,
            output_status="approved",
            outcome=DecisionOutcome.APPROVE_OUTPUT,
            reason="approved_output_ready",
            messages=["Output manifest is approved by governed backend review."],
        )

    def _finish(
        self,
        *,
        source_packet: SourcePacket,
        draft_candidate: DraftCandidate | None,
        review_decision: ReviewDecision | None,
        gate_results: list[GateResult],
        output_status: str,
        outcome: DecisionOutcome,
        reason: str,
        messages: list[str],
    ) -> GovernedAuthoringResult:
        output_manifest = OutputManifest.build(
            source_packet=source_packet,
            draft_candidate=draft_candidate,
            review_decision=review_decision,
            output_status=output_status,
            decision=outcome.value,
            decision_reason=reason,
            messages=messages,
        )
        decision = authoring_decision(
            source_packet=source_packet,
            draft_candidate=draft_candidate,
            review_decision=review_decision,
            output_manifest=output_manifest,
            gate_results=gate_results,
        )
        ledger_entry = None
        if self.canonical_ledger_path is not None:
            ledger_entry = append_authoring_decision_entry(
                self.canonical_ledger_path,
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                output_manifest=output_manifest,
                decision=decision,
            )
            output_manifest = output_manifest.with_canonical_entry(str(ledger_entry["ledger_entry_id"]))

        return GovernedAuthoringResult(
            source_packet=source_packet,
            draft_candidate=draft_candidate,
            review_decision=review_decision,
            output_manifest=output_manifest,
            formal_decision=decision,
            canonical_ledger_entry=ledger_entry,
        )
