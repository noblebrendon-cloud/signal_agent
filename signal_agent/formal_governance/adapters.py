from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_ledger import append_canonical_ledger_entry
from .hashing import short_hash, stable_hash
from .models import (
    ArtifactPocket,
    BranchVector,
    DecisionOutcome,
    GateResult,
    GateStatus,
    HumanTrigger,
    Invariant,
    InvariantPath,
    PromotionDecision,
    RollbackPath,
    State,
    TransitionProposal,
    VariantPocket,
)


CLAIM_ROOT_INVARIANT_ID = "invariant.claim_evidence_required"
HQ_PROMOTION_ROOT_INVARIANT_ID = "invariant.hq_promotion_governed_decision"


def _clean_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _sorted_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted(str(item) for item in values if str(item))


def _path_str(path: Path | str | None) -> str:
    return "" if path is None else str(path)


def _claim_evidence_refs(claim: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in claim.get("evidence_refs") or []:
        if not ref:
            continue
        refs.append({"evidence_id": str(ref), "ref": str(ref)})
    return refs


def _claim_human_trigger(claim: dict[str, Any], action: str) -> HumanTrigger | None:
    authority = claim.get("evidence_authority")
    if type(authority) is not dict:
        return None
    actor_type = _clean_str(authority.get("actor_type"))
    actor_id = _clean_str(authority.get("actor_id")) or "unknown"
    self_certified = bool(authority.get("self_certified"))
    return HumanTrigger(
        trigger_id=f"claim_evidence_authority.{short_hash({'claim_id': claim.get('claim_id'), 'action': action})}",
        actor_id=actor_id,
        actor_type=actor_type,
        role="evidence_authority",
        scope=f"claim:{action}",
        approval_status="approved" if actor_type == "human" and not self_certified else "unapproved",
        timestamp=_clean_str(claim.get("timestamp_utc")),
        self_certified=self_certified,
    )


def _claim_default_subsystem_refs(
    claim: dict[str, Any],
    action: str,
    subsystem_refs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    refs = [
        {
            "subsystem": "claim_runtime",
            "ref_type": "claim",
            "claim_id": _clean_str(claim.get("claim_id")),
            "claim_source_id": _clean_str(claim.get("source_id")),
            "claim_status": _clean_str(claim.get("status")),
            "action": action,
        }
    ]
    refs.extend(dict(item) for item in subsystem_refs or [])
    return refs


def claim_evidence_proposal(
    claim: dict[str, Any],
    *,
    action: str,
    decision: PromotionDecision,
) -> TransitionProposal:
    claim_id = _clean_str(claim.get("claim_id")) or decision.proposal_id
    origin_state = _clean_str(claim.get("status")) or "unknown"
    proposed_state = f"claim.{action}"
    invariant_path_id = f"claim_evidence.{action}.v1"
    statement = _clean_str(claim.get("statement"))
    core_assertion = _clean_str(claim.get("core_assertion"))

    return TransitionProposal(
        proposal_id=decision.proposal_id or claim_id,
        requested_decision=decision.decision.value,
        origin_state=State(
            state_id=origin_state,
            label=origin_state,
            kind="claim_evidence",
        ),
        proposed_state=State(
            state_id=proposed_state,
            label=action,
            kind="claim_evidence",
        ),
        root_invariant=Invariant(
            invariant_id=CLAIM_ROOT_INVARIANT_ID,
            statement="Claims that advance beyond provisional draft require non-empty, non-self-certified evidence references.",
            version="v1",
        ),
        invariant_path=InvariantPath(
            path_id=invariant_path_id,
            root_invariant_id=CLAIM_ROOT_INVARIANT_ID,
            state_sequence=[origin_state, proposed_state],
        ),
        branch_vector=BranchVector(
            branch_id=f"claim.{claim_id}.{action}",
            origin_state=origin_state,
            proposed_state=proposed_state,
            target_intent=f"claim_{action}",
            root_branch_id=f"claim.{claim_id}",
            invariant_path_id=invariant_path_id,
            artifact_refs=[claim_id],
        ),
        artifact_pocket=ArtifactPocket(
            pocket_id=f"claim_artifacts.{claim_id}",
            admission_status=origin_state,
            artifact_refs=[
                {
                    "artifact_id": claim_id,
                    "artifact_type": "claim",
                    "source_status": origin_state,
                    "content_hash": stable_hash(
                        {
                            "statement": statement,
                            "core_assertion": core_assertion,
                            "evidence_refs": claim.get("evidence_refs") or [],
                        }
                    ),
                }
            ],
        ),
        variant_pocket=VariantPocket(pocket_id=f"claim_variants.{claim_id}", variant_refs=[]),
        human_trigger=_claim_human_trigger(claim, action),
        rollback_path=RollbackPath(
            rollback_id=f"rollback.claim.{claim_id}.{action}",
            strategy="append_only_claim_reversal",
            path_ref=claim_id,
            not_required=True,
            reason="Claim evidence decisions are ledgered before optional downstream writes.",
        ),
        unresolved_tensions=[],
        evidence_references=_claim_evidence_refs(claim),
        claim_assertions=[
            {
                "claim_id": claim_id,
                "statement": statement,
                "core_assertion": core_assertion,
            }
        ],
    )


def append_claim_evidence_entry(
    path: Path,
    *,
    claim: dict[str, Any],
    action: str,
    decision: PromotionDecision,
    subsystem_refs: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    proposal = claim_evidence_proposal(claim, action=action, decision=decision)
    return append_canonical_ledger_entry(
        Path(path),
        proposal=proposal,
        decision=decision,
        subsystem_refs=_claim_default_subsystem_refs(claim, action, subsystem_refs),
        timestamp=timestamp,
    )


def _hq_gate_results(validation: dict[str, Any]) -> list[GateResult]:
    policy_result = validation.get("policy_result") if type(validation.get("policy_result")) is dict else {}
    runtime_checks = policy_result.get("runtime_checks") if type(policy_result.get("runtime_checks")) is list else []
    gates: list[GateResult] = []

    for check in runtime_checks:
        if type(check) is not dict:
            continue
        name = _clean_str(check.get("name")) or "hq_transition_check"
        ok = bool(check.get("ok"))
        gates.append(
            GateResult(
                gate_name=name,
                status=GateStatus.PASS if ok else GateStatus.FAIL,
                reason_code=f"{name}_passed" if ok else name,
                message=str(check.get("detail") if check.get("detail") is not None else name),
                outcome=None if ok else DecisionOutcome.MANUAL_REVIEW_REQUIRED,
            )
        )

    if gates:
        return gates

    allowed = bool(validation.get("allowed"))
    reason = _clean_str(validation.get("reason")) or ("transition_allowed" if allowed else "transition_rejected")
    return [
        GateResult(
            gate_name=_clean_str(validation.get("gate")) or "hq_transition_gate",
            status=GateStatus.PASS if allowed else GateStatus.FAIL,
            reason_code=reason,
            message=reason,
            outcome=None if allowed else DecisionOutcome.MANUAL_REVIEW_REQUIRED,
        )
    ]


def hq_promotion_decision(
    validation: dict[str, Any],
    *,
    artifact_id: str,
    bundle_filename: str,
    cluster_id: str,
    candidate_cluster_members: list[str],
) -> PromotionDecision:
    allowed = bool(validation.get("allowed"))
    reason = _clean_str(validation.get("reason")) or ("transition_allowed" if allowed else "transition_rejected")
    deterministic_decision_id = stable_hash(
        {
            "schema_version": "hq_promotion_decision.v1",
            "allowed": allowed,
            "artifact_id": artifact_id,
            "bundle_filename": bundle_filename,
            "cluster_id": cluster_id,
            "candidate_cluster_members": sorted(candidate_cluster_members),
            "current_state": validation.get("current_state"),
            "next_state": validation.get("next_state"),
            "lane_id": validation.get("lane_id"),
            "policy_id": validation.get("policy_id"),
            "policy_result": validation.get("policy_result"),
            "reason": validation.get("reason"),
        }
    )
    return PromotionDecision(
        deterministic_decision_id=deterministic_decision_id,
        decision=DecisionOutcome.PROMOTE_TO_STATE if allowed else DecisionOutcome.MANUAL_REVIEW_REQUIRED,
        decision_reason=reason,
        gate_results=_hq_gate_results(validation),
        proposal_id=artifact_id,
    )


def hq_promotion_proposal(
    validation: dict[str, Any],
    *,
    artifact_id: str,
    bundle_filename: str,
    cluster_id: str,
    candidate_cluster_members: list[str],
    bundle_path: Path | None = None,
    transition_ledger_path: Path | None = None,
) -> TransitionProposal:
    origin_state = _clean_str(validation.get("current_state")) or "missing"
    proposed_state = _clean_str(validation.get("next_state")) or "promoted"
    invariant_path_id = "hq_capture_promotion.v1"
    raw_refs = _sorted_strings(candidate_cluster_members)

    artifact_refs = [
        {
            "artifact_id": bundle_filename or artifact_id,
            "artifact_type": "hq_capture_bundle",
            "source_status": origin_state,
            "path": _path_str(bundle_path),
            "cluster_id": cluster_id,
        }
    ]
    artifact_refs.extend(
        {
            "artifact_id": raw_file,
            "artifact_type": "raw_capture",
            "source_status": "raw",
            "cluster_id": cluster_id,
        }
        for raw_file in raw_refs
    )

    evidence_refs = [
        {
            "evidence_id": f"raw_capture:{raw_file}",
            "ref": raw_file,
            "evidence_type": "candidate_cluster_member",
        }
        for raw_file in raw_refs
    ]
    if transition_ledger_path is not None:
        evidence_refs.append(
            {
                "evidence_id": "hq_transition_gate_events",
                "ref": str(transition_ledger_path),
                "evidence_type": "transition_gate_ledger",
            }
        )

    return TransitionProposal(
        proposal_id=artifact_id,
        requested_decision=DecisionOutcome.PROMOTE_TO_STATE.value,
        origin_state=State(state_id=origin_state, label=origin_state, kind="hq_lifecycle"),
        proposed_state=State(state_id=proposed_state, label=proposed_state, kind="hq_lifecycle"),
        root_invariant=Invariant(
            invariant_id=HQ_PROMOTION_ROOT_INVARIANT_ID,
            statement="HQ capture promotion decisions must precede promoted bundle materialization and state promotion writes.",
            version="v1",
        ),
        invariant_path=InvariantPath(
            path_id=invariant_path_id,
            root_invariant_id=HQ_PROMOTION_ROOT_INVARIANT_ID,
            state_sequence=[origin_state, proposed_state],
        ),
        branch_vector=BranchVector(
            branch_id=f"hq_capture.{cluster_id or short_hash({'bundle': bundle_filename})}",
            origin_state=origin_state,
            proposed_state=proposed_state,
            target_intent="promote_capture_cluster",
            root_branch_id=f"hq_capture.{cluster_id or artifact_id}",
            invariant_path_id=invariant_path_id,
            artifact_refs=[bundle_filename or artifact_id, *raw_refs],
        ),
        artifact_pocket=ArtifactPocket(
            pocket_id=f"hq_capture_artifacts.{cluster_id or artifact_id}",
            admission_status="candidate",
            artifact_refs=artifact_refs,
        ),
        variant_pocket=VariantPocket(pocket_id=f"hq_capture_variants.{cluster_id or artifact_id}", variant_refs=[]),
        human_trigger=None,
        rollback_path=RollbackPath(
            rollback_id=f"rollback.hq_capture.{artifact_id}",
            strategy="pre_write_rejection_or_append_only_state_reversal",
            path_ref=_path_str(bundle_path),
            not_required=False,
            reason="",
        ),
        unresolved_tensions=[],
        evidence_references=evidence_refs,
    )


def _hq_subsystem_refs(
    validation: dict[str, Any],
    *,
    artifact_id: str,
    bundle_filename: str,
    bundle_path: Path | None,
    promotion_log_path: Path | None,
    transition_ledger_path: Path | None,
    transition_event: dict[str, Any] | None,
    artifact_registry_path: Path | None,
) -> list[dict[str, Any]]:
    refs = [
        {
            "subsystem": "hq_capture",
            "ref_type": "promotion_bundle",
            "artifact_id": artifact_id,
            "bundle_filename": bundle_filename,
            "path": _path_str(bundle_path),
            "materialized": bool(validation.get("allowed")),
        }
    ]
    if promotion_log_path is not None:
        refs.append(
            {
                "subsystem": "hq_capture",
                "ref_type": "promotion_log",
                "path": str(promotion_log_path),
                "success_log_applicable": bool(validation.get("allowed")),
            }
        )
    if transition_ledger_path is not None:
        refs.append(
            {
                "subsystem": "hq_governance",
                "ref_type": "transition_gate_event",
                "path": str(transition_ledger_path),
                "run_id": _clean_str((transition_event or {}).get("run_id")),
                "status": _clean_str((transition_event or {}).get("status")),
            }
        )
    if artifact_registry_path is not None:
        refs.append(
            {
                "subsystem": "state_registry",
                "ref_type": "artifact_registry",
                "path": str(artifact_registry_path),
                "state_update_applicable": bool(validation.get("allowed")),
            }
        )
    return refs


def append_hq_promotion_entry(
    path: Path,
    *,
    validation: dict[str, Any],
    artifact_id: str,
    bundle_filename: str,
    cluster_id: str,
    candidate_cluster_members: list[str],
    bundle_path: Path | None = None,
    promotion_log_path: Path | None = None,
    transition_ledger_path: Path | None = None,
    transition_event: dict[str, Any] | None = None,
    artifact_registry_path: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    decision = hq_promotion_decision(
        validation,
        artifact_id=artifact_id,
        bundle_filename=bundle_filename,
        cluster_id=cluster_id,
        candidate_cluster_members=candidate_cluster_members,
    )
    proposal = hq_promotion_proposal(
        validation,
        artifact_id=artifact_id,
        bundle_filename=bundle_filename,
        cluster_id=cluster_id,
        candidate_cluster_members=candidate_cluster_members,
        bundle_path=bundle_path,
        transition_ledger_path=transition_ledger_path,
    )
    return append_canonical_ledger_entry(
        Path(path),
        proposal=proposal,
        decision=decision,
        subsystem_refs=_hq_subsystem_refs(
            validation,
            artifact_id=artifact_id,
            bundle_filename=bundle_filename,
            bundle_path=bundle_path,
            promotion_log_path=promotion_log_path,
            transition_ledger_path=transition_ledger_path,
            transition_event=transition_event,
            artifact_registry_path=artifact_registry_path,
        ),
        timestamp=timestamp or _clean_str((transition_event or {}).get("timestamp_utc")) or None,
    )
