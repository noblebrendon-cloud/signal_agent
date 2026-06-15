from __future__ import annotations

from pathlib import Path
from typing import Any

from signal_agent.formal_governance.canonical_ledger import append_canonical_ledger_entry
from signal_agent.formal_governance.hashing import short_hash, stable_hash
from signal_agent.formal_governance.models import (
    ArchitectureNode,
    ArtifactPocket,
    BranchVector,
    ConsolidationPass,
    DecisionOutcome,
    GateResult,
    Invariant,
    InvariantArchitecture,
    InvariantPath,
    PromotionDecision,
    RollbackPath,
    State,
    TransitionProposal,
    UnresolvedTension,
    VariantPocket,
)

from .models import DraftCandidate, OutputManifest, ReviewDecision, SourcePacket


GOVERNED_AUTHORING_ROOT_INVARIANT_ID = "invariant.governed_authoring_backend_proof"
GOVERNED_AUTHORING_INVARIANT_PATH_ID = "governed_authoring.backend_proof.v1"


def _review_material(review_decision: ReviewDecision | None) -> dict[str, Any]:
    if review_decision is None:
        return {}
    return {
        "review_decision_id": review_decision.review_decision_id,
        "actor_type": review_decision.actor_type,
        "role": review_decision.role,
        "scope": review_decision.scope,
        "decision": review_decision.decision,
        "self_certified": review_decision.self_certified,
    }


def _decision_material(
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
) -> dict[str, Any]:
    return {
        "schema_version": "governed_authoring_decision.v1",
        "source_packet_id": source_packet.source_packet_id,
        "requested_output_status": source_packet.requested_output_status,
        "draft_mode": source_packet.draft_mode,
        "draft_candidate_id": draft_candidate.draft_candidate_id if draft_candidate else "",
        "review": _review_material(review_decision),
        "output_status": output_manifest.output_status,
        "decision": output_manifest.decision,
        "decision_reason": output_manifest.decision_reason,
        "claim_refs": sorted(output_manifest.claim_refs),
        "evidence_refs": sorted(output_manifest.evidence_refs),
        "tensions": sorted(
            [
                {
                    "tension_id": item.tension_id,
                    "blocking": item.blocking,
                    "severity": item.severity,
                }
                for item in output_manifest.unresolved_tensions
            ],
            key=lambda item: item["tension_id"],
        ),
    }


def authoring_decision(
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
    gate_results: list[GateResult],
) -> PromotionDecision:
    return PromotionDecision(
        deterministic_decision_id=stable_hash(
            _decision_material(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                output_manifest=output_manifest,
            )
        ),
        decision=DecisionOutcome(output_manifest.decision),
        decision_reason=output_manifest.decision_reason,
        gate_results=list(gate_results),
        proposal_id=output_manifest.output_manifest_id,
    )


def _artifact_references(
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
) -> list[dict[str, Any]]:
    refs = [
        {
            "artifact_id": source_packet.source_packet_id,
            "artifact_type": "governed_authoring_source_packet",
            "source_status": "received",
            "content_hash": stable_hash(source_packet.to_dict()),
        },
        {
            "artifact_id": output_manifest.output_manifest_id,
            "artifact_type": "governed_authoring_output_manifest",
            "source_status": output_manifest.output_status,
            "content_hash": stable_hash(output_manifest.to_dict()),
        },
    ]
    if draft_candidate is not None:
        refs.append(
            {
                "artifact_id": draft_candidate.draft_candidate_id,
                "artifact_type": "governed_authoring_draft_candidate",
                "source_status": draft_candidate.status,
                "content_hash": stable_hash(draft_candidate.to_dict()),
            }
        )
    if review_decision is not None:
        refs.append(
            {
                "artifact_id": review_decision.review_decision_id,
                "artifact_type": "governed_authoring_review_decision",
                "source_status": review_decision.decision,
                "content_hash": stable_hash(review_decision.to_dict()),
            }
        )
    return refs


def _evidence_references(output_manifest: OutputManifest) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": ref,
            "ref": ref,
            "evidence_type": "governed_authoring_claim_evidence",
        }
        for ref in output_manifest.evidence_refs
    ]


def _formal_tensions(output_manifest: OutputManifest) -> list[UnresolvedTension]:
    return [
        UnresolvedTension(
            tension_id=item.tension_id,
            description=item.description,
            blocking=item.blocking,
            severity=item.severity,
        )
        for item in output_manifest.unresolved_tensions
    ]


def authoring_transition_proposal(
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
    decision: PromotionDecision,
) -> TransitionProposal:
    origin_state = "governed_authoring.source_packet_received"
    if output_manifest.decision == DecisionOutcome.REJECT_MISSING_SOURCE.value:
        origin_state = "governed_authoring.source_missing"
    proposed_state = f"governed_authoring.{output_manifest.output_status}"
    artifact_ids = [
        source_packet.source_packet_id,
        output_manifest.output_manifest_id,
    ]
    if draft_candidate is not None:
        artifact_ids.append(draft_candidate.draft_candidate_id)
    if review_decision is not None:
        artifact_ids.append(review_decision.review_decision_id)

    return TransitionProposal(
        proposal_id=output_manifest.output_manifest_id,
        requested_decision=decision.decision.value,
        origin_state=State(
            state_id=origin_state,
            label=origin_state,
            kind="governed_authoring",
        ),
        proposed_state=State(
            state_id=proposed_state,
            label=output_manifest.output_status,
            kind="governed_authoring",
        ),
        root_invariant=Invariant(
            invariant_id=GOVERNED_AUTHORING_ROOT_INVARIANT_ID,
            statement=(
                "Governed Authoring outputs require source material, evidence-bearing claims, "
                "unresolved-tension handling, and human authority for approved output."
            ),
            version="v1",
        ),
        invariant_path=InvariantPath(
            path_id=GOVERNED_AUTHORING_INVARIANT_PATH_ID,
            root_invariant_id=GOVERNED_AUTHORING_ROOT_INVARIANT_ID,
            state_sequence=[origin_state, proposed_state],
        ),
        branch_vector=BranchVector(
            branch_id=(
                f"governed_authoring.{source_packet.source_packet_id}."
                f"{short_hash(_decision_material(source_packet=source_packet, draft_candidate=draft_candidate, review_decision=review_decision, output_manifest=output_manifest))}"
            ),
            origin_state=origin_state,
            proposed_state=proposed_state,
            target_intent=f"governed_authoring.{output_manifest.output_status}",
            root_branch_id=f"governed_authoring.{source_packet.source_packet_id}",
            divergence_reason=output_manifest.decision_reason,
            invariant_path_id=GOVERNED_AUTHORING_INVARIANT_PATH_ID,
            artifact_refs=artifact_ids,
        ),
        artifact_pocket=ArtifactPocket(
            pocket_id=f"governed_authoring_artifacts.{source_packet.source_packet_id}",
            admission_status=output_manifest.output_status,
            artifact_refs=_artifact_references(
                source_packet=source_packet,
                draft_candidate=draft_candidate,
                review_decision=review_decision,
                output_manifest=output_manifest,
            ),
        ),
        variant_pocket=VariantPocket(
            pocket_id=f"governed_authoring_variants.{source_packet.source_packet_id}",
            variant_refs=[],
        ),
        human_trigger=None if review_decision is None else review_decision.to_human_trigger(),
        rollback_path=RollbackPath(
            rollback_id=f"rollback.governed_authoring.{output_manifest.output_manifest_id}",
            strategy="append_only_manifest_reversal",
            path_ref=output_manifest.output_manifest_id,
            not_required=True,
            reason="Phase 5 emits an output manifest proof path only and does not write production authoring artifacts.",
        ),
        unresolved_tensions=_formal_tensions(output_manifest),
        evidence_references=_evidence_references(output_manifest),
        architecture_nodes=[
            ArchitectureNode(
                node_id="governed_authoring_backend",
                node_type="runtime",
                authority_scope="source_to_manifest_authoring_path",
            )
        ],
        invariant_architecture=InvariantArchitecture(
            architecture_id="governed_authoring_backend.v1",
            node_ids=["governed_authoring_backend"],
            invariant_ids=[GOVERNED_AUTHORING_ROOT_INVARIANT_ID],
        ),
        consolidation_pass=ConsolidationPass(
            pass_id=f"authoring_consolidation.{source_packet.source_packet_id}",
            source_refs=[item.source_id for item in source_packet.source_material],
            output_ref=output_manifest.output_manifest_id,
        ),
        claim_assertions=[
            {
                "claim_id": claim.claim_id,
                "statement": claim.statement,
                "evidence_refs": list(claim.evidence_refs),
            }
            for claim in (draft_candidate.claim_refs if draft_candidate is not None else [])
        ],
    )


def authoring_subsystem_refs(
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
) -> list[dict[str, Any]]:
    evidence_refs = list(output_manifest.evidence_refs)
    tension_ids = [item.tension_id for item in output_manifest.unresolved_tensions]
    refs = [
        {
            "subsystem": "governed_authoring",
            "ref_type": "authoring_trace",
            "source_packet_id": source_packet.source_packet_id,
            "draft_candidate_id": output_manifest.draft_candidate_id,
            "review_decision_id": output_manifest.review_decision_id,
            "output_manifest_id": output_manifest.output_manifest_id,
            "evidence_refs": evidence_refs,
            "tension_ids": tension_ids,
        },
        {
            "subsystem": "governed_authoring",
            "ref_type": "source_packet",
            "source_packet_id": source_packet.source_packet_id,
        },
        {
            "subsystem": "governed_authoring",
            "ref_type": "output_manifest",
            "output_manifest_id": output_manifest.output_manifest_id,
            "output_status": output_manifest.output_status,
        },
    ]
    if draft_candidate is not None:
        refs.append(
            {
                "subsystem": "governed_authoring",
                "ref_type": "draft_candidate",
                "draft_candidate_id": draft_candidate.draft_candidate_id,
                "source_packet_id": source_packet.source_packet_id,
            }
        )
    if review_decision is not None:
        refs.append(
            {
                "subsystem": "governed_authoring",
                "ref_type": "review_decision",
                "review_decision_id": review_decision.review_decision_id,
                "actor_type": review_decision.actor_type,
                "decision": review_decision.decision,
            }
        )
    refs.extend(
        {
            "subsystem": "governed_authoring",
            "ref_type": "evidence_ref",
            "evidence_ref": ref,
            "output_manifest_id": output_manifest.output_manifest_id,
        }
        for ref in evidence_refs
    )
    refs.extend(
        {
            "subsystem": "governed_authoring",
            "ref_type": "unresolved_tension",
            "tension_id": item.tension_id,
            "blocking": item.blocking,
            "output_manifest_id": output_manifest.output_manifest_id,
        }
        for item in output_manifest.unresolved_tensions
    )
    return refs


def append_authoring_decision_entry(
    path: Path,
    *,
    source_packet: SourcePacket,
    draft_candidate: DraftCandidate | None,
    review_decision: ReviewDecision | None,
    output_manifest: OutputManifest,
    decision: PromotionDecision,
    timestamp: str | None = None,
) -> dict[str, Any]:
    proposal = authoring_transition_proposal(
        source_packet=source_packet,
        draft_candidate=draft_candidate,
        review_decision=review_decision,
        output_manifest=output_manifest,
        decision=decision,
    )
    return append_canonical_ledger_entry(
        Path(path),
        proposal=proposal,
        decision=decision,
        subsystem_refs=authoring_subsystem_refs(
            source_packet=source_packet,
            draft_candidate=draft_candidate,
            review_decision=review_decision,
            output_manifest=output_manifest,
        ),
        timestamp=timestamp,
    )
