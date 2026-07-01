from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .models import (
    ArchiveDossierRecord,
    CampaignLink,
    CanonicalCivicEssay,
    CorrectionUpdateRecord,
    IssueRecord,
    PlatformAdaptation,
    PublicationSection,
    SourcePacket,
    WTPUPublicationEvent,
)
from .taxonomy import WTPU_BRAND_ID


class WTPUProjectionReplayError(RuntimeError):
    pass


class WTPUProjectionTransitionError(WTPUProjectionReplayError):
    pass


@dataclass(frozen=True)
class ArchiveReadiness:
    issue_id: str
    archive_ready: bool
    blockers: tuple[str, ...]
    essay_ids: tuple[str, ...]
    source_packet_ids: tuple[str, ...]
    correction_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "archive_ready": self.archive_ready,
            "blockers": list(self.blockers),
            "essay_ids": list(self.essay_ids),
            "source_packet_ids": list(self.source_packet_ids),
            "correction_ids": list(self.correction_ids),
        }


@dataclass(frozen=True)
class WTPUPublicationProjection:
    sections: dict[str, PublicationSection] = field(default_factory=dict)
    issues: dict[str, IssueRecord] = field(default_factory=dict)
    source_packets: dict[str, SourcePacket] = field(default_factory=dict)
    essays: dict[str, CanonicalCivicEssay] = field(default_factory=dict)
    campaign_links: dict[str, CampaignLink] = field(default_factory=dict)
    adaptations: dict[str, PlatformAdaptation] = field(default_factory=dict)
    corrections: dict[str, CorrectionUpdateRecord] = field(default_factory=dict)
    archive_dossiers: dict[str, ArchiveDossierRecord] = field(default_factory=dict)
    issue_history: dict[str, tuple[IssueRecord, ...]] = field(default_factory=dict)
    source_packet_history: dict[str, tuple[SourcePacket, ...]] = field(default_factory=dict)
    essay_history: dict[str, tuple[CanonicalCivicEssay, ...]] = field(default_factory=dict)
    campaign_link_history: dict[str, tuple[CampaignLink, ...]] = field(default_factory=dict)
    adaptation_history: dict[str, tuple[PlatformAdaptation, ...]] = field(default_factory=dict)
    correction_history: dict[str, tuple[CorrectionUpdateRecord, ...]] = field(default_factory=dict)
    lineage_refs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    command_event_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    command_payload_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": {key: value.to_dict() for key, value in self.sections.items()},
            "issues": {key: value.to_dict() for key, value in self.issues.items()},
            "source_packets": {key: value.to_dict() for key, value in self.source_packets.items()},
            "essays": {key: value.to_dict() for key, value in self.essays.items()},
            "campaign_links": {key: value.to_dict() for key, value in self.campaign_links.items()},
            "adaptations": {key: value.to_dict() for key, value in self.adaptations.items()},
            "corrections": {key: value.to_dict() for key, value in self.corrections.items()},
            "archive_dossiers": {key: value.to_dict() for key, value in self.archive_dossiers.items()},
            "issue_history": {
                key: [item.to_dict() for item in value] for key, value in self.issue_history.items()
            },
            "source_packet_history": {
                key: [item.to_dict() for item in value] for key, value in self.source_packet_history.items()
            },
            "essay_history": {
                key: [item.to_dict() for item in value] for key, value in self.essay_history.items()
            },
            "campaign_link_history": {
                key: [item.to_dict() for item in value] for key, value in self.campaign_link_history.items()
            },
            "adaptation_history": {
                key: [item.to_dict() for item in value] for key, value in self.adaptation_history.items()
            },
            "correction_history": {
                key: [item.to_dict() for item in value] for key, value in self.correction_history.items()
            },
            "lineage_refs": {key: list(value) for key, value in self.lineage_refs.items()},
            "command_event_ids": {key: list(value) for key, value in self.command_event_ids.items()},
            "command_payload_hashes": dict(self.command_payload_hashes),
            "dashboard": self.dashboard_summary(),
        }

    def dashboard_summary(self) -> dict[str, Any]:
        return {
            "brand_id": WTPU_BRAND_ID,
            "section_count": len(self.sections),
            "issue_count": len(self.issues),
            "source_packet_count": len(self.source_packets),
            "essay_count": len(self.essays),
            "canonical_essay_count": sum(1 for essay in self.essays.values() if essay.status == "canonical"),
            "review_requested_count": sum(1 for essay in self.essays.values() if essay.status == "review_requested"),
            "reviewed_count": sum(1 for essay in self.essays.values() if essay.status == "reviewed"),
            "correction_count": len(self.corrections),
            "adaptation_draft_count": sum(1 for item in self.adaptations.values() if item.status == "draft"),
            "archive_ready_issue_count": sum(
                1 for issue_id in self.issues if self.archive_readiness(issue_id).archive_ready
            ),
        }

    def issue_summary(self, issue_id: str) -> dict[str, Any]:
        issue = self.issues.get(issue_id)
        if issue is None:
            raise WTPUProjectionTransitionError(f"wtpu_issue_missing:{issue_id}")
        essays = [essay for essay in self.essays.values() if essay.issue_id == issue_id]
        corrections = [
            correction
            for correction in self.corrections.values()
            if correction.target_id in {essay.essay_id for essay in essays} or correction.target_id == issue_id
        ]
        readiness = self.archive_readiness(issue_id)
        return {
            "issue": issue.to_dict(),
            "essays": [essay.to_dict() for essay in essays],
            "source_packets": [
                packet.to_dict()
                for packet in self.source_packets.values()
                if packet.source_packet_id in issue.source_packet_ids
            ],
            "campaign_links": [
                link.to_dict() for link in self.campaign_links.values() if link.issue_id == issue_id
            ],
            "corrections": [correction.to_dict() for correction in corrections],
            "archive_readiness": readiness.to_dict(),
        }

    def essay_summary(self, essay_id: str) -> dict[str, Any]:
        essay = self.essays.get(essay_id)
        if essay is None:
            raise WTPUProjectionTransitionError(f"wtpu_essay_missing:{essay_id}")
        return {
            "essay": essay.to_dict(),
            "history": [item.to_dict() for item in self.essay_history.get(essay_id, ())],
            "source_packets": [
                self.source_packets[source_packet_id].to_dict()
                for source_packet_id in essay.source_packet_ids
                if source_packet_id in self.source_packets
            ],
            "campaign_links": [
                link.to_dict() for link in self.campaign_links.values() if link.essay_id == essay_id
            ],
            "adaptations": [
                item.to_dict() for item in self.adaptations.values() if item.essay_id == essay_id
            ],
            "corrections": [
                item.to_dict() for item in self.corrections.values() if item.target_id == essay_id
            ],
        }

    def archive_readiness(self, issue_id: str) -> ArchiveReadiness:
        issue = self.issues.get(issue_id)
        if issue is None:
            raise WTPUProjectionTransitionError(f"wtpu_issue_missing:{issue_id}")
        essays = tuple(essay for essay in self.essays.values() if essay.issue_id == issue_id)
        source_packet_ids = tuple(
            dict.fromkeys(source_packet_id for essay in essays for source_packet_id in essay.source_packet_ids)
        )
        correction_ids = tuple(
            correction.correction_id
            for correction in self.corrections.values()
            if correction.target_id in {essay.essay_id for essay in essays} or correction.target_id == issue_id
        )
        blockers: list[str] = []
        if not issue.jurisdiction:
            blockers.append("issue_jurisdiction_missing")
        if not issue.scope:
            blockers.append("issue_scope_missing")
        if not essays:
            blockers.append("canonical_essay_missing")
        if not any(essay.status == "canonical" for essay in essays):
            blockers.append("canonical_essay_not_approved")
        if any(essay.status == "correction_pending" for essay in essays):
            blockers.append("correction_pending")
        if not source_packet_ids:
            blockers.append("source_packet_missing")
        for source_packet_id in source_packet_ids:
            packet = self.source_packets.get(source_packet_id)
            if packet is None:
                blockers.append(f"source_packet_missing:{source_packet_id}")
            elif not packet.source_limitations:
                blockers.append(f"source_limitations_missing:{source_packet_id}")
        return ArchiveReadiness(
            issue_id=issue_id,
            archive_ready=not blockers,
            blockers=tuple(dict.fromkeys(blockers)),
            essay_ids=tuple(essay.essay_id for essay in essays),
            source_packet_ids=source_packet_ids,
            correction_ids=correction_ids,
        )


def replay_wtpu_publication_events(
    events: list[WTPUPublicationEvent] | tuple[WTPUPublicationEvent, ...],
) -> WTPUPublicationProjection:
    builder = _ProjectionBuilder()
    for event in events:
        builder.apply(event)
    return builder.projection()


class _ProjectionBuilder:
    def __init__(self) -> None:
        self.sections: dict[str, PublicationSection] = {}
        self.issues: dict[str, IssueRecord] = {}
        self.source_packets: dict[str, SourcePacket] = {}
        self.essays: dict[str, CanonicalCivicEssay] = {}
        self.campaign_links: dict[str, CampaignLink] = {}
        self.adaptations: dict[str, PlatformAdaptation] = {}
        self.corrections: dict[str, CorrectionUpdateRecord] = {}
        self.archive_dossiers: dict[str, ArchiveDossierRecord] = {}
        self.issue_history: dict[str, list[IssueRecord]] = {}
        self.source_packet_history: dict[str, list[SourcePacket]] = {}
        self.essay_history: dict[str, list[CanonicalCivicEssay]] = {}
        self.campaign_link_history: dict[str, list[CampaignLink]] = {}
        self.adaptation_history: dict[str, list[PlatformAdaptation]] = {}
        self.correction_history: dict[str, list[CorrectionUpdateRecord]] = {}
        self.lineage_refs: dict[str, list[str]] = {}
        self.command_event_ids: dict[str, list[str]] = {}
        self.command_payload_hashes: dict[str, str] = {}

    def apply(self, event: WTPUPublicationEvent) -> None:
        self._record_command(event)
        match event.event_type:
            case "section_created":
                self._section_created(event)
            case "issue_created":
                self._issue_recorded(event, require_new=True)
            case "source_packet_registered":
                self._source_packet_registered(event)
            case "essay_draft_created":
                self._essay_recorded(event, expected_status="draft", require_new=True)
            case "essay_source_packet_attached":
                self._essay_recorded(event)
            case "essay_claim_index_entry_added":
                self._essay_recorded(event)
            case "essay_evidence_interpretation_summary_set":
                self._essay_recorded(event)
            case "essay_review_requested":
                self._essay_recorded(event, expected_status="review_requested")
            case "essay_reviewed":
                self._essay_recorded(event, expected_status="reviewed")
            case "essay_canonical_approved":
                self._essay_recorded(event, expected_status="canonical")
            case "campaign_link_created":
                self._campaign_link_created(event)
            case "platform_adaptation_draft_created":
                self._adaptation_created(event)
            case "correction_update_created":
                self._correction_created(event)
            case "archive_dossier_recorded":
                self._archive_dossier_recorded(event)
            case _:
                raise WTPUProjectionTransitionError(f"unsupported_wtpu_publication_event:{event.event_type}")

    def projection(self) -> WTPUPublicationProjection:
        return WTPUPublicationProjection(
            sections=dict(self.sections),
            issues=dict(self.issues),
            source_packets=dict(self.source_packets),
            essays=dict(self.essays),
            campaign_links=dict(self.campaign_links),
            adaptations=dict(self.adaptations),
            corrections=dict(self.corrections),
            archive_dossiers=dict(self.archive_dossiers),
            issue_history={key: tuple(value) for key, value in self.issue_history.items()},
            source_packet_history={key: tuple(value) for key, value in self.source_packet_history.items()},
            essay_history={key: tuple(value) for key, value in self.essay_history.items()},
            campaign_link_history={key: tuple(value) for key, value in self.campaign_link_history.items()},
            adaptation_history={key: tuple(value) for key, value in self.adaptation_history.items()},
            correction_history={key: tuple(value) for key, value in self.correction_history.items()},
            lineage_refs={key: tuple(value) for key, value in self.lineage_refs.items()},
            command_event_ids={key: tuple(value) for key, value in self.command_event_ids.items()},
            command_payload_hashes=dict(self.command_payload_hashes),
        )

    def _record_command(self, event: WTPUPublicationEvent) -> None:
        if not event.command_id:
            return
        if not event.command_payload_hash:
            raise WTPUProjectionTransitionError(
                f"wtpu_publication_command_payload_hash_required:{event.command_id}"
            )
        existing_hash = self.command_payload_hashes.get(event.command_id)
        if existing_hash is not None and existing_hash != event.command_payload_hash:
            raise WTPUProjectionTransitionError(
                f"wtpu_publication_command_payload_hash_conflict:{event.command_id}"
            )
        self.command_payload_hashes[event.command_id] = event.command_payload_hash
        event_ids = self.command_event_ids.setdefault(event.command_id, [])
        if event.event_id not in event_ids:
            event_ids.append(event.event_id)

    def _section_created(self, event: WTPUPublicationEvent) -> None:
        section = PublicationSection.from_dict(_metadata_mapping(event, "section"))
        existing = self.sections.get(section.section_id)
        if existing is not None and existing.to_dict() != section.to_dict():
            raise WTPUProjectionTransitionError(f"wtpu_section_duplicate:{section.section_id}")
        self.sections[section.section_id] = section
        self._add_lineage(section.section_id, event.event_id)

    def _issue_recorded(self, event: WTPUPublicationEvent, *, require_new: bool = False) -> None:
        issue = IssueRecord.from_dict(_metadata_mapping(event, "issue"))
        if issue.section_id not in self.sections:
            raise WTPUProjectionTransitionError(f"wtpu_issue_missing_section:{issue.section_id}")
        if require_new and issue.issue_id in self.issues:
            raise WTPUProjectionTransitionError(f"wtpu_issue_duplicate:{issue.issue_id}")
        self.issues[issue.issue_id] = issue
        self.issue_history.setdefault(issue.issue_id, []).append(issue)
        self._add_lineage(issue.issue_id, issue.section_id, *issue.source_packet_ids, *issue.essay_ids)

    def _source_packet_registered(self, event: WTPUPublicationEvent) -> None:
        packet = SourcePacket.from_dict(_metadata_mapping(event, "source_packet"))
        existing = self.source_packets.get(packet.source_packet_id)
        if existing is not None and existing.content_hash != packet.content_hash:
            raise WTPUProjectionTransitionError(f"wtpu_source_packet_duplicate:{packet.source_packet_id}")
        self.source_packets[packet.source_packet_id] = packet
        self.source_packet_history.setdefault(packet.source_packet_id, []).append(packet)
        self._add_lineage(packet.source_packet_id, *(ref.source_ref_id for ref in packet.source_refs))

    def _essay_recorded(
        self,
        event: WTPUPublicationEvent,
        *,
        expected_status: str = "",
        require_new: bool = False,
    ) -> None:
        essay = CanonicalCivicEssay.from_dict(_metadata_mapping(event, "essay"))
        issue = self.issues.get(essay.issue_id)
        if issue is None:
            raise WTPUProjectionTransitionError(f"wtpu_essay_missing_issue:{essay.issue_id}")
        if essay.section_id != issue.section_id:
            raise WTPUProjectionTransitionError(f"wtpu_essay_section_mismatch:{essay.essay_id}")
        if require_new and essay.essay_id in self.essays:
            raise WTPUProjectionTransitionError(f"wtpu_essay_duplicate:{essay.essay_id}")
        if expected_status and essay.status != expected_status:
            raise WTPUProjectionTransitionError(
                f"wtpu_essay_status_mismatch:{essay.essay_id}:{essay.status}:{expected_status}"
            )
        for source_packet_id in essay.source_packet_ids:
            if source_packet_id not in self.source_packets:
                raise WTPUProjectionTransitionError(f"wtpu_essay_missing_source_packet:{source_packet_id}")
        self.essays[essay.essay_id] = essay
        self.essay_history.setdefault(essay.essay_id, []).append(essay)
        self.issues[issue.issue_id] = _issue_with_refs(
            issue,
            source_packet_ids=(*issue.source_packet_ids, *essay.source_packet_ids),
            essay_ids=(*issue.essay_ids, essay.essay_id),
            updated_at=event.occurred_at,
        )
        self.issue_history.setdefault(issue.issue_id, []).append(self.issues[issue.issue_id])
        self._add_lineage(essay.essay_id, essay.issue_id, *essay.source_packet_ids, *(claim.claim_id for claim in essay.claim_index))

    def _campaign_link_created(self, event: WTPUPublicationEvent) -> None:
        link = CampaignLink.from_dict(_metadata_mapping(event, "campaign_link"))
        if link.issue_id not in self.issues:
            raise WTPUProjectionTransitionError(f"wtpu_campaign_link_missing_issue:{link.issue_id}")
        if link.essay_id not in self.essays:
            raise WTPUProjectionTransitionError(f"wtpu_campaign_link_missing_essay:{link.essay_id}")
        if link.campaign_link_id in self.campaign_links:
            raise WTPUProjectionTransitionError(f"wtpu_campaign_link_duplicate:{link.campaign_link_id}")
        self.campaign_links[link.campaign_link_id] = link
        self.campaign_link_history.setdefault(link.campaign_link_id, []).append(link)
        issue = self.issues[link.issue_id]
        self.issues[issue.issue_id] = _issue_with_refs(
            issue,
            campaign_link_ids=(*issue.campaign_link_ids, link.campaign_link_id),
            updated_at=event.occurred_at,
        )
        self.issue_history.setdefault(issue.issue_id, []).append(self.issues[issue.issue_id])
        self._add_lineage(link.campaign_link_id, link.issue_id, link.essay_id, link.campaign_id)

    def _adaptation_created(self, event: WTPUPublicationEvent) -> None:
        adaptation = PlatformAdaptation.from_dict(_metadata_mapping(event, "adaptation"))
        if adaptation.essay_id not in self.essays:
            raise WTPUProjectionTransitionError(f"wtpu_adaptation_missing_essay:{adaptation.essay_id}")
        if adaptation.adaptation_id in self.adaptations:
            raise WTPUProjectionTransitionError(f"wtpu_adaptation_duplicate:{adaptation.adaptation_id}")
        if adaptation.campaign_link_id and adaptation.campaign_link_id not in self.campaign_links:
            raise WTPUProjectionTransitionError(
                f"wtpu_adaptation_missing_campaign_link:{adaptation.campaign_link_id}"
            )
        self.adaptations[adaptation.adaptation_id] = adaptation
        self.adaptation_history.setdefault(adaptation.adaptation_id, []).append(adaptation)
        if adaptation.campaign_link_id:
            link = self.campaign_links[adaptation.campaign_link_id]
            self.campaign_links[link.campaign_link_id] = replace(
                link,
                adaptation_ids=tuple(dict.fromkeys((*link.adaptation_ids, adaptation.adaptation_id))),
                updated_at=event.occurred_at,
            )
            self.campaign_link_history.setdefault(link.campaign_link_id, []).append(
                self.campaign_links[link.campaign_link_id]
            )
        self._add_lineage(adaptation.adaptation_id, adaptation.essay_id, adaptation.campaign_link_id, *adaptation.source_refs)

    def _correction_created(self, event: WTPUPublicationEvent) -> None:
        correction = CorrectionUpdateRecord.from_dict(_metadata_mapping(event, "correction"))
        if correction.correction_id in self.corrections:
            raise WTPUProjectionTransitionError(f"wtpu_correction_duplicate:{correction.correction_id}")
        target = self._target_hash(correction.target_type, correction.target_id)
        if target != correction.target_hash:
            raise WTPUProjectionTransitionError(f"wtpu_correction_target_hash_mismatch:{correction.target_id}")
        self.corrections[correction.correction_id] = correction
        self.correction_history.setdefault(correction.target_id, []).append(correction)
        if correction.target_type == "essay":
            essay = self.essays[correction.target_id]
            if correction.status in {"correction_pending", "corrected", "retracted", "superseded"}:
                updated = replace(essay, status=correction.status, updated_at=event.occurred_at)
                self.essays[essay.essay_id] = updated
                self.essay_history.setdefault(essay.essay_id, []).append(updated)
        self._add_lineage(correction.correction_id, correction.target_id, correction.replacement_ref)

    def _archive_dossier_recorded(self, event: WTPUPublicationEvent) -> None:
        dossier = ArchiveDossierRecord.from_dict(_metadata_mapping(event, "dossier"))
        for issue_id in dossier.issue_ids:
            if issue_id not in self.issues:
                raise WTPUProjectionTransitionError(f"wtpu_dossier_missing_issue:{issue_id}")
        self.archive_dossiers[dossier.dossier_id] = dossier
        self._add_lineage(dossier.dossier_id, *dossier.issue_ids, *dossier.essay_ids, *dossier.source_packet_ids)

    def _target_hash(self, target_type: str, target_id: str) -> str:
        if target_type == "essay":
            target = self.essays.get(target_id)
            if target is None:
                raise WTPUProjectionTransitionError(f"wtpu_correction_missing_target:{target_id}")
            return target.content_hash
        if target_type == "source_packet":
            target = self.source_packets.get(target_id)
            if target is None:
                raise WTPUProjectionTransitionError(f"wtpu_correction_missing_target:{target_id}")
            return target.content_hash
        if target_type == "campaign_link":
            target = self.campaign_links.get(target_id)
            if target is None:
                raise WTPUProjectionTransitionError(f"wtpu_correction_missing_target:{target_id}")
            return target.campaign_hash
        if target_type == "adaptation":
            target = self.adaptations.get(target_id)
            if target is None:
                raise WTPUProjectionTransitionError(f"wtpu_correction_missing_target:{target_id}")
            return target.content_hash
        raise WTPUProjectionTransitionError(f"wtpu_correction_target_type_not_allowed:{target_type}")

    def _add_lineage(self, entity_id: str, *refs: str) -> None:
        if not entity_id:
            return
        current = self.lineage_refs.setdefault(entity_id, [])
        for ref in refs:
            clean = str(ref or "").strip()
            if clean and clean not in current:
                current.append(clean)


def _metadata_mapping(event: WTPUPublicationEvent, key: str) -> Mapping[str, Any]:
    value = event.metadata.get(key)
    if not isinstance(value, Mapping):
        raise WTPUProjectionTransitionError(f"wtpu_publication_event_missing_{key}:{event.event_id}")
    return value


def _issue_with_refs(
    issue: IssueRecord,
    *,
    source_packet_ids: tuple[str, ...] = (),
    essay_ids: tuple[str, ...] = (),
    campaign_link_ids: tuple[str, ...] = (),
    updated_at: str = "",
) -> IssueRecord:
    return replace(
        issue,
        source_packet_ids=tuple(dict.fromkeys(source_packet_ids or issue.source_packet_ids)),
        essay_ids=tuple(dict.fromkeys(essay_ids or issue.essay_ids)),
        campaign_link_ids=tuple(dict.fromkeys(campaign_link_ids or issue.campaign_link_ids)),
        updated_at=updated_at or issue.updated_at,
    )
