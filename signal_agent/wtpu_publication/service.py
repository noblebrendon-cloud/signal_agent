from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

from signal_agent.formal_governance.hashing import stable_hash
from signal_agent.transport.ledgers import utc_now_iso

from .governance import (
    GovernanceBlocker,
    canonical_essay_governance,
    correction_governance,
    platform_adaptation_governance,
)
from .ledgers import WTPUPublicationLedger
from .models import (
    ArchiveDossierRecord,
    CampaignLink,
    CanonicalCivicEssay,
    ClaimIndexEntry,
    CorrectionUpdateRecord,
    IssueRecord,
    PlatformAdaptation,
    PublicationSection,
    SourcePacket,
    SourceReference,
    WTPUPublicationEvent,
    derive_wtpu_publication_id,
    reject_forbidden_publication_fields,
)
from .projection import ArchiveReadiness, WTPUPublicationProjection, replay_wtpu_publication_events
from .taxonomy import WTPU_BRAND_ID


class WTPUPublicationServiceError(RuntimeError):
    pass


class WTPUPublicationCommandConflict(WTPUPublicationServiceError):
    pass


class WTPUPublicationValidationError(WTPUPublicationServiceError):
    def __init__(self, message: str, blockers: tuple[GovernanceBlocker, ...] = ()) -> None:
        super().__init__(message)
        self.blockers = blockers


class WTPUPublicationService:
    """Internal command surface for WTPU civic publication records."""

    def __init__(
        self,
        *,
        ledger: WTPUPublicationLedger | None = None,
        root: str | Path | None = None,
        path: str | Path | None = None,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        if ledger is not None and (root is not None or path is not None):
            raise ValueError("wtpu_publication_service_accepts_ledger_or_root_path")
        self.clock = clock
        self.ledger = ledger or WTPUPublicationLedger(root=root, path=path, clock=clock)

    def create_section(
        self,
        *,
        command_id: str,
        section_id: str,
        display_name: str = "",
        description: str = "",
        actor_id: str = "",
    ) -> PublicationSection:
        now = self.clock()
        section = PublicationSection(
            section_id=section_id,
            display_name=display_name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="create_section",
            event_type="section_created",
            actor_id=actor_id,
            entity_id=section.section_id,
            entity_type="publication_section",
            section_id=section.section_id,
            metadata={"section": section.to_dict()},
            output_hash=stable_hash(section.to_dict()),
        )
        return PublicationSection.from_dict(event.metadata["section"])

    def create_issue(
        self,
        *,
        command_id: str,
        section_id: str,
        title: str,
        jurisdiction: str,
        scope: str,
        issue_id: str = "",
        topic_tags: tuple[str, ...] | list[str] = (),
        provenance_note: str = "",
        actor_id: str = "",
    ) -> IssueRecord:
        projection = self.projection()
        if section_id not in projection.sections:
            raise WTPUPublicationValidationError(f"wtpu_issue_missing_section:{section_id}")
        now = self.clock()
        issue = IssueRecord(
            issue_id=issue_id or derive_wtpu_publication_id("issue", section_id, title, jurisdiction, scope),
            section_id=section_id,
            title=title,
            jurisdiction=jurisdiction,
            scope=scope,
            topic_tags=tuple(topic_tags),
            provenance_note=provenance_note,
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="create_issue",
            event_type="issue_created",
            actor_id=actor_id,
            entity_id=issue.issue_id,
            entity_type="issue_record",
            section_id=issue.section_id,
            issue_id=issue.issue_id,
            metadata={"issue": issue.to_dict()},
            output_hash=stable_hash(issue.to_dict()),
        )
        return IssueRecord.from_dict(event.metadata["issue"])

    def register_source_packet(
        self,
        *,
        command_id: str,
        title: str,
        source_refs: tuple[SourceReference | Mapping[str, Any], ...] | list[SourceReference | Mapping[str, Any]],
        source_limitations: tuple[str, ...] | list[str],
        source_packet_id: str = "",
        created_by: str = "",
        provenance_note: str = "",
        actor_id: str = "",
    ) -> SourcePacket:
        now = self.clock()
        refs = tuple(item if isinstance(item, SourceReference) else SourceReference.from_dict(item) for item in source_refs)
        packet = SourcePacket(
            source_packet_id=source_packet_id
            or derive_wtpu_publication_id("source_packet", title, [item.to_dict() for item in refs]),
            title=title,
            source_refs=refs,
            source_limitations=tuple(source_limitations),
            created_by=created_by,
            provenance_note=provenance_note,
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="register_source_packet",
            event_type="source_packet_registered",
            actor_id=actor_id,
            entity_id=packet.source_packet_id,
            entity_type="source_packet",
            source_packet_id=packet.source_packet_id,
            metadata={"source_packet": packet.to_dict()},
            output_hash=packet.content_hash,
        )
        return SourcePacket.from_dict(event.metadata["source_packet"])

    def create_essay_draft(
        self,
        *,
        command_id: str,
        issue_id: str,
        title: str,
        body: str,
        essay_id: str = "",
        subtitle: str = "",
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        issue = self._require_issue(projection, issue_id)
        now = self.clock()
        essay = CanonicalCivicEssay(
            essay_id=essay_id or derive_wtpu_publication_id("essay", issue_id, title, body),
            issue_id=issue.issue_id,
            section_id=issue.section_id,
            title=title,
            subtitle=subtitle,
            body=body,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="create_essay_draft",
            event_type="essay_draft_created",
            actor_id=actor_id,
            entity_id=essay.essay_id,
            entity_type="canonical_civic_essay",
            section_id=essay.section_id,
            issue_id=essay.issue_id,
            essay_id=essay.essay_id,
            metadata={"essay": essay.to_dict()},
            output_hash=essay.content_hash,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def attach_source_packet(
        self,
        *,
        command_id: str,
        essay_id: str,
        source_packet_id: str,
        source_limitations: tuple[str, ...] | list[str] = (),
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        packet = self._require_source_packet(projection, source_packet_id)
        limitations = tuple(dict.fromkeys((*essay.source_limitations, *(source_limitations or packet.source_limitations))))
        updated = replace(
            essay,
            source_packet_ids=tuple(dict.fromkeys((*essay.source_packet_ids, source_packet_id))),
            source_limitations=limitations,
            content_hash="",
            updated_at=self.clock(),
        )
        event = self._append_essay_update(
            command_id=command_id,
            command_type="attach_source_packet",
            event_type="essay_source_packet_attached",
            essay=updated,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def add_claim_index_entry(
        self,
        *,
        command_id: str,
        essay_id: str,
        claim: ClaimIndexEntry | Mapping[str, Any],
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        if isinstance(claim, Mapping):
            claim_payload = dict(claim)
            claim_payload.setdefault("claim_id", derive_wtpu_publication_id("claim", essay_id, claim_payload))
            claim_entry = ClaimIndexEntry.from_dict(claim_payload)
        else:
            claim_entry = claim
        claims = list(essay.claim_index)
        claims = [item for item in claims if item.claim_id != claim_entry.claim_id]
        claims.append(claim_entry)
        updated = replace(
            essay,
            claim_index=tuple(claims),
            content_hash="",
            updated_at=self.clock(),
        )
        event = self._append_essay_update(
            command_id=command_id,
            command_type="add_claim_index_entry",
            event_type="essay_claim_index_entry_added",
            essay=updated,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def set_evidence_interpretation_summaries(
        self,
        *,
        command_id: str,
        essay_id: str,
        evidence_summary: str,
        interpretation_summary: str,
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        updated = replace(
            essay,
            evidence_summary=evidence_summary,
            interpretation_summary=interpretation_summary,
            content_hash="",
            updated_at=self.clock(),
        )
        event = self._append_essay_update(
            command_id=command_id,
            command_type="set_evidence_interpretation_summaries",
            event_type="essay_evidence_interpretation_summary_set",
            essay=updated,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def set_evidence_interpretation_summary(
        self,
        *,
        command_id: str,
        essay_id: str,
        evidence_summary: str,
        interpretation_summary: str,
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        return self.set_evidence_interpretation_summaries(
            command_id=command_id,
            essay_id=essay_id,
            evidence_summary=evidence_summary,
            interpretation_summary=interpretation_summary,
            actor_id=actor_id,
        )

    def request_editorial_review(
        self,
        *,
        command_id: str,
        essay_id: str,
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        if essay.status != "draft":
            raise WTPUPublicationValidationError(f"wtpu_review_request_requires_draft:{essay.status}")
        now = self.clock()
        updated = replace(essay, status="review_requested", review_requested_at=now, updated_at=now)
        event = self._append_essay_update(
            command_id=command_id,
            command_type="request_editorial_review",
            event_type="essay_review_requested",
            essay=updated,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def mark_reviewed(
        self,
        *,
        command_id: str,
        essay_id: str,
        reviewer_ref: str,
        review_note: str = "",
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        if essay.status != "review_requested":
            raise WTPUPublicationValidationError(f"wtpu_review_requires_requested:{essay.status}")
        if not str(reviewer_ref or "").strip():
            raise WTPUPublicationValidationError("wtpu_reviewer_ref_required")
        now = self.clock()
        updated = replace(
            essay,
            status="reviewed",
            reviewer_ref=reviewer_ref,
            reviewed_at=now,
            review_note=review_note,
            updated_at=now,
        )
        event = self._append_essay_update(
            command_id=command_id,
            command_type="mark_reviewed",
            event_type="essay_reviewed",
            essay=updated,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def approve_canonical_essay(
        self,
        *,
        command_id: str,
        essay_id: str,
        approved_content_hash: str,
        reviewer_ref: str = "",
        approval_ref: str = "",
        review_note: str = "",
        actor_id: str = "",
    ) -> CanonicalCivicEssay:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        if essay.status != "reviewed":
            raise WTPUPublicationValidationError(f"wtpu_canonical_approval_requires_reviewed:{essay.status}")
        candidate = replace(
            essay,
            status="canonical",
            reviewer_ref=reviewer_ref or essay.reviewer_ref,
            approved_content_hash=approved_content_hash,
            approval_ref=approval_ref,
            review_note=review_note or essay.review_note,
            updated_at=self.clock(),
        )
        result = canonical_essay_governance(candidate, projection.source_packets)
        if not result.allowed:
            raise WTPUPublicationValidationError("wtpu_canonical_approval_blocked", result.blockers)
        event = self._append_essay_update(
            command_id=command_id,
            command_type="approve_canonical_essay",
            event_type="essay_canonical_approved",
            essay=candidate,
            actor_id=actor_id,
        )
        return CanonicalCivicEssay.from_dict(event.metadata["essay"])

    def create_campaign_link(
        self,
        *,
        command_id: str,
        issue_id: str,
        essay_id: str,
        campaign_id: str,
        campaign_link_id: str = "",
        campaign_system: str = "social_orchestration",
        campaign_hash: str = "",
        source_brand_id: str = WTPU_BRAND_ID,
        relationship_type: str = "campaign_derivative",
        provenance_note: str = "",
        actor_id: str = "",
    ) -> CampaignLink:
        projection = self.projection()
        self._require_issue(projection, issue_id)
        essay = self._require_essay(projection, essay_id)
        if essay.issue_id != issue_id:
            raise WTPUPublicationValidationError(f"wtpu_campaign_link_issue_mismatch:{essay_id}:{issue_id}")
        if essay.status != "canonical":
            raise WTPUPublicationValidationError(f"wtpu_campaign_link_requires_canonical:{essay.status}")
        now = self.clock()
        link = CampaignLink(
            campaign_link_id=campaign_link_id
            or derive_wtpu_publication_id("campaign_link", issue_id, essay_id, campaign_id),
            issue_id=issue_id,
            essay_id=essay_id,
            campaign_id=campaign_id,
            campaign_system=campaign_system,
            campaign_hash=campaign_hash,
            source_brand_id=source_brand_id,
            relationship_type=relationship_type,
            provenance_note=provenance_note,
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="create_campaign_link",
            event_type="campaign_link_created",
            actor_id=actor_id,
            entity_id=link.campaign_link_id,
            entity_type="campaign_link",
            section_id=essay.section_id,
            issue_id=issue_id,
            essay_id=essay_id,
            metadata={"campaign_link": link.to_dict()},
            output_hash=stable_hash(link.to_dict()),
        )
        return CampaignLink.from_dict(event.metadata["campaign_link"])

    def create_platform_adaptation_draft(
        self,
        *,
        command_id: str,
        essay_id: str,
        platform: str,
        adaptation_type: str,
        body: str,
        adaptation_id: str = "",
        campaign_link_id: str = "",
        source_refs: tuple[str, ...] | list[str] = (),
        claim_ids: tuple[str, ...] | list[str] = (),
        risk_flags: tuple[str, ...] | list[str] = (),
        metadata: Mapping[str, Any] | None = None,
        actor_id: str = "",
    ) -> PlatformAdaptation:
        projection = self.projection()
        essay = self._require_essay(projection, essay_id)
        if campaign_link_id and campaign_link_id not in projection.campaign_links:
            raise WTPUPublicationValidationError(f"wtpu_adaptation_missing_campaign_link:{campaign_link_id}")
        now = self.clock()
        adaptation = PlatformAdaptation(
            adaptation_id=adaptation_id
            or derive_wtpu_publication_id("adaptation", essay_id, platform, adaptation_type, body),
            essay_id=essay_id,
            platform=platform,
            adaptation_type=adaptation_type,
            body=body,
            campaign_link_id=campaign_link_id,
            source_refs=tuple(source_refs),
            claim_ids=tuple(claim_ids),
            risk_flags=tuple(risk_flags),
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        result = platform_adaptation_governance(adaptation)
        if not result.allowed:
            raise WTPUPublicationValidationError("wtpu_adaptation_draft_blocked", result.blockers)
        event = self._append_event(
            command_id=command_id,
            command_type="create_platform_adaptation_draft",
            event_type="platform_adaptation_draft_created",
            actor_id=actor_id,
            entity_id=adaptation.adaptation_id,
            entity_type="platform_adaptation",
            section_id=essay.section_id,
            issue_id=essay.issue_id,
            essay_id=essay_id,
            adaptation_id=adaptation.adaptation_id,
            metadata={"adaptation": adaptation.to_dict()},
            output_hash=adaptation.content_hash,
        )
        return PlatformAdaptation.from_dict(event.metadata["adaptation"])

    def create_correction_or_update(
        self,
        *,
        command_id: str,
        target_type: str,
        target_id: str,
        target_hash: str,
        correction_type: str,
        reason: str,
        correction_id: str = "",
        status: str = "correction_pending",
        replacement_ref: str = "",
        visible_note: str = "",
        reviewer_ref: str = "",
        actor_id: str = "",
    ) -> CorrectionUpdateRecord:
        projection = self.projection()
        expected_hash = self._target_hash(projection, target_type, target_id)
        now = self.clock()
        correction = CorrectionUpdateRecord(
            correction_id=correction_id
            or derive_wtpu_publication_id("correction", target_type, target_id, target_hash, status, reason),
            target_type=target_type,
            target_id=target_id,
            target_hash=target_hash,
            correction_type=correction_type,
            reason=reason,
            status=status,
            replacement_ref=replacement_ref,
            visible_note=visible_note,
            reviewer_ref=reviewer_ref,
            created_at=now,
            updated_at=now,
        )
        result = correction_governance(correction, expected_target_hash=expected_hash)
        if not result.allowed:
            raise WTPUPublicationValidationError("wtpu_correction_blocked", result.blockers)
        event = self._append_event(
            command_id=command_id,
            command_type="create_correction_or_update",
            event_type="correction_update_created",
            actor_id=actor_id,
            entity_id=correction.correction_id,
            entity_type="correction_update",
            essay_id=target_id if target_type == "essay" else "",
            correction_id=correction.correction_id,
            metadata={"correction": correction.to_dict()},
            input_hash=target_hash,
            output_hash=correction.content_hash,
        )
        return CorrectionUpdateRecord.from_dict(event.metadata["correction"])

    def record_archive_dossier(
        self,
        *,
        command_id: str,
        title: str,
        issue_ids: tuple[str, ...] | list[str],
        dossier_id: str = "",
        curator_ref: str = "",
        provenance_note: str = "",
        actor_id: str = "",
    ) -> ArchiveDossierRecord:
        projection = self.projection()
        for issue_id in issue_ids:
            self._require_issue(projection, issue_id)
        readiness_blockers = tuple(
            blocker
            for issue_id in issue_ids
            for blocker in projection.archive_readiness(issue_id).blockers
        )
        essays = tuple(
            essay for essay in projection.essays.values() if essay.issue_id in set(issue_ids)
        )
        source_packet_ids = tuple(dict.fromkeys(packet_id for essay in essays for packet_id in essay.source_packet_ids))
        correction_ids = tuple(
            correction.correction_id
            for correction in projection.corrections.values()
            if correction.target_id in {essay.essay_id for essay in essays} or correction.target_id in set(issue_ids)
        )
        now = self.clock()
        dossier = ArchiveDossierRecord(
            dossier_id=dossier_id or derive_wtpu_publication_id("archive_dossier", title, tuple(issue_ids)),
            title=title,
            issue_ids=tuple(issue_ids),
            essay_ids=tuple(essay.essay_id for essay in essays),
            source_packet_ids=source_packet_ids,
            correction_ids=correction_ids,
            archive_status="archive_ready" if not readiness_blockers else "draft",
            readiness_blockers=readiness_blockers,
            curator_ref=curator_ref,
            provenance_note=provenance_note,
            created_at=now,
            updated_at=now,
        )
        event = self._append_event(
            command_id=command_id,
            command_type="record_archive_dossier",
            event_type="archive_dossier_recorded",
            actor_id=actor_id,
            entity_id=dossier.dossier_id,
            entity_type="archive_dossier",
            dossier_id=dossier.dossier_id,
            metadata={"dossier": dossier.to_dict()},
            output_hash=stable_hash(dossier.to_dict()),
        )
        return ArchiveDossierRecord.from_dict(event.metadata["dossier"])

    def compute_archive_readiness(self, issue_id: str) -> ArchiveReadiness:
        return self.projection().archive_readiness(issue_id)

    def projection(self) -> WTPUPublicationProjection:
        return replay_wtpu_publication_events(self.ledger.read_events(validate=True))

    def read_dashboard_projection(self) -> dict[str, Any]:
        return self.projection().dashboard_summary()

    def read_issue_projection(self, issue_id: str) -> dict[str, Any]:
        return self.projection().issue_summary(issue_id)

    def read_essay_projection(self, essay_id: str) -> dict[str, Any]:
        return self.projection().essay_summary(essay_id)

    def _append_essay_update(
        self,
        *,
        command_id: str,
        command_type: str,
        event_type: str,
        essay: CanonicalCivicEssay,
        actor_id: str,
    ) -> WTPUPublicationEvent:
        return self._append_event(
            command_id=command_id,
            command_type=command_type,
            event_type=event_type,
            actor_id=actor_id,
            entity_id=essay.essay_id,
            entity_type="canonical_civic_essay",
            section_id=essay.section_id,
            issue_id=essay.issue_id,
            essay_id=essay.essay_id,
            metadata={"essay": essay.to_dict()},
            output_hash=essay.content_hash,
        )

    def _append_event(
        self,
        *,
        command_id: str,
        command_type: str,
        event_type: str,
        metadata: Mapping[str, Any],
        actor_id: str = "",
        actor_type: str = "human",
        entity_id: str = "",
        entity_type: str = "",
        section_id: str = "",
        issue_id: str = "",
        source_packet_id: str = "",
        essay_id: str = "",
        adaptation_id: str = "",
        correction_id: str = "",
        dossier_id: str = "",
        input_hash: str = "",
        output_hash: str = "",
    ) -> WTPUPublicationEvent:
        command_id = _require_command_id(command_id)
        reject_forbidden_publication_fields(metadata)
        payload_hash = stable_hash(
            {
                "command_type": command_type,
                "command_id": command_id,
                "event_type": event_type,
                "metadata": _command_payload_material(dict(metadata)),
            }
        )
        existing = self._event_for_command(command_id)
        if existing is not None:
            if existing.command_payload_hash != payload_hash or existing.event_type != event_type:
                raise WTPUPublicationCommandConflict(f"wtpu_publication_command_id_conflict:{command_id}")
            return existing
        event = WTPUPublicationEvent(
            event_id=derive_wtpu_publication_id("event", event_type, command_id),
            event_type=event_type,
            occurred_at=self.clock(),
            actor_id=actor_id,
            actor_type=actor_type,
            command_id=command_id,
            command_payload_hash=payload_hash,
            entity_id=entity_id,
            entity_type=entity_type,
            section_id=section_id,
            issue_id=issue_id,
            source_packet_id=source_packet_id,
            essay_id=essay_id,
            adaptation_id=adaptation_id,
            correction_id=correction_id,
            dossier_id=dossier_id,
            input_hash=input_hash,
            output_hash=output_hash,
            metadata=dict(metadata),
        )
        self.ledger.append(event)
        return event

    def _event_for_command(self, command_id: str) -> WTPUPublicationEvent | None:
        matches = tuple(event for event in self.ledger.read_events(validate=True) if event.command_id == command_id)
        if len(matches) > 1:
            raise WTPUPublicationCommandConflict(f"wtpu_publication_command_event_conflict:{command_id}")
        return matches[0] if matches else None

    def _require_issue(self, projection: WTPUPublicationProjection, issue_id: str) -> IssueRecord:
        issue = projection.issues.get(issue_id)
        if issue is None:
            raise WTPUPublicationValidationError(f"wtpu_issue_missing:{issue_id}")
        return issue

    def _require_source_packet(self, projection: WTPUPublicationProjection, source_packet_id: str) -> SourcePacket:
        packet = projection.source_packets.get(source_packet_id)
        if packet is None:
            raise WTPUPublicationValidationError(f"wtpu_source_packet_missing:{source_packet_id}")
        return packet

    def _require_essay(self, projection: WTPUPublicationProjection, essay_id: str) -> CanonicalCivicEssay:
        essay = projection.essays.get(essay_id)
        if essay is None:
            raise WTPUPublicationValidationError(f"wtpu_essay_missing:{essay_id}")
        return essay

    def _target_hash(self, projection: WTPUPublicationProjection, target_type: str, target_id: str) -> str:
        if target_type == "essay":
            return self._require_essay(projection, target_id).content_hash
        if target_type == "source_packet":
            return self._require_source_packet(projection, target_id).content_hash
        if target_type == "adaptation":
            adaptation = projection.adaptations.get(target_id)
            if adaptation is None:
                raise WTPUPublicationValidationError(f"wtpu_adaptation_missing:{target_id}")
            return adaptation.content_hash
        raise WTPUPublicationValidationError(f"wtpu_correction_target_type_not_allowed:{target_type}")


def _require_command_id(command_id: str) -> str:
    normalized = str(command_id or "").strip()
    if not normalized:
        raise WTPUPublicationValidationError("wtpu_command_id_required")
    return normalized


def _command_payload_material(value: Any) -> Any:
    generated_fields = {
        "created_at",
        "updated_at",
        "audit_event_refs",
        "review_requested_at",
        "reviewed_at",
    }
    if isinstance(value, Mapping):
        return {
            str(key): _command_payload_material(item)
            for key, item in value.items()
            if str(key) not in generated_fields
        }
    if isinstance(value, (list, tuple)):
        return [_command_payload_material(item) for item in value]
    return value
