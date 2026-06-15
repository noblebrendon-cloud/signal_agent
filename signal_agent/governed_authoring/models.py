from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from signal_agent.formal_governance.hashing import short_hash, stable_hash
from signal_agent.formal_governance.models import HumanTrigger, PromotionDecision


SOURCE_PACKET_SCHEMA_VERSION = "governed_authoring.source_packet.v1"
DRAFT_CANDIDATE_SCHEMA_VERSION = "governed_authoring.draft_candidate.v1"
REVIEW_DECISION_SCHEMA_VERSION = "governed_authoring.review_decision.v1"
OUTPUT_MANIFEST_SCHEMA_VERSION = "governed_authoring.output_manifest.v1"

PROVISIONAL_MODES = {"provisional", "unverified"}
PUBLICATION_READY_MODES = {"approved", "publication_ready", "publish_ready"}
SELF_APPROVAL_ACTOR_TYPES = {"agent", "generator", "model"}


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _bool(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _clean_refs(values: Any) -> list[str]:
    refs: list[str] = []
    for value in _as_list(values):
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
        elif type(value) is dict:
            ref = _str(value.get("evidence_id")) or _str(value.get("ref")) or _str(value.get("uri"))
            if ref:
                refs.append(ref)
    return list(dict.fromkeys(refs))


@dataclass(frozen=True)
class SourceMaterial:
    source_id: str
    text: str = ""
    uri: str = ""
    content_hash: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_obj(cls, value: Any) -> "SourceMaterial":
        if isinstance(value, str):
            return cls(
                source_id=f"source.{short_hash(value)}",
                text=value,
                content_hash=stable_hash(value),
            )
        payload = _as_mapping(value)
        text = _str(payload.get("text"))
        uri = _str(payload.get("uri"))
        content_hash = _str(payload.get("content_hash")) or (stable_hash(text) if text else "")
        return cls(
            source_id=_str(payload.get("source_id")) or f"source.{short_hash({'text': text, 'uri': uri})}",
            text=text,
            uri=uri,
            content_hash=content_hash,
            evidence_refs=_clean_refs(payload.get("evidence_refs")),
        )

    def has_content(self) -> bool:
        return bool(self.text.strip() or self.uri.strip() or self.content_hash.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "text": self.text,
            "uri": self.uri,
            "content_hash": self.content_hash,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ClaimReference:
    claim_id: str
    statement: str
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "provisional"

    @classmethod
    def from_obj(cls, value: Any) -> "ClaimReference":
        payload = _as_mapping(value)
        statement = _str(payload.get("statement")) or _str(payload.get("core_assertion"))
        return cls(
            claim_id=_str(payload.get("claim_id")) or f"claim.{short_hash(statement)}",
            statement=statement,
            evidence_refs=_clean_refs(payload.get("evidence_refs")),
            status=_str(payload.get("status")) or "provisional",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
        }


@dataclass(frozen=True)
class AuthoringTension:
    tension_id: str
    description: str
    blocking: bool
    severity: str = "medium"

    @classmethod
    def from_obj(cls, value: Any) -> "AuthoringTension":
        payload = _as_mapping(value)
        return cls(
            tension_id=_str(payload.get("tension_id")) or f"tension.{short_hash(payload)}",
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
class ReviewDecision:
    review_decision_id: str
    actor_id: str
    actor_type: str
    role: str
    scope: str
    decision: str
    timestamp: str
    self_certified: bool = False

    @classmethod
    def from_obj(cls, value: Any) -> "ReviewDecision | None":
        if value is None:
            return None
        payload = _as_mapping(value)
        return cls(
            review_decision_id=_str(payload.get("review_decision_id")) or f"review.{short_hash(payload)}",
            actor_id=_str(payload.get("actor_id")),
            actor_type=_str(payload.get("actor_type")),
            role=_str(payload.get("role")) or "authoring_reviewer",
            scope=_str(payload.get("scope")) or "governed_authoring_output",
            decision=_str(payload.get("decision")),
            timestamp=_str(payload.get("timestamp")),
            self_certified=_bool(payload.get("self_certified")),
        )

    def is_self_approval(self) -> bool:
        return self.self_certified or self.actor_type in SELF_APPROVAL_ACTOR_TYPES

    def is_approved_human(self) -> bool:
        return bool(
            self.actor_type == "human"
            and self.actor_id
            and self.role
            and self.scope
            and self.decision == "approved"
            and self.timestamp
            and not self.self_certified
        )

    def to_human_trigger(self) -> HumanTrigger:
        return HumanTrigger(
            trigger_id=self.review_decision_id,
            actor_id=self.actor_id,
            actor_type=self.actor_type,
            role=self.role,
            scope=self.scope,
            approval_status="approved" if self.is_approved_human() else "unapproved",
            timestamp=self.timestamp,
            self_certified=self.self_certified,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_DECISION_SCHEMA_VERSION,
            "review_decision_id": self.review_decision_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "role": self.role,
            "scope": self.scope,
            "decision": self.decision,
            "timestamp": self.timestamp,
            "self_certified": self.self_certified,
        }


@dataclass(frozen=True)
class SourcePacket:
    source_packet_id: str
    requested_output_status: str
    draft_mode: str
    source_material: list[SourceMaterial] = field(default_factory=list)
    claims: list[ClaimReference] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    unresolved_tensions: list[AuthoringTension] = field(default_factory=list)
    review_decision: ReviewDecision | None = None
    title: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourcePacket":
        packet = _as_mapping(payload)
        source_material = [SourceMaterial.from_obj(item) for item in _as_list(packet.get("source_material"))]
        claims = [ClaimReference.from_obj(item) for item in _as_list(packet.get("claims"))]
        source_packet_id = _str(packet.get("source_packet_id")) or f"source_packet.{short_hash(packet)}"
        draft_mode = _str(packet.get("draft_mode")) or "provisional"
        return cls(
            source_packet_id=source_packet_id,
            requested_output_status=_str(packet.get("requested_output_status")) or "provisional",
            draft_mode=draft_mode,
            source_material=source_material,
            claims=claims,
            evidence_refs=_clean_refs(packet.get("evidence_refs")),
            unresolved_tensions=[
                AuthoringTension.from_obj(item) for item in _as_list(packet.get("unresolved_tensions"))
            ],
            review_decision=ReviewDecision.from_obj(packet.get("review_decision")),
            title=_str(packet.get("title")),
        )

    def has_source_material(self) -> bool:
        return any(item.has_content() for item in self.source_material)

    def all_evidence_refs(self) -> list[str]:
        refs: list[str] = []
        refs.extend(self.evidence_refs)
        for material in self.source_material:
            refs.extend(material.evidence_refs)
        for claim in self.claims:
            refs.extend(claim.evidence_refs)
        return list(dict.fromkeys(ref for ref in refs if ref))

    def claim_references(self) -> list[ClaimReference]:
        if self.claims:
            return list(self.claims)
        first_source = next((item for item in self.source_material if item.has_content()), None)
        if first_source is None:
            return []
        statement = first_source.text.strip() or first_source.uri or first_source.content_hash
        return [
            ClaimReference(
                claim_id=f"claim.{short_hash({'source_packet_id': self.source_packet_id, 'statement': statement})}",
                statement=statement[:500],
                evidence_refs=self.all_evidence_refs(),
                status="provisional" if self.draft_mode in PROVISIONAL_MODES else "publication_ready",
            )
        ]

    def is_provisional_request(self) -> bool:
        return self.requested_output_status in PROVISIONAL_MODES or self.draft_mode in PROVISIONAL_MODES

    def is_publication_ready_request(self) -> bool:
        return self.requested_output_status in PUBLICATION_READY_MODES or self.draft_mode in PUBLICATION_READY_MODES

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SOURCE_PACKET_SCHEMA_VERSION,
            "source_packet_id": self.source_packet_id,
            "requested_output_status": self.requested_output_status,
            "draft_mode": self.draft_mode,
            "title": self.title,
            "source_material": [item.to_dict() for item in self.source_material],
            "claims": [item.to_dict() for item in self.claims],
            "evidence_refs": list(self.evidence_refs),
            "unresolved_tensions": [item.to_dict() for item in self.unresolved_tensions],
            "review_decision": None if self.review_decision is None else self.review_decision.to_dict(),
        }


@dataclass(frozen=True)
class DraftCandidate:
    draft_candidate_id: str
    source_packet_id: str
    status: str
    claim_refs: list[ClaimReference] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    source_material_refs: list[str] = field(default_factory=list)
    unresolved_tensions: list[AuthoringTension] = field(default_factory=list)

    @classmethod
    def from_source_packet(cls, packet: SourcePacket) -> "DraftCandidate":
        claim_refs = packet.claim_references()
        status = "provisional" if packet.is_provisional_request() else "publication_ready"
        source_refs = [item.source_id for item in packet.source_material if item.has_content()]
        return cls(
            draft_candidate_id=f"draft.{short_hash({'packet': packet.source_packet_id, 'claims': [c.to_dict() for c in claim_refs]})}",
            source_packet_id=packet.source_packet_id,
            status=status,
            claim_refs=claim_refs,
            evidence_refs=packet.all_evidence_refs(),
            source_material_refs=source_refs,
            unresolved_tensions=list(packet.unresolved_tensions),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DRAFT_CANDIDATE_SCHEMA_VERSION,
            "draft_candidate_id": self.draft_candidate_id,
            "source_packet_id": self.source_packet_id,
            "status": self.status,
            "claim_refs": [item.to_dict() for item in self.claim_refs],
            "evidence_refs": list(self.evidence_refs),
            "source_material_refs": list(self.source_material_refs),
            "unresolved_tensions": [item.to_dict() for item in self.unresolved_tensions],
        }


@dataclass(frozen=True)
class OutputManifest:
    output_manifest_id: str
    source_packet_id: str
    draft_candidate_id: str
    review_decision_id: str
    output_status: str
    decision: str
    decision_reason: str
    claim_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    unresolved_tensions: list[AuthoringTension] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    canonical_ledger_entry_id: str = ""

    @classmethod
    def build(
        cls,
        *,
        source_packet: SourcePacket,
        draft_candidate: DraftCandidate | None,
        review_decision: ReviewDecision | None,
        output_status: str,
        decision: str,
        decision_reason: str,
        messages: list[str] | None = None,
    ) -> "OutputManifest":
        claim_refs = [claim.claim_id for claim in draft_candidate.claim_refs] if draft_candidate else []
        evidence_refs = list(draft_candidate.evidence_refs) if draft_candidate else []
        tensions = list(source_packet.unresolved_tensions)
        review_decision_id = review_decision.review_decision_id if review_decision else ""
        material = {
            "source_packet_id": source_packet.source_packet_id,
            "draft_candidate_id": draft_candidate.draft_candidate_id if draft_candidate else "",
            "review_decision_id": review_decision_id,
            "output_status": output_status,
            "decision": decision,
            "claim_refs": claim_refs,
            "evidence_refs": evidence_refs,
            "tension_ids": [item.tension_id for item in tensions],
        }
        return cls(
            output_manifest_id=f"output_manifest.{short_hash(material)}",
            source_packet_id=source_packet.source_packet_id,
            draft_candidate_id=draft_candidate.draft_candidate_id if draft_candidate else "",
            review_decision_id=review_decision_id,
            output_status=output_status,
            decision=decision,
            decision_reason=decision_reason,
            claim_refs=claim_refs,
            evidence_refs=evidence_refs,
            unresolved_tensions=tensions,
            messages=list(messages or []),
        )

    def with_canonical_entry(self, ledger_entry_id: str) -> "OutputManifest":
        return OutputManifest(
            output_manifest_id=self.output_manifest_id,
            source_packet_id=self.source_packet_id,
            draft_candidate_id=self.draft_candidate_id,
            review_decision_id=self.review_decision_id,
            output_status=self.output_status,
            decision=self.decision,
            decision_reason=self.decision_reason,
            claim_refs=list(self.claim_refs),
            evidence_refs=list(self.evidence_refs),
            unresolved_tensions=list(self.unresolved_tensions),
            messages=list(self.messages),
            canonical_ledger_entry_id=ledger_entry_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OUTPUT_MANIFEST_SCHEMA_VERSION,
            "output_manifest_id": self.output_manifest_id,
            "source_packet_id": self.source_packet_id,
            "draft_candidate_id": self.draft_candidate_id,
            "review_decision_id": self.review_decision_id,
            "output_status": self.output_status,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "claim_refs": list(self.claim_refs),
            "evidence_refs": list(self.evidence_refs),
            "unresolved_tensions": [item.to_dict() for item in self.unresolved_tensions],
            "messages": list(self.messages),
            "canonical_ledger_entry_id": self.canonical_ledger_entry_id,
        }


@dataclass(frozen=True)
class GovernedAuthoringResult:
    source_packet: SourcePacket
    draft_candidate: DraftCandidate | None
    review_decision: ReviewDecision | None
    output_manifest: OutputManifest
    formal_decision: PromotionDecision
    canonical_ledger_entry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_packet": self.source_packet.to_dict(),
            "draft_candidate": None if self.draft_candidate is None else self.draft_candidate.to_dict(),
            "review_decision": None if self.review_decision is None else self.review_decision.to_dict(),
            "output_manifest": self.output_manifest.to_dict(),
            "formal_decision": self.formal_decision.to_dict(),
            "canonical_ledger_entry": self.canonical_ledger_entry,
        }
