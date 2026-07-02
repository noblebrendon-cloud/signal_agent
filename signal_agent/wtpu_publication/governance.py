from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import (
    CanonicalCivicEssay,
    CorrectionUpdateRecord,
    PlatformAdaptation,
    SourcePacket,
    reject_forbidden_publication_fields,
)
from .taxonomy import WTPU_BRAND_ID


@dataclass(frozen=True)
class GovernanceBlocker:
    code: str
    entity_id: str = ""
    field: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "entity_id": self.entity_id,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class GovernanceResult:
    allowed: bool
    blockers: tuple[GovernanceBlocker, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


def canonical_essay_governance(
    essay: CanonicalCivicEssay,
    source_packets: Mapping[str, SourcePacket],
) -> GovernanceResult:
    blockers: list[GovernanceBlocker] = []
    blockers.extend(_forbidden_field_blockers(essay.to_dict(), essay.essay_id))
    if essay.brand_id != WTPU_BRAND_ID:
        blockers.append(_blocker("brand_mismatch", essay.essay_id, "brand_id", essay.brand_id))
    if not essay.source_packet_ids:
        blockers.append(_blocker("source_packet_missing", essay.essay_id, "source_packet_ids"))
    for source_packet_id in essay.source_packet_ids:
        packet = source_packets.get(source_packet_id)
        if packet is None:
            blockers.append(_blocker("source_packet_missing", essay.essay_id, "source_packet_ids", source_packet_id))
            continue
        if packet.brand_id != WTPU_BRAND_ID:
            blockers.append(_blocker("brand_mismatch", source_packet_id, "brand_id", packet.brand_id))
        if not packet.source_limitations:
            blockers.append(_blocker("source_limitations_missing", source_packet_id, "source_limitations"))
        for source_ref in packet.source_refs:
            if not source_ref.source_content_hash:
                blockers.append(_blocker("source_content_hash_missing", source_ref.source_ref_id, "source_content_hash"))
    if not essay.source_limitations:
        blockers.append(_blocker("source_limitations_missing", essay.essay_id, "source_limitations"))
    if not essay.reviewer_ref:
        blockers.append(_blocker("reviewer_missing", essay.essay_id, "reviewer_ref"))
    if essay.approved_content_hash != essay.content_hash:
        blockers.append(_blocker("approval_hash_mismatch", essay.essay_id, "approved_content_hash"))
    material_claims = tuple(claim for claim in essay.claim_index if claim.material)
    if material_claims and any(not claim.claim_type for claim in material_claims):
        blockers.append(_blocker("material_claim_untyped", essay.essay_id, "claim_index"))
    if not essay.evidence_summary or not essay.interpretation_summary:
        blockers.append(_blocker("evidence_interpretation_not_separated", essay.essay_id))
    elif essay.evidence_summary.strip() == essay.interpretation_summary.strip():
        blockers.append(_blocker("evidence_interpretation_not_separated", essay.essay_id))
    for claim in material_claims:
        if not claim.source_refs:
            blockers.append(_blocker("material_claim_source_missing", claim.claim_id, "source_refs"))
        if claim.claim_type == "allegation_requires_caution":
            if (
                not claim.source_refs
                or not claim.caution_note
                or not str(claim.review_metadata.get("caution_review_ref") or "").strip()
                or claim.evidence_confidence in {"unverified", "unsupported_blocked"}
            ):
                blockers.append(_blocker("unsupported_allegation", claim.claim_id, "claim_index"))
    return GovernanceResult(allowed=not blockers, blockers=tuple(_dedupe_blockers(blockers)))


def platform_adaptation_governance(adaptation: PlatformAdaptation) -> GovernanceResult:
    blockers = list(_forbidden_field_blockers(adaptation.to_dict(), adaptation.adaptation_id))
    if adaptation.brand_id != WTPU_BRAND_ID:
        blockers.append(_blocker("brand_mismatch", adaptation.adaptation_id, "brand_id", adaptation.brand_id))
    if adaptation.status != "draft":
        blockers.append(_blocker("adaptation_must_remain_draft", adaptation.adaptation_id, "status", adaptation.status))
    return GovernanceResult(allowed=not blockers, blockers=tuple(_dedupe_blockers(blockers)))


def correction_governance(
    correction: CorrectionUpdateRecord,
    *,
    expected_target_hash: str,
) -> GovernanceResult:
    blockers = list(_forbidden_field_blockers(correction.to_dict(), correction.correction_id))
    if correction.brand_id != WTPU_BRAND_ID:
        blockers.append(_blocker("brand_mismatch", correction.correction_id, "brand_id", correction.brand_id))
    if not correction.target_id:
        blockers.append(_blocker("correction_target_missing", correction.correction_id, "target_id"))
    if not correction.target_hash:
        blockers.append(_blocker("correction_target_hash_missing", correction.correction_id, "target_hash"))
    if expected_target_hash and correction.target_hash != expected_target_hash:
        blockers.append(_blocker("correction_target_hash_mismatch", correction.correction_id, "target_hash"))
    if not correction.reason:
        blockers.append(_blocker("correction_reason_missing", correction.correction_id, "reason"))
    return GovernanceResult(allowed=not blockers, blockers=tuple(_dedupe_blockers(blockers)))


def archive_readiness_governance(readiness_blockers: tuple[str, ...] | list[str]) -> GovernanceResult:
    blockers = tuple(_blocker(str(code), field="archive_readiness") for code in readiness_blockers)
    return GovernanceResult(allowed=not blockers, blockers=blockers)


def _forbidden_field_blockers(payload: Mapping[str, Any], entity_id: str) -> tuple[GovernanceBlocker, ...]:
    try:
        reject_forbidden_publication_fields(payload)
    except ValueError as exc:
        return (_blocker("publication_path_forbidden", entity_id, message=str(exc)),)
    return ()


def _blocker(code: str, entity_id: str = "", field: str = "", message: str = "") -> GovernanceBlocker:
    return GovernanceBlocker(code=code, entity_id=entity_id, field=field, message=message)


def _dedupe_blockers(blockers: list[GovernanceBlocker]) -> tuple[GovernanceBlocker, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[GovernanceBlocker] = []
    for blocker in blockers:
        key = (blocker.code, blocker.entity_id, blocker.field, blocker.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(blocker)
    return tuple(unique)
