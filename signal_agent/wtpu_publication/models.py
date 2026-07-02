from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from signal_agent.formal_governance.hashing import short_hash, stable_hash

from .taxonomy import (
    ADAPTATION_STATUSES,
    ESSAY_LIFECYCLE,
    FORBIDDEN_PUBLICATION_FIELDS,
    WTPU_BRAND_ID,
    validate_adaptation_status,
    validate_archive_status,
    validate_claim_type,
    validate_correction_status,
    validate_essay_lifecycle,
    validate_evidence_confidence,
    validate_interpretation_status,
    validate_section_id,
    validate_source_type,
)


_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

WTPU_PUBLICATION_EVENT_TYPES = (
    "section_created",
    "issue_created",
    "source_packet_registered",
    "essay_draft_created",
    "essay_source_packet_attached",
    "essay_claim_index_entry_added",
    "essay_evidence_interpretation_summary_set",
    "essay_review_requested",
    "essay_reviewed",
    "essay_canonical_approved",
    "campaign_link_created",
    "platform_adaptation_draft_created",
    "correction_update_created",
    "archive_dossier_recorded",
)


class WTPUModelValidationError(ValueError):
    pass


def derive_wtpu_publication_id(prefix: str, *parts: object) -> str:
    return f"{prefix}.{short_hash(parts)}"


def content_hash_for(*, record_type: str, payload: Mapping[str, Any]) -> str:
    return stable_hash({"record_type": record_type, **dict(payload)})


def reject_forbidden_publication_fields(value: object, path: str = "") -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(FORBIDDEN_PUBLICATION_FIELDS & {str(key) for key in value})
        if forbidden:
            location = f"{path}:" if path else ""
            raise WTPUModelValidationError(
                f"wtpu_publication_path_forbidden:{location}{','.join(forbidden)}"
            )
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            reject_forbidden_publication_fields(item, next_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_forbidden_publication_fields(item, f"{path}[{index}]")


def _required(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise WTPUModelValidationError(f"wtpu_{field_name}_required")
    return normalized


def _tuple(value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (value or ()) if str(item).strip())


def _dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    reject_forbidden_publication_fields(payload)
    return payload


def _validate_brand_id(value: object) -> str:
    brand_id = _required(value, "brand_id")
    if brand_id != WTPU_BRAND_ID:
        raise WTPUModelValidationError(f"wtpu_brand_mismatch:{brand_id}")
    return brand_id


def _validate_hash(value: object, field_name: str) -> str:
    normalized = _required(value, field_name)
    if not _CONTENT_HASH_RE.match(normalized):
        raise WTPUModelValidationError(f"wtpu_{field_name}_malformed")
    return normalized


def _event_refs(value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return _tuple(value)


@dataclass(frozen=True)
class PublicationSection:
    section_id: str
    brand_id: str = WTPU_BRAND_ID
    display_name: str = ""
    description: str = ""
    status: str = "active"
    provenance_note: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        section_id = validate_section_id(self.section_id)
        object.__setattr__(self, "section_id", section_id)
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "display_name", self.display_name or section_id.replace("_", " ").title())
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "brand_id": self.brand_id,
            "display_name": self.display_name,
            "description": self.description,
            "status": self.status,
            "provenance_note": self.provenance_note,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PublicationSection":
        reject_forbidden_publication_fields(payload)
        return cls(
            section_id=str(payload.get("section_id") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            display_name=str(payload.get("display_name") or ""),
            description=str(payload.get("description") or ""),
            status=str(payload.get("status") or "active"),
            provenance_note=str(payload.get("provenance_note") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class IssueRecord:
    issue_id: str
    section_id: str
    title: str
    jurisdiction: str
    scope: str
    brand_id: str = WTPU_BRAND_ID
    topic_tags: tuple[str, ...] = ()
    status: str = "draft"
    source_packet_ids: tuple[str, ...] = ()
    essay_ids: tuple[str, ...] = ()
    campaign_link_ids: tuple[str, ...] = ()
    archive_status: str = "draft"
    provenance_note: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_id", _required(self.issue_id, "issue_id"))
        object.__setattr__(self, "section_id", validate_section_id(self.section_id))
        object.__setattr__(self, "title", _required(self.title, "issue_title"))
        object.__setattr__(self, "jurisdiction", _required(self.jurisdiction, "jurisdiction"))
        object.__setattr__(self, "scope", _required(self.scope, "scope"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "topic_tags", _tuple(self.topic_tags))
        object.__setattr__(self, "source_packet_ids", _tuple(self.source_packet_ids))
        object.__setattr__(self, "essay_ids", _tuple(self.essay_ids))
        object.__setattr__(self, "campaign_link_ids", _tuple(self.campaign_link_ids))
        object.__setattr__(self, "archive_status", validate_archive_status(self.archive_status))
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "section_id": self.section_id,
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "scope": self.scope,
            "brand_id": self.brand_id,
            "topic_tags": list(self.topic_tags),
            "status": self.status,
            "source_packet_ids": list(self.source_packet_ids),
            "essay_ids": list(self.essay_ids),
            "campaign_link_ids": list(self.campaign_link_ids),
            "archive_status": self.archive_status,
            "provenance_note": self.provenance_note,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IssueRecord":
        reject_forbidden_publication_fields(payload)
        return cls(
            issue_id=str(payload.get("issue_id") or ""),
            section_id=str(payload.get("section_id") or ""),
            title=str(payload.get("title") or ""),
            jurisdiction=str(payload.get("jurisdiction") or ""),
            scope=str(payload.get("scope") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            topic_tags=tuple(payload.get("topic_tags") or ()),
            status=str(payload.get("status") or "draft"),
            source_packet_ids=tuple(payload.get("source_packet_ids") or ()),
            essay_ids=tuple(payload.get("essay_ids") or ()),
            campaign_link_ids=tuple(payload.get("campaign_link_ids") or ()),
            archive_status=str(payload.get("archive_status") or "draft"),
            provenance_note=str(payload.get("provenance_note") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class SourceReference:
    source_ref_id: str
    source_type: str
    locator: str
    source_content_hash: str
    title: str = ""
    retrieved_at: str = ""
    accessed_by: str = ""
    provenance_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ref_id", _required(self.source_ref_id, "source_ref_id"))
        object.__setattr__(self, "source_type", validate_source_type(self.source_type))
        object.__setattr__(self, "locator", _required(self.locator, "source_locator"))
        object.__setattr__(self, "source_content_hash", _validate_hash(self.source_content_hash, "source_content_hash"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ref_id": self.source_ref_id,
            "source_type": self.source_type,
            "locator": self.locator,
            "source_content_hash": self.source_content_hash,
            "title": self.title,
            "retrieved_at": self.retrieved_at,
            "accessed_by": self.accessed_by,
            "provenance_note": self.provenance_note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceReference":
        reject_forbidden_publication_fields(payload)
        return cls(
            source_ref_id=str(payload.get("source_ref_id") or ""),
            source_type=str(payload.get("source_type") or ""),
            locator=str(payload.get("locator") or ""),
            source_content_hash=str(payload.get("source_content_hash") or ""),
            title=str(payload.get("title") or ""),
            retrieved_at=str(payload.get("retrieved_at") or ""),
            accessed_by=str(payload.get("accessed_by") or ""),
            provenance_note=str(payload.get("provenance_note") or ""),
        )


@dataclass(frozen=True)
class SourcePacket:
    source_packet_id: str
    title: str
    source_refs: tuple[SourceReference, ...]
    source_limitations: tuple[str, ...]
    brand_id: str = WTPU_BRAND_ID
    status: str = "registered"
    created_by: str = ""
    provenance_note: str = ""
    content_hash: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        source_refs = _coerce_source_refs(self.source_refs)
        limitations = _tuple(self.source_limitations)
        if not source_refs:
            raise WTPUModelValidationError("wtpu_source_refs_required")
        if not limitations:
            raise WTPUModelValidationError("wtpu_source_limitations_required")
        expected_hash = content_hash_for(
            record_type="source_packet",
            payload={
                "title": self.title,
                "source_refs": [item.to_dict() for item in source_refs],
                "source_limitations": list(limitations),
                "provenance_note": self.provenance_note,
            },
        )
        if self.content_hash and self.content_hash != expected_hash:
            raise WTPUModelValidationError("wtpu_source_packet_content_hash_mismatch")
        object.__setattr__(self, "source_packet_id", _required(self.source_packet_id, "source_packet_id"))
        object.__setattr__(self, "title", _required(self.title, "source_packet_title"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "source_limitations", limitations)
        object.__setattr__(self, "content_hash", expected_hash)
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_packet_id": self.source_packet_id,
            "title": self.title,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "source_limitations": list(self.source_limitations),
            "brand_id": self.brand_id,
            "status": self.status,
            "created_by": self.created_by,
            "provenance_note": self.provenance_note,
            "content_hash": self.content_hash,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourcePacket":
        reject_forbidden_publication_fields(payload)
        return cls(
            source_packet_id=str(payload.get("source_packet_id") or ""),
            title=str(payload.get("title") or ""),
            source_refs=_coerce_source_refs(tuple(payload.get("source_refs") or ())),
            source_limitations=tuple(payload.get("source_limitations") or ()),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            status=str(payload.get("status") or "registered"),
            created_by=str(payload.get("created_by") or ""),
            provenance_note=str(payload.get("provenance_note") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class ClaimIndexEntry:
    claim_id: str
    claim_type: str
    text: str
    material: bool = True
    source_refs: tuple[str, ...] = ()
    evidence_confidence: str = "moderate"
    interpretation_status: str = "needs_review"
    caution_note: str = ""
    review_metadata: Mapping[str, Any] = field(default_factory=dict)
    claim_hash: str = ""

    def __post_init__(self) -> None:
        claim_type = validate_claim_type(self.claim_type, allow_blank=True)
        source_refs = _tuple(self.source_refs)
        metadata = _dict(self.review_metadata)
        expected_hash = content_hash_for(
            record_type="claim_index_entry",
            payload={
                "claim_id": self.claim_id,
                "claim_type": claim_type,
                "text": self.text,
                "material": bool(self.material),
                "source_refs": list(source_refs),
                "evidence_confidence": self.evidence_confidence,
                "interpretation_status": self.interpretation_status,
                "caution_note": self.caution_note,
                "review_metadata": metadata,
            },
        )
        if self.claim_hash and self.claim_hash != expected_hash:
            raise WTPUModelValidationError("wtpu_claim_hash_mismatch")
        object.__setattr__(self, "claim_id", _required(self.claim_id, "claim_id"))
        object.__setattr__(self, "text", _required(self.text, "claim_text"))
        object.__setattr__(self, "claim_type", claim_type)
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "evidence_confidence", validate_evidence_confidence(self.evidence_confidence))
        object.__setattr__(self, "interpretation_status", validate_interpretation_status(self.interpretation_status))
        object.__setattr__(self, "review_metadata", metadata)
        object.__setattr__(self, "claim_hash", expected_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "text": self.text,
            "material": self.material,
            "source_refs": list(self.source_refs),
            "evidence_confidence": self.evidence_confidence,
            "interpretation_status": self.interpretation_status,
            "caution_note": self.caution_note,
            "review_metadata": dict(self.review_metadata),
            "claim_hash": self.claim_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ClaimIndexEntry":
        reject_forbidden_publication_fields(payload)
        return cls(
            claim_id=str(payload.get("claim_id") or ""),
            claim_type=str(payload.get("claim_type") or ""),
            text=str(payload.get("text") or ""),
            material=bool(payload.get("material", True)),
            source_refs=tuple(payload.get("source_refs") or ()),
            evidence_confidence=str(payload.get("evidence_confidence") or "moderate"),
            interpretation_status=str(payload.get("interpretation_status") or "needs_review"),
            caution_note=str(payload.get("caution_note") or ""),
            review_metadata=dict(payload.get("review_metadata") or {}),
            claim_hash=str(payload.get("claim_hash") or ""),
        )


@dataclass(frozen=True)
class CanonicalCivicEssay:
    essay_id: str
    issue_id: str
    section_id: str
    title: str
    body: str
    brand_id: str = WTPU_BRAND_ID
    subtitle: str = ""
    status: str = "draft"
    source_packet_ids: tuple[str, ...] = ()
    source_limitations: tuple[str, ...] = ()
    claim_index: tuple[ClaimIndexEntry, ...] = ()
    evidence_summary: str = ""
    interpretation_summary: str = ""
    reviewer_ref: str = ""
    review_requested_at: str = ""
    reviewed_at: str = ""
    approved_content_hash: str = ""
    approval_ref: str = ""
    review_note: str = ""
    content_hash: str = ""
    version: int = 1
    supersedes_essay_id: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        claim_index = _coerce_claims(self.claim_index)
        source_packet_ids = _tuple(self.source_packet_ids)
        source_limitations = _tuple(self.source_limitations)
        expected_hash = content_hash_for(
            record_type="canonical_civic_essay",
            payload={
                "essay_id": self.essay_id,
                "issue_id": self.issue_id,
                "section_id": self.section_id,
                "title": self.title,
                "subtitle": self.subtitle,
                "body": self.body,
                "source_packet_ids": list(source_packet_ids),
                "source_limitations": list(source_limitations),
                "claim_index": [item.to_dict() for item in claim_index],
                "evidence_summary": self.evidence_summary,
                "interpretation_summary": self.interpretation_summary,
                "version": self.version,
                "supersedes_essay_id": self.supersedes_essay_id,
            },
        )
        if self.content_hash and self.content_hash != expected_hash:
            raise WTPUModelValidationError("wtpu_essay_content_hash_mismatch")
        if self.approved_content_hash:
            _validate_hash(self.approved_content_hash, "approved_content_hash")
        object.__setattr__(self, "essay_id", _required(self.essay_id, "essay_id"))
        object.__setattr__(self, "issue_id", _required(self.issue_id, "issue_id"))
        object.__setattr__(self, "section_id", validate_section_id(self.section_id))
        object.__setattr__(self, "title", _required(self.title, "essay_title"))
        object.__setattr__(self, "body", str(self.body))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "status", validate_essay_lifecycle(self.status))
        object.__setattr__(self, "source_packet_ids", source_packet_ids)
        object.__setattr__(self, "source_limitations", source_limitations)
        object.__setattr__(self, "claim_index", claim_index)
        object.__setattr__(self, "content_hash", expected_hash)
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "essay_id": self.essay_id,
            "issue_id": self.issue_id,
            "section_id": self.section_id,
            "title": self.title,
            "body": self.body,
            "brand_id": self.brand_id,
            "subtitle": self.subtitle,
            "status": self.status,
            "source_packet_ids": list(self.source_packet_ids),
            "source_limitations": list(self.source_limitations),
            "claim_index": [item.to_dict() for item in self.claim_index],
            "evidence_summary": self.evidence_summary,
            "interpretation_summary": self.interpretation_summary,
            "reviewer_ref": self.reviewer_ref,
            "review_requested_at": self.review_requested_at,
            "reviewed_at": self.reviewed_at,
            "approved_content_hash": self.approved_content_hash,
            "approval_ref": self.approval_ref,
            "review_note": self.review_note,
            "content_hash": self.content_hash,
            "version": self.version,
            "supersedes_essay_id": self.supersedes_essay_id,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanonicalCivicEssay":
        reject_forbidden_publication_fields(payload)
        return cls(
            essay_id=str(payload.get("essay_id") or ""),
            issue_id=str(payload.get("issue_id") or ""),
            section_id=str(payload.get("section_id") or ""),
            title=str(payload.get("title") or ""),
            body=str(payload.get("body") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            subtitle=str(payload.get("subtitle") or ""),
            status=str(payload.get("status") or "draft"),
            source_packet_ids=tuple(payload.get("source_packet_ids") or ()),
            source_limitations=tuple(payload.get("source_limitations") or ()),
            claim_index=_coerce_claims(tuple(payload.get("claim_index") or ())),
            evidence_summary=str(payload.get("evidence_summary") or ""),
            interpretation_summary=str(payload.get("interpretation_summary") or ""),
            reviewer_ref=str(payload.get("reviewer_ref") or ""),
            review_requested_at=str(payload.get("review_requested_at") or ""),
            reviewed_at=str(payload.get("reviewed_at") or ""),
            approved_content_hash=str(payload.get("approved_content_hash") or ""),
            approval_ref=str(payload.get("approval_ref") or ""),
            review_note=str(payload.get("review_note") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            version=int(payload.get("version", 1) or 1),
            supersedes_essay_id=str(payload.get("supersedes_essay_id") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class CampaignLink:
    campaign_link_id: str
    issue_id: str
    essay_id: str
    campaign_id: str
    brand_id: str = WTPU_BRAND_ID
    campaign_system: str = "social_orchestration"
    campaign_hash: str = ""
    source_brand_id: str = WTPU_BRAND_ID
    relationship_type: str = "campaign_derivative"
    adaptation_ids: tuple[str, ...] = ()
    status: str = "linked"
    provenance_note: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_link_id", _required(self.campaign_link_id, "campaign_link_id"))
        object.__setattr__(self, "issue_id", _required(self.issue_id, "issue_id"))
        object.__setattr__(self, "essay_id", _required(self.essay_id, "essay_id"))
        object.__setattr__(self, "campaign_id", _required(self.campaign_id, "campaign_id"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        if self.source_brand_id and self.source_brand_id != WTPU_BRAND_ID:
            raise WTPUModelValidationError(f"wtpu_brand_mismatch:{self.source_brand_id}")
        object.__setattr__(self, "adaptation_ids", _tuple(self.adaptation_ids))
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_link_id": self.campaign_link_id,
            "issue_id": self.issue_id,
            "essay_id": self.essay_id,
            "campaign_id": self.campaign_id,
            "brand_id": self.brand_id,
            "campaign_system": self.campaign_system,
            "campaign_hash": self.campaign_hash,
            "source_brand_id": self.source_brand_id,
            "relationship_type": self.relationship_type,
            "adaptation_ids": list(self.adaptation_ids),
            "status": self.status,
            "provenance_note": self.provenance_note,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignLink":
        reject_forbidden_publication_fields(payload)
        return cls(
            campaign_link_id=str(payload.get("campaign_link_id") or ""),
            issue_id=str(payload.get("issue_id") or ""),
            essay_id=str(payload.get("essay_id") or ""),
            campaign_id=str(payload.get("campaign_id") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            campaign_system=str(payload.get("campaign_system") or "social_orchestration"),
            campaign_hash=str(payload.get("campaign_hash") or ""),
            source_brand_id=str(payload.get("source_brand_id") or WTPU_BRAND_ID),
            relationship_type=str(payload.get("relationship_type") or "campaign_derivative"),
            adaptation_ids=tuple(payload.get("adaptation_ids") or ()),
            status=str(payload.get("status") or "linked"),
            provenance_note=str(payload.get("provenance_note") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class PlatformAdaptation:
    adaptation_id: str
    essay_id: str
    platform: str
    adaptation_type: str
    body: str
    brand_id: str = WTPU_BRAND_ID
    campaign_link_id: str = ""
    status: str = "draft"
    source_refs: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()
    reviewer_ref: str = ""
    approved_content_hash: str = ""
    content_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        metadata = _dict(self.metadata)
        source_refs = _tuple(self.source_refs)
        claim_ids = _tuple(self.claim_ids)
        risk_flags = _tuple(self.risk_flags)
        expected_hash = content_hash_for(
            record_type="platform_adaptation",
            payload={
                "essay_id": self.essay_id,
                "platform": self.platform,
                "adaptation_type": self.adaptation_type,
                "body": self.body,
                "source_refs": list(source_refs),
                "claim_ids": list(claim_ids),
                "risk_flags": list(risk_flags),
                "metadata": metadata,
            },
        )
        if self.content_hash and self.content_hash != expected_hash:
            raise WTPUModelValidationError("wtpu_adaptation_content_hash_mismatch")
        if self.approved_content_hash:
            _validate_hash(self.approved_content_hash, "approved_content_hash")
        object.__setattr__(self, "adaptation_id", _required(self.adaptation_id, "adaptation_id"))
        object.__setattr__(self, "essay_id", _required(self.essay_id, "essay_id"))
        object.__setattr__(self, "platform", _required(self.platform, "platform"))
        object.__setattr__(self, "adaptation_type", _required(self.adaptation_type, "adaptation_type"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "status", validate_adaptation_status(self.status))
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "claim_ids", claim_ids)
        object.__setattr__(self, "risk_flags", risk_flags)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "content_hash", expected_hash)
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "adaptation_id": self.adaptation_id,
            "essay_id": self.essay_id,
            "platform": self.platform,
            "adaptation_type": self.adaptation_type,
            "body": self.body,
            "brand_id": self.brand_id,
            "campaign_link_id": self.campaign_link_id,
            "status": self.status,
            "source_refs": list(self.source_refs),
            "claim_ids": list(self.claim_ids),
            "risk_flags": list(self.risk_flags),
            "reviewer_ref": self.reviewer_ref,
            "approved_content_hash": self.approved_content_hash,
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlatformAdaptation":
        reject_forbidden_publication_fields(payload)
        return cls(
            adaptation_id=str(payload.get("adaptation_id") or ""),
            essay_id=str(payload.get("essay_id") or ""),
            platform=str(payload.get("platform") or ""),
            adaptation_type=str(payload.get("adaptation_type") or ""),
            body=str(payload.get("body") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            campaign_link_id=str(payload.get("campaign_link_id") or ""),
            status=str(payload.get("status") or "draft"),
            source_refs=tuple(payload.get("source_refs") or ()),
            claim_ids=tuple(payload.get("claim_ids") or ()),
            risk_flags=tuple(payload.get("risk_flags") or ()),
            reviewer_ref=str(payload.get("reviewer_ref") or ""),
            approved_content_hash=str(payload.get("approved_content_hash") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            metadata=dict(payload.get("metadata") or {}),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class CorrectionUpdateRecord:
    correction_id: str
    target_type: str
    target_id: str
    target_hash: str
    correction_type: str
    reason: str
    brand_id: str = WTPU_BRAND_ID
    status: str = "correction_pending"
    replacement_ref: str = ""
    visible_note: str = ""
    reviewer_ref: str = ""
    content_hash: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        expected_hash = content_hash_for(
            record_type="correction_update",
            payload={
                "target_type": self.target_type,
                "target_id": self.target_id,
                "target_hash": self.target_hash,
                "correction_type": self.correction_type,
                "reason": self.reason,
                "status": self.status,
                "replacement_ref": self.replacement_ref,
                "visible_note": self.visible_note,
                "reviewer_ref": self.reviewer_ref,
            },
        )
        if self.content_hash and self.content_hash != expected_hash:
            raise WTPUModelValidationError("wtpu_correction_content_hash_mismatch")
        object.__setattr__(self, "correction_id", _required(self.correction_id, "correction_id"))
        object.__setattr__(self, "target_type", _required(self.target_type, "target_type"))
        object.__setattr__(self, "target_id", _required(self.target_id, "target_id"))
        object.__setattr__(self, "target_hash", _validate_hash(self.target_hash, "target_hash"))
        object.__setattr__(self, "correction_type", _required(self.correction_type, "correction_type"))
        object.__setattr__(self, "reason", _required(self.reason, "correction_reason"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "status", validate_correction_status(self.status))
        object.__setattr__(self, "content_hash", expected_hash)
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "correction_id": self.correction_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_hash": self.target_hash,
            "correction_type": self.correction_type,
            "reason": self.reason,
            "brand_id": self.brand_id,
            "status": self.status,
            "replacement_ref": self.replacement_ref,
            "visible_note": self.visible_note,
            "reviewer_ref": self.reviewer_ref,
            "content_hash": self.content_hash,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CorrectionUpdateRecord":
        reject_forbidden_publication_fields(payload)
        return cls(
            correction_id=str(payload.get("correction_id") or ""),
            target_type=str(payload.get("target_type") or ""),
            target_id=str(payload.get("target_id") or ""),
            target_hash=str(payload.get("target_hash") or ""),
            correction_type=str(payload.get("correction_type") or ""),
            reason=str(payload.get("reason") or ""),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            status=str(payload.get("status") or "correction_pending"),
            replacement_ref=str(payload.get("replacement_ref") or ""),
            visible_note=str(payload.get("visible_note") or ""),
            reviewer_ref=str(payload.get("reviewer_ref") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class ArchiveDossierRecord:
    dossier_id: str
    title: str
    issue_ids: tuple[str, ...]
    brand_id: str = WTPU_BRAND_ID
    essay_ids: tuple[str, ...] = ()
    source_packet_ids: tuple[str, ...] = ()
    campaign_link_ids: tuple[str, ...] = ()
    correction_ids: tuple[str, ...] = ()
    archive_status: str = "draft"
    readiness_blockers: tuple[str, ...] = ()
    curator_ref: str = ""
    provenance_note: str = ""
    audit_event_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    internal_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "dossier_id", _required(self.dossier_id, "dossier_id"))
        object.__setattr__(self, "title", _required(self.title, "dossier_title"))
        object.__setattr__(self, "brand_id", _validate_brand_id(self.brand_id))
        object.__setattr__(self, "issue_ids", _tuple(self.issue_ids))
        if not self.issue_ids:
            raise WTPUModelValidationError("wtpu_dossier_issue_ids_required")
        object.__setattr__(self, "essay_ids", _tuple(self.essay_ids))
        object.__setattr__(self, "source_packet_ids", _tuple(self.source_packet_ids))
        object.__setattr__(self, "campaign_link_ids", _tuple(self.campaign_link_ids))
        object.__setattr__(self, "correction_ids", _tuple(self.correction_ids))
        object.__setattr__(self, "archive_status", validate_archive_status(self.archive_status))
        object.__setattr__(self, "readiness_blockers", _tuple(self.readiness_blockers))
        object.__setattr__(self, "audit_event_refs", _event_refs(self.audit_event_refs))
        if self.internal_only is not True:
            raise WTPUModelValidationError("wtpu_internal_only_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "title": self.title,
            "issue_ids": list(self.issue_ids),
            "brand_id": self.brand_id,
            "essay_ids": list(self.essay_ids),
            "source_packet_ids": list(self.source_packet_ids),
            "campaign_link_ids": list(self.campaign_link_ids),
            "correction_ids": list(self.correction_ids),
            "archive_status": self.archive_status,
            "readiness_blockers": list(self.readiness_blockers),
            "curator_ref": self.curator_ref,
            "provenance_note": self.provenance_note,
            "audit_event_refs": list(self.audit_event_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "internal_only": self.internal_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArchiveDossierRecord":
        reject_forbidden_publication_fields(payload)
        return cls(
            dossier_id=str(payload.get("dossier_id") or ""),
            title=str(payload.get("title") or ""),
            issue_ids=tuple(payload.get("issue_ids") or ()),
            brand_id=str(payload.get("brand_id") or WTPU_BRAND_ID),
            essay_ids=tuple(payload.get("essay_ids") or ()),
            source_packet_ids=tuple(payload.get("source_packet_ids") or ()),
            campaign_link_ids=tuple(payload.get("campaign_link_ids") or ()),
            correction_ids=tuple(payload.get("correction_ids") or ()),
            archive_status=str(payload.get("archive_status") or "draft"),
            readiness_blockers=tuple(payload.get("readiness_blockers") or ()),
            curator_ref=str(payload.get("curator_ref") or ""),
            provenance_note=str(payload.get("provenance_note") or ""),
            audit_event_refs=tuple(payload.get("audit_event_refs") or ()),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            internal_only=bool(payload.get("internal_only", True)),
        )


@dataclass(frozen=True)
class WTPUPublicationEvent:
    event_id: str
    event_type: str
    occurred_at: str
    actor_id: str = ""
    actor_type: str = ""
    command_id: str = ""
    command_payload_hash: str = ""
    entity_id: str = ""
    entity_type: str = ""
    section_id: str = ""
    issue_id: str = ""
    source_packet_id: str = ""
    essay_id: str = ""
    adaptation_id: str = ""
    correction_id: str = ""
    dossier_id: str = ""
    input_hash: str = ""
    output_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        event_type = str(self.event_type or "").strip()
        if event_type not in WTPU_PUBLICATION_EVENT_TYPES:
            raise WTPUModelValidationError(f"wtpu_event_type_not_allowed:{event_type}")
        metadata = _dict(self.metadata)
        object.__setattr__(self, "event_id", _required(self.event_id, "event_id"))
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "occurred_at", _required(self.occurred_at, "occurred_at"))
        if self.command_id and not self.command_payload_hash:
            raise WTPUModelValidationError("wtpu_command_payload_hash_required")
        if self.command_payload_hash:
            _validate_hash(self.command_payload_hash, "command_payload_hash")
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "command_id": self.command_id,
            "command_payload_hash": self.command_payload_hash,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "section_id": self.section_id,
            "issue_id": self.issue_id,
            "source_packet_id": self.source_packet_id,
            "essay_id": self.essay_id,
            "adaptation_id": self.adaptation_id,
            "correction_id": self.correction_id,
            "dossier_id": self.dossier_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WTPUPublicationEvent":
        reject_forbidden_publication_fields(payload)
        return cls(
            event_id=str(payload.get("event_id") or ""),
            event_type=str(payload.get("event_type") or ""),
            occurred_at=str(payload.get("occurred_at") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            actor_type=str(payload.get("actor_type") or ""),
            command_id=str(payload.get("command_id") or ""),
            command_payload_hash=str(payload.get("command_payload_hash") or ""),
            entity_id=str(payload.get("entity_id") or ""),
            entity_type=str(payload.get("entity_type") or ""),
            section_id=str(payload.get("section_id") or ""),
            issue_id=str(payload.get("issue_id") or ""),
            source_packet_id=str(payload.get("source_packet_id") or ""),
            essay_id=str(payload.get("essay_id") or ""),
            adaptation_id=str(payload.get("adaptation_id") or ""),
            correction_id=str(payload.get("correction_id") or ""),
            dossier_id=str(payload.get("dossier_id") or ""),
            input_hash=str(payload.get("input_hash") or ""),
            output_hash=str(payload.get("output_hash") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


def validate_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip()
    if normalized not in WTPU_PUBLICATION_EVENT_TYPES:
        raise WTPUModelValidationError(f"wtpu_event_type_not_allowed:{normalized}")
    return normalized


def _coerce_source_refs(value: tuple[SourceReference | Mapping[str, Any], ...]) -> tuple[SourceReference, ...]:
    return tuple(item if isinstance(item, SourceReference) else SourceReference.from_dict(item) for item in value)


def _coerce_claims(value: tuple[ClaimIndexEntry | Mapping[str, Any], ...]) -> tuple[ClaimIndexEntry, ...]:
    return tuple(item if isinstance(item, ClaimIndexEntry) else ClaimIndexEntry.from_dict(item) for item in value)
