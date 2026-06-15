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
OPERATOR_ROOT_INVARIANT_ID = "invariant.operator_write_governance"


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


def _attr(value: Any, name: str, default: Any = None) -> Any:
    if type(value) is dict:
        return value.get(name, default)
    return getattr(value, name, default)


def _operator_plan_identity(plan: Any) -> dict[str, Any]:
    intent = _attr(plan, "intent")
    workflow = _attr(plan, "workflow")
    target_workflow = _attr(plan, "target_workflow")
    return {
        "plan_status": _clean_str(_attr(plan, "status")),
        "command_text": _clean_str(_attr(intent, "command_text")).strip().lower(),
        "intent_id": _clean_str(_attr(intent, "intent_id")),
        "requested_workflow": _clean_str(_attr(intent, "requested_workflow")),
        "requested_target": _clean_str(_attr(intent, "requested_target")),
        "requested_target_kind": _clean_str(_attr(intent, "requested_target_kind")),
        "workflow_id": _clean_str(_attr(workflow, "workflow_id")),
        "workflow_mode": _clean_str(_attr(workflow, "mode")),
        "target_workflow_id": _clean_str(_attr(target_workflow, "workflow_id")),
    }


def _operator_tool_summaries(result: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for tool_result in _attr(result, "tool_results", ()) or ():
        details = _attr(tool_result, "details", {}) if type(_attr(tool_result, "details", {})) is dict else {}
        summaries.append(
            {
                "tool_id": _clean_str(_attr(tool_result, "tool_id")),
                "status": _clean_str(_attr(tool_result, "status")),
                "consistency_status": _clean_str(details.get("_consistency_status")),
                "rejection_reason": _clean_str(details.get("rejection_reason")),
                "violation": _clean_str(details.get("violation")),
                "verification_status": _clean_str(
                    details.get("_tool_contract", {}).get("verification_status")
                    if type(details.get("_tool_contract")) is dict
                    else ""
                ),
                "workflow_id": _clean_str(details.get("workflow_id")),
            }
        )
    return summaries


def _operator_gate_summary(gate_validation: dict[str, Any] | None) -> dict[str, Any]:
    if type(gate_validation) is not dict:
        return {}
    policy_result = gate_validation.get("policy_result") if type(gate_validation.get("policy_result")) is dict else {}
    return {
        "allowed": bool(gate_validation.get("allowed")),
        "current_state": gate_validation.get("current_state"),
        "next_state": gate_validation.get("next_state"),
        "lane_id": gate_validation.get("lane_id"),
        "gate": gate_validation.get("gate"),
        "policy_id": gate_validation.get("policy_id"),
        "policy_failures": list(policy_result.get("failures") or []),
        "reason": gate_validation.get("reason"),
    }


def _operator_decision_reason(
    result: Any,
    gate_validation: dict[str, Any] | None,
    tool_summaries: list[dict[str, Any]],
) -> str:
    for summary in tool_summaries:
        for key in ("rejection_reason", "violation", "consistency_status"):
            value = _clean_str(summary.get(key))
            if value and value not in {"consistent_read_only", "observed_as_declared", "observed_as_declared_transactional"}:
                return value
    if type(gate_validation) is dict and _clean_str(gate_validation.get("reason")):
        return _clean_str(gate_validation.get("reason"))
    status = _clean_str(_attr(result, "status"))
    return "operator_decision_allowed" if status == "ok" else status or "operator_decision_unknown"


def _operator_decision_outcome(status: str, reason: str) -> DecisionOutcome:
    if reason == "duplicate_record_detected":
        return DecisionOutcome.BLOCK_DUPLICATE
    if status == "ok":
        return DecisionOutcome.PROMOTE_TO_STATE
    return DecisionOutcome.MANUAL_REVIEW_REQUIRED


def _operator_gate_results(
    result: Any,
    gate_validation: dict[str, Any] | None,
    tool_summaries: list[dict[str, Any]],
) -> list[GateResult]:
    gates: list[GateResult] = []
    if type(gate_validation) is dict:
        policy_result = gate_validation.get("policy_result") if type(gate_validation.get("policy_result")) is dict else {}
        runtime_checks = policy_result.get("runtime_checks") if type(policy_result.get("runtime_checks")) is list else []
        for check in runtime_checks:
            if type(check) is not dict:
                continue
            name = _clean_str(check.get("name")) or "operator_transition_check"
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
        if not gates:
            allowed = bool(gate_validation.get("allowed"))
            reason = _clean_str(gate_validation.get("reason")) or ("operator_transition_allowed" if allowed else "operator_transition_rejected")
            gates.append(
                GateResult(
                    gate_name=_clean_str(gate_validation.get("gate")) or "operator_transition_gate",
                    status=GateStatus.PASS if allowed else GateStatus.FAIL,
                    reason_code=reason,
                    message=reason,
                    outcome=None if allowed else DecisionOutcome.MANUAL_REVIEW_REQUIRED,
                )
            )

    for summary in tool_summaries:
        status = _clean_str(summary.get("status"))
        reason = (
            _clean_str(summary.get("rejection_reason"))
            or _clean_str(summary.get("violation"))
            or _clean_str(summary.get("consistency_status"))
            or status
            or "operator_tool_result"
        )
        ok = status == "ok" and reason in {"ok", "observed_as_declared", "observed_as_declared_transactional", "consistent_read_only"}
        outcome = None
        if reason == "duplicate_record_detected":
            outcome = DecisionOutcome.BLOCK_DUPLICATE
        elif not ok:
            outcome = DecisionOutcome.MANUAL_REVIEW_REQUIRED
        gates.append(
            GateResult(
                gate_name=f"operator_tool:{summary.get('tool_id') or 'unknown'}",
                status=GateStatus.PASS if ok else GateStatus.FAIL,
                reason_code=reason,
                message=f"operator tool status={status or 'unknown'} consistency={summary.get('consistency_status') or 'unknown'}",
                outcome=outcome,
            )
        )

    if not gates:
        status = _clean_str(_attr(result, "status"))
        gates.append(
            GateResult(
                gate_name="operator_result",
                status=GateStatus.PASS if status == "ok" else GateStatus.FAIL,
                reason_code=status or "operator_result_unknown",
                message=f"operator result status={status or 'unknown'}",
                outcome=None if status == "ok" else DecisionOutcome.MANUAL_REVIEW_REQUIRED,
            )
        )
    return gates


def _operator_decision_material(
    plan: Any,
    result: Any,
    gate_validation: dict[str, Any] | None,
    tool_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "operator_governed_decision.v1",
        "plan": _operator_plan_identity(plan),
        "result_status": _clean_str(_attr(result, "status")),
        "gate": _operator_gate_summary(gate_validation),
        "tools": tool_summaries,
    }


def operator_decision(
    *,
    plan: Any,
    result: Any,
    gate_validation: dict[str, Any] | None = None,
) -> PromotionDecision:
    tool_summaries = _operator_tool_summaries(result)
    reason = _operator_decision_reason(result, gate_validation, tool_summaries)
    status = _clean_str(_attr(result, "status"))
    return PromotionDecision(
        deterministic_decision_id=stable_hash(
            _operator_decision_material(plan, result, gate_validation, tool_summaries)
        ),
        decision=_operator_decision_outcome(status, reason),
        decision_reason=reason,
        gate_results=_operator_gate_results(result, gate_validation, tool_summaries),
        proposal_id=_clean_str(_attr(result, "run_id")),
    )


def _operator_artifact_references(result: Any, tool_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_id = _clean_str(_attr(result, "run_id"))
    refs = [
        {
            "artifact_id": run_id,
            "artifact_type": "operator_run_record",
            "source_status": _clean_str(_attr(result, "status")),
            "path": _clean_str(_attr(result, "run_record_path")),
        },
        {
            "artifact_id": "operator_runs.jsonl",
            "artifact_type": "operator_run_ledger",
            "source_status": "append_only_summary",
            "path": _clean_str(_attr(result, "ledger_path")),
        },
    ]
    refs.extend(
        {
            "artifact_id": f"{run_id}:{summary.get('tool_id')}",
            "artifact_type": "operator_tool_result",
            "source_status": _clean_str(summary.get("status")),
            "tool_id": _clean_str(summary.get("tool_id")),
            "consistency_status": _clean_str(summary.get("consistency_status")),
        }
        for summary in tool_summaries
    )
    return refs


def operator_transition_proposal(
    *,
    plan: Any,
    result: Any,
    decision: PromotionDecision,
    gate_validation: dict[str, Any] | None = None,
) -> TransitionProposal:
    plan_identity = _operator_plan_identity(plan)
    tool_summaries = _operator_tool_summaries(result)
    gate_summary = _operator_gate_summary(gate_validation)
    origin_state = _clean_str(gate_summary.get("current_state")) or f"operator.{plan_identity['plan_status'] or 'planned'}"
    proposed_state = _clean_str(gate_summary.get("next_state")) or f"operator.{_clean_str(_attr(result, 'status')) or 'completed'}"
    invariant_path_id = "operator_write_governance.v1"
    run_id = _clean_str(_attr(result, "run_id"))
    workflow_id = plan_identity["workflow_id"] or _clean_str(_attr(result, "workflow_id"))
    tool_ids = [_clean_str(summary.get("tool_id")) for summary in tool_summaries if _clean_str(summary.get("tool_id"))]

    return TransitionProposal(
        proposal_id=run_id,
        requested_decision=decision.decision.value,
        origin_state=State(state_id=origin_state, label=origin_state, kind="operator_runtime"),
        proposed_state=State(state_id=proposed_state, label=proposed_state, kind="operator_runtime"),
        root_invariant=Invariant(
            invariant_id=OPERATOR_ROOT_INVARIANT_ID,
            statement="Operator write decisions must be governed by registry contracts, transition gates, duplicate checks, and observed-effect evidence.",
            version="v1",
        ),
        invariant_path=InvariantPath(
            path_id=invariant_path_id,
            root_invariant_id=OPERATOR_ROOT_INVARIANT_ID,
            state_sequence=[origin_state, proposed_state],
        ),
        branch_vector=BranchVector(
            branch_id=f"operator.{workflow_id or 'unknown'}.{short_hash(_operator_decision_material(plan, result, gate_validation, tool_summaries))}",
            origin_state=origin_state,
            proposed_state=proposed_state,
            target_intent=plan_identity["intent_id"],
            root_branch_id=f"operator.{workflow_id or 'unknown'}",
            invariant_path_id=invariant_path_id,
            artifact_refs=[run_id, *tool_ids],
        ),
        artifact_pocket=ArtifactPocket(
            pocket_id=f"operator_artifacts.{run_id}",
            admission_status=_clean_str(_attr(result, "status")),
            artifact_refs=_operator_artifact_references(result, tool_summaries),
        ),
        variant_pocket=VariantPocket(pocket_id=f"operator_variants.{run_id}", variant_refs=[]),
        human_trigger=None,
        rollback_path=RollbackPath(
            rollback_id=f"rollback.operator.{run_id}",
            strategy="operator_run_evidence_and_existing_subsystem_controls",
            path_ref=_clean_str(_attr(result, "run_record_path")),
            not_required=True,
            reason="Canonical operator entries link existing run evidence without replacing operator ledgers.",
        ),
        unresolved_tensions=[],
        evidence_references=[
            {
                "evidence_id": f"operator_run_record:{run_id}",
                "ref": _clean_str(_attr(result, "run_record_path")),
                "evidence_type": "operator_run_record",
            },
            {
                "evidence_id": "operator_runs_ledger",
                "ref": _clean_str(_attr(result, "ledger_path")),
                "evidence_type": "operator_summary_ledger",
            },
        ],
    )


def _operator_subsystem_refs(
    *,
    plan: Any,
    result: Any,
    gate_validation: dict[str, Any] | None,
    extra_refs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    plan_identity = _operator_plan_identity(plan)
    tool_summaries = _operator_tool_summaries(result)
    consistency_statuses = sorted(
        {
            _clean_str(summary.get("consistency_status"))
            for summary in tool_summaries
            if _clean_str(summary.get("consistency_status"))
        }
    )
    refs = [
        {
            "subsystem": "operator_runtime",
            "ref_type": "operator_run",
            "run_id": _clean_str(_attr(result, "run_id")),
            "workflow_id": plan_identity["workflow_id"] or _clean_str(_attr(result, "workflow_id")),
            "target_workflow_id": plan_identity["target_workflow_id"] or _clean_str(_attr(result, "target_workflow_id")),
            "tool_ids": [
                _clean_str(summary.get("tool_id"))
                for summary in tool_summaries
                if _clean_str(summary.get("tool_id"))
            ],
            "run_record_path": _clean_str(_attr(result, "run_record_path")),
            "operator_ledger_path": _clean_str(_attr(result, "ledger_path")),
            "transition_status": _clean_str(_attr(result, "status")),
            "consistency_status": ",".join(consistency_statuses),
        }
    ]
    if type(gate_validation) is dict:
        refs.append(
            {
                "subsystem": "operator_runtime",
                "ref_type": "transition_gate",
                "run_id": _clean_str(_attr(result, "run_id")),
                "workflow_id": plan_identity["workflow_id"] or _clean_str(_attr(result, "workflow_id")),
                "allowed": bool(gate_validation.get("allowed")),
                "current_state": _clean_str(gate_validation.get("current_state")),
                "next_state": _clean_str(gate_validation.get("next_state")),
                "lane_id": _clean_str(gate_validation.get("lane_id")),
                "reason": _clean_str(gate_validation.get("reason")),
            }
        )
    refs.extend(dict(item) for item in extra_refs or [])
    return refs


def append_operator_decision_entry(
    path: Path,
    *,
    plan: Any,
    result: Any,
    gate_validation: dict[str, Any] | None = None,
    subsystem_refs: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    decision = operator_decision(
        plan=plan,
        result=result,
        gate_validation=gate_validation,
    )
    proposal = operator_transition_proposal(
        plan=plan,
        result=result,
        decision=decision,
        gate_validation=gate_validation,
    )
    return append_canonical_ledger_entry(
        Path(path),
        proposal=proposal,
        decision=decision,
        subsystem_refs=_operator_subsystem_refs(
            plan=plan,
            result=result,
            gate_validation=gate_validation,
            extra_refs=subsystem_refs,
        ),
        timestamp=timestamp or _clean_str(_attr(result, "completed_at")) or None,
    )
