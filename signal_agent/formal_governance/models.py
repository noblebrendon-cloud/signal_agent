from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionOutcome(str, Enum):
    ADMIT_ARTIFACT = "ADMIT_ARTIFACT"
    CONSOLIDATE_ONLY = "CONSOLIDATE_ONLY"
    PROMOTE_TO_STATE = "PROMOTE_TO_STATE"
    DEFER_UNRESOLVED_TENSION = "DEFER_UNRESOLVED_TENSION"
    REJECT_INVALID_LINEAGE = "REJECT_INVALID_LINEAGE"
    REJECT_MISSING_INVARIANT = "REJECT_MISSING_INVARIANT"
    REJECT_RAW_ARTIFACT_SELF_PROMOTION = "REJECT_RAW_ARTIFACT_SELF_PROMOTION"
    REJECT_MISSING_EVIDENCE = "REJECT_MISSING_EVIDENCE"
    REJECT_MISSING_AUTHORITY = "REJECT_MISSING_AUTHORITY"
    REJECT_SELF_CERTIFICATION = "REJECT_SELF_CERTIFICATION"
    REJECT_MISSING_ROLLBACK = "REJECT_MISSING_ROLLBACK"
    BLOCK_DUPLICATE = "BLOCK_DUPLICATE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    DEFER = "defer"
    BLOCK = "block"
    MANUAL_REVIEW = "manual_review"


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _bool(value: Any) -> bool:
    return value if isinstance(value, bool) else False


@dataclass(frozen=True)
class State:
    state_id: str
    label: str = ""
    kind: str = "lifecycle"

    @classmethod
    def from_obj(cls, value: Any) -> "State":
        if isinstance(value, str):
            return cls(state_id=value)
        payload = _as_mapping(value)
        return cls(
            state_id=_str(payload.get("state_id")),
            label=_str(payload.get("label")),
            kind=_str(payload.get("kind")) or "lifecycle",
        )

    def to_dict(self) -> dict[str, Any]:
        return {"state_id": self.state_id, "label": self.label, "kind": self.kind}


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    statement: str
    version: str = "v1"

    @classmethod
    def from_obj(cls, value: Any) -> "Invariant":
        payload = _as_mapping(value)
        return cls(
            invariant_id=_str(payload.get("invariant_id")),
            statement=_str(payload.get("statement")),
            version=_str(payload.get("version")) or "v1",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "statement": self.statement,
            "version": self.version,
        }


@dataclass(frozen=True)
class InvariantPath:
    path_id: str
    root_invariant_id: str
    state_sequence: list[str] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "InvariantPath":
        payload = _as_mapping(value)
        return cls(
            path_id=_str(payload.get("path_id")),
            root_invariant_id=_str(payload.get("root_invariant_id")),
            state_sequence=[_str(item) for item in _as_list(payload.get("state_sequence"))],
        )

    def binds(self, invariant: Invariant) -> bool:
        return bool(self.path_id and invariant.invariant_id and self.root_invariant_id == invariant.invariant_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "root_invariant_id": self.root_invariant_id,
            "state_sequence": list(self.state_sequence),
        }


@dataclass(frozen=True)
class BranchVector:
    branch_id: str
    origin_state: str
    proposed_state: str = ""
    target_intent: str = ""
    parent_branch_id: str = ""
    root_branch_id: str = ""
    divergence_reason: str = ""
    invariant_path_id: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    variant_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "BranchVector":
        payload = _as_mapping(value)
        return cls(
            branch_id=_str(payload.get("branch_id")),
            origin_state=_str(payload.get("origin_state")),
            proposed_state=_str(payload.get("proposed_state")),
            target_intent=_str(payload.get("target_intent")),
            parent_branch_id=_str(payload.get("parent_branch_id")),
            root_branch_id=_str(payload.get("root_branch_id")),
            divergence_reason=_str(payload.get("divergence_reason")),
            invariant_path_id=_str(payload.get("invariant_path_id")),
            artifact_refs=[_str(item) for item in _as_list(payload.get("artifact_refs"))],
            variant_refs=[_str(item) for item in _as_list(payload.get("variant_refs"))],
        )

    def has_parent_or_root(self) -> bool:
        return bool(self.parent_branch_id or self.root_branch_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "origin_state": self.origin_state,
            "proposed_state": self.proposed_state,
            "target_intent": self.target_intent,
            "parent_branch_id": self.parent_branch_id,
            "root_branch_id": self.root_branch_id,
            "divergence_reason": self.divergence_reason,
            "invariant_path_id": self.invariant_path_id,
            "artifact_refs": list(self.artifact_refs),
            "variant_refs": list(self.variant_refs),
        }


@dataclass(frozen=True)
class ArtifactPocket:
    pocket_id: str
    admission_status: str
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "ArtifactPocket":
        payload = _as_mapping(value)
        return cls(
            pocket_id=_str(payload.get("pocket_id")),
            admission_status=_str(payload.get("admission_status")),
            artifact_refs=[dict(item) for item in _as_list(payload.get("artifact_refs")) if type(item) is dict],
        )

    def artifact_ids(self) -> list[str]:
        return [_str(item.get("artifact_id")) for item in self.artifact_refs if _str(item.get("artifact_id"))]

    def has_raw_artifacts(self) -> bool:
        if self.admission_status == "raw":
            return True
        return any(_str(item.get("source_status")) == "raw" for item in self.artifact_refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pocket_id": self.pocket_id,
            "admission_status": self.admission_status,
            "artifact_refs": [dict(item) for item in self.artifact_refs],
        }


@dataclass(frozen=True)
class VariantPocket:
    pocket_id: str
    variant_refs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "VariantPocket":
        payload = _as_mapping(value)
        return cls(
            pocket_id=_str(payload.get("pocket_id")),
            variant_refs=[dict(item) for item in _as_list(payload.get("variant_refs")) if type(item) is dict],
        )

    def variant_ids(self) -> list[str]:
        return [_str(item.get("variant_id")) for item in self.variant_refs if _str(item.get("variant_id"))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pocket_id": self.pocket_id,
            "variant_refs": [dict(item) for item in self.variant_refs],
        }


@dataclass(frozen=True)
class ArchitectureNode:
    node_id: str
    node_type: str
    authority_scope: str = ""

    @classmethod
    def from_obj(cls, value: Any) -> "ArchitectureNode":
        payload = _as_mapping(value)
        return cls(
            node_id=_str(payload.get("node_id")),
            node_type=_str(payload.get("node_type")),
            authority_scope=_str(payload.get("authority_scope")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "authority_scope": self.authority_scope,
        }


@dataclass(frozen=True)
class InvariantArchitecture:
    architecture_id: str
    node_ids: list[str] = field(default_factory=list)
    invariant_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "InvariantArchitecture":
        payload = _as_mapping(value)
        return cls(
            architecture_id=_str(payload.get("architecture_id")),
            node_ids=[_str(item) for item in _as_list(payload.get("node_ids"))],
            invariant_ids=[_str(item) for item in _as_list(payload.get("invariant_ids"))],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture_id": self.architecture_id,
            "node_ids": list(self.node_ids),
            "invariant_ids": list(self.invariant_ids),
        }


@dataclass(frozen=True)
class HumanTrigger:
    trigger_id: str
    actor_id: str
    actor_type: str
    role: str
    scope: str
    approval_status: str
    timestamp: str
    self_certified: bool = False

    @classmethod
    def from_obj(cls, value: Any) -> "HumanTrigger | None":
        if value is None:
            return None
        payload = _as_mapping(value)
        return cls(
            trigger_id=_str(payload.get("trigger_id")),
            actor_id=_str(payload.get("actor_id")),
            actor_type=_str(payload.get("actor_type")),
            role=_str(payload.get("role")),
            scope=_str(payload.get("scope")),
            approval_status=_str(payload.get("approval_status")),
            timestamp=_str(payload.get("timestamp")),
            self_certified=_bool(payload.get("self_certified")),
        )

    def is_approved_human(self) -> bool:
        return bool(
            self.actor_type == "human"
            and self.role
            and self.scope
            and self.approval_status == "approved"
            and self.timestamp
        )

    def is_self_certifying(self) -> bool:
        return self.self_certified or self.actor_type in {"agent", "generator", "model"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "role": self.role,
            "scope": self.scope,
            "approval_status": self.approval_status,
            "timestamp": self.timestamp,
            "self_certified": self.self_certified,
        }


@dataclass(frozen=True)
class ConsolidationPass:
    pass_id: str
    source_refs: list[str] = field(default_factory=list)
    output_ref: str = ""

    @classmethod
    def from_obj(cls, value: Any) -> "ConsolidationPass":
        payload = _as_mapping(value)
        return cls(
            pass_id=_str(payload.get("pass_id")),
            source_refs=[_str(item) for item in _as_list(payload.get("source_refs"))],
            output_ref=_str(payload.get("output_ref")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_id": self.pass_id,
            "source_refs": list(self.source_refs),
            "output_ref": self.output_ref,
        }


@dataclass(frozen=True)
class RollbackPath:
    rollback_id: str
    strategy: str
    path_ref: str = ""
    not_required: bool = False
    reason: str = ""

    @classmethod
    def from_obj(cls, value: Any) -> "RollbackPath | None":
        if value is None:
            return None
        payload = _as_mapping(value)
        return cls(
            rollback_id=_str(payload.get("rollback_id")),
            strategy=_str(payload.get("strategy")),
            path_ref=_str(payload.get("path_ref")),
            not_required=_bool(payload.get("not_required")),
            reason=_str(payload.get("reason")),
        )

    def satisfies_state_mutation(self) -> bool:
        if self.not_required:
            return bool(self.reason)
        return bool(self.rollback_id and self.strategy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "strategy": self.strategy,
            "path_ref": self.path_ref,
            "not_required": self.not_required,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class UnresolvedTension:
    tension_id: str
    description: str
    blocking: bool
    severity: str = "medium"

    @classmethod
    def from_obj(cls, value: Any) -> "UnresolvedTension":
        payload = _as_mapping(value)
        return cls(
            tension_id=_str(payload.get("tension_id")),
            description=_str(payload.get("description")),
            blocking=_bool(payload.get("blocking")),
            severity=_str(payload.get("severity")) or "medium",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tension_id": self.tension_id,
            "description": self.description,
            "blocking": self.blocking,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    status: GateStatus
    reason_code: str
    message: str
    outcome: DecisionOutcome | None = None

    def is_blocking(self) -> bool:
        return self.status in {
            GateStatus.FAIL,
            GateStatus.DEFER,
            GateStatus.BLOCK,
            GateStatus.MANUAL_REVIEW,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "message": self.message,
        }
        if self.outcome is not None:
            payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True)
class TransitionProposal:
    proposal_id: str
    requested_decision: str
    origin_state: State
    proposed_state: State
    root_invariant: Invariant
    invariant_path: InvariantPath
    branch_vector: BranchVector
    artifact_pocket: ArtifactPocket
    variant_pocket: VariantPocket
    human_trigger: HumanTrigger | None
    rollback_path: RollbackPath | None
    unresolved_tensions: list[UnresolvedTension] = field(default_factory=list)
    evidence_references: list[dict[str, Any]] = field(default_factory=list)
    architecture_nodes: list[ArchitectureNode] = field(default_factory=list)
    invariant_architecture: InvariantArchitecture = field(default_factory=lambda: InvariantArchitecture(""))
    consolidation_pass: ConsolidationPass = field(default_factory=lambda: ConsolidationPass(""))
    claim_assertions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_fixture(cls, fixture: dict[str, Any]) -> "TransitionProposal":
        return cls.from_dict(_as_mapping(fixture.get("proposal")))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TransitionProposal":
        return cls(
            proposal_id=_str(payload.get("proposal_id")),
            requested_decision=_str(payload.get("requested_decision")),
            origin_state=State.from_obj(payload.get("origin_state")),
            proposed_state=State.from_obj(payload.get("proposed_state")),
            root_invariant=Invariant.from_obj(payload.get("root_invariant")),
            invariant_path=InvariantPath.from_obj(payload.get("invariant_path")),
            branch_vector=BranchVector.from_obj(payload.get("branch_vector")),
            artifact_pocket=ArtifactPocket.from_obj(payload.get("artifact_pocket")),
            variant_pocket=VariantPocket.from_obj(payload.get("variant_pocket")),
            human_trigger=HumanTrigger.from_obj(payload.get("human_trigger")),
            rollback_path=RollbackPath.from_obj(payload.get("rollback_path")),
            unresolved_tensions=[
                UnresolvedTension.from_obj(item) for item in _as_list(payload.get("unresolved_tensions"))
            ],
            evidence_references=[
                dict(item) for item in _as_list(payload.get("evidence_references")) if type(item) is dict
            ],
            architecture_nodes=[
                ArchitectureNode.from_obj(item) for item in _as_list(payload.get("architecture_nodes"))
            ],
            invariant_architecture=InvariantArchitecture.from_obj(payload.get("invariant_architecture")),
            consolidation_pass=ConsolidationPass.from_obj(payload.get("consolidation_pass")),
            claim_assertions=[dict(item) for item in _as_list(payload.get("claim_assertions")) if type(item) is dict],
        )

    def is_state_promotion(self) -> bool:
        return self.requested_decision == DecisionOutcome.PROMOTE_TO_STATE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "requested_decision": self.requested_decision,
            "origin_state": self.origin_state.to_dict(),
            "proposed_state": self.proposed_state.to_dict(),
            "root_invariant": self.root_invariant.to_dict(),
            "invariant_path": self.invariant_path.to_dict(),
            "branch_vector": self.branch_vector.to_dict(),
            "artifact_pocket": self.artifact_pocket.to_dict(),
            "variant_pocket": self.variant_pocket.to_dict(),
            "human_trigger": None if self.human_trigger is None else self.human_trigger.to_dict(),
            "rollback_path": None if self.rollback_path is None else self.rollback_path.to_dict(),
            "unresolved_tensions": [item.to_dict() for item in self.unresolved_tensions],
            "evidence_references": [dict(item) for item in self.evidence_references],
            "architecture_nodes": [item.to_dict() for item in self.architecture_nodes],
            "invariant_architecture": self.invariant_architecture.to_dict(),
            "consolidation_pass": self.consolidation_pass.to_dict(),
            "claim_assertions": [dict(item) for item in self.claim_assertions],
        }


@dataclass(frozen=True)
class PromotionDecision:
    deterministic_decision_id: str
    decision: DecisionOutcome
    decision_reason: str
    gate_results: list[GateResult]
    proposal_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "deterministic_decision_id": self.deterministic_decision_id,
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "gate_results": [gate.to_dict() for gate in self.gate_results],
            "proposal_id": self.proposal_id,
        }


@dataclass(frozen=True)
class LedgerEntry:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)

