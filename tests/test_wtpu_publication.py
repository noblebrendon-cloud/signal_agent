from __future__ import annotations

import json
from dataclasses import replace

import pytest

from signal_agent.formal_governance.hashing import stable_hash
from signal_agent.wtpu_publication.governance import canonical_essay_governance
from signal_agent.wtpu_publication.ledgers import (
    WTPUPublicationLedger,
    WTPULedgerIntegrityError,
    validate_wtpu_publication_ledger_records,
)
from signal_agent.wtpu_publication.models import (
    CanonicalCivicEssay,
    ClaimIndexEntry,
    IssueRecord,
    PlatformAdaptation,
    SourcePacket,
    SourceReference,
    WTPUModelValidationError,
)
from signal_agent.wtpu_publication.service import (
    WTPUPublicationCommandConflict,
    WTPUPublicationService,
    WTPUPublicationValidationError,
)
from signal_agent.wtpu_publication.taxonomy import (
    ESSAY_LIFECYCLE,
    FORBIDDEN_PUBLICATION_FIELDS,
    WTPU_BRAND_ID,
    WTPUTaxonomyError,
    validate_claim_type,
    validate_essay_lifecycle,
    validate_section_id,
)


def test_wtpu_taxonomy_is_fixed_and_release_fields_are_forbidden() -> None:
    assert validate_section_id("public_record") == "public_record"
    assert validate_claim_type("allegation_requires_caution") == "allegation_requires_caution"
    assert ESSAY_LIFECYCLE == (
        "draft",
        "review_requested",
        "reviewed",
        "canonical",
        "correction_pending",
        "corrected",
        "retracted",
        "superseded",
    )
    assert "release_eligible" in FORBIDDEN_PUBLICATION_FIELDS
    with pytest.raises(WTPUTaxonomyError):
        validate_section_id("national_release")
    with pytest.raises(WTPUTaxonomyError):
        validate_essay_lifecycle("released")


def test_issue_jurisdiction_scope_and_source_reference_hash_are_required() -> None:
    with pytest.raises(WTPUModelValidationError, match="jurisdiction"):
        IssueRecord(
            issue_id="issue.local",
            section_id="public_record",
            title="Local budget",
            jurisdiction="",
            scope="local",
        )
    with pytest.raises(WTPUModelValidationError, match="scope"):
        IssueRecord(
            issue_id="issue.state",
            section_id="public_record",
            title="State hearing",
            jurisdiction="Indiana",
            scope="",
        )
    with pytest.raises(WTPUModelValidationError, match="source_content_hash"):
        SourceReference(
            source_ref_id="src.missing_hash",
            source_type="public_record",
            locator="https://example.test/record",
            source_content_hash="",
        )
    with pytest.raises(WTPUModelValidationError, match="source_limitations"):
        SourcePacket(
            source_packet_id="packet.no_limits",
            title="No limits",
            source_refs=(_source_ref("src.no_limits"),),
            source_limitations=(),
        )


def test_wtpu_brand_isolation_and_forbidden_release_fields_fail_closed() -> None:
    with pytest.raises(WTPUModelValidationError, match="brand_mismatch"):
        IssueRecord(
            issue_id="issue.other_brand",
            section_id="public_record",
            title="Wrong brand",
            jurisdiction="Indiana",
            scope="state",
            brand_id="letters_of_light",
        )
    with pytest.raises(WTPUModelValidationError, match="release_eligible"):
        IssueRecord.from_dict(
            {
                "issue_id": "issue.release",
                "section_id": "public_record",
                "title": "Release field",
                "jurisdiction": "Indiana",
                "scope": "state",
                "release_eligible": False,
            }
        )
    with pytest.raises(WTPUModelValidationError, match="external_url"):
        PlatformAdaptation(
            adaptation_id="adapt.release",
            essay_id="essay.one",
            platform="internal-social-draft",
            adaptation_type="short_post",
            body="Internal draft only.",
            metadata={"external_url": "https://example.test/post"},
        )


def test_service_happy_path_ledger_projection_and_archive_ready(tmp_path) -> None:
    service, issue, packet, essay = _canonical_service_fixture(tmp_path)

    assert essay.status == "canonical"
    assert essay.approved_content_hash == essay.content_hash
    assert service.compute_archive_readiness(issue.issue_id).archive_ready is True

    validation = service.ledger.validate()
    assert validation["clean"] is True
    assert validation["event_count"] >= 8

    projection = service.projection()
    assert projection.issues[issue.issue_id].jurisdiction == "Indiana"
    assert projection.issues[issue.issue_id].scope == "state"
    assert packet.source_refs[0].source_content_hash.startswith("sha256:")
    assert projection.essay_history[essay.essay_id][0].status == "draft"
    assert projection.essay_history[essay.essay_id][-1].status == "canonical"
    assert projection.dashboard_summary()["canonical_essay_count"] == 1
    assert "release_eligible" not in json.dumps(projection.to_dict(), sort_keys=True)


def test_command_id_retries_are_idempotent_and_reuse_with_new_payload_fails(tmp_path) -> None:
    service = _service(tmp_path)
    service.create_section(command_id="section.public_record", section_id="public_record")
    issue = service.create_issue(
        command_id="issue.open_meetings",
        section_id="public_record",
        title="Open meetings",
        jurisdiction="Indiana",
        scope="state",
    )

    retry = service.create_issue(
        command_id="issue.open_meetings",
        section_id="public_record",
        title="Open meetings",
        jurisdiction="Indiana",
        scope="state",
    )
    assert retry.issue_id == issue.issue_id
    assert len(service.ledger.read_events()) == 2

    with pytest.raises(WTPUPublicationCommandConflict):
        service.create_issue(
            command_id="issue.open_meetings",
            section_id="public_record",
            title="Different issue",
            jurisdiction="Indiana",
            scope="state",
        )


def test_ledger_integrity_detects_hash_chain_tampering(tmp_path) -> None:
    service = _service(tmp_path)
    service.create_section(command_id="section.public_record", section_id="public_record")
    rows = service.ledger.read_records()
    tampered = [dict(rows[0])]
    tampered[0]["event_type"] = "issue_created"

    with pytest.raises(WTPULedgerIntegrityError):
        validate_wtpu_publication_ledger_records(tampered)


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda essay, packet: replace(essay, source_packet_ids=(), source_limitations=(), content_hash=""), "source_packet_missing"),
        (lambda essay, packet: _approved(replace(essay, source_limitations=(), content_hash="")), "source_limitations_missing"),
        (lambda essay, packet: replace(essay, reviewer_ref=""), "reviewer_missing"),
        (lambda essay, packet: replace(essay, approved_content_hash=stable_hash({"wrong": "hash"})), "approval_hash_mismatch"),
        (
            lambda essay, packet: _approved(
                replace(essay, claim_index=(_claim("claim.untyped", ""),), content_hash="")
            ),
            "material_claim_untyped",
        ),
        (
            lambda essay, packet: _approved(
                replace(
                    essay,
                    evidence_summary="Same summary.",
                    interpretation_summary="Same summary.",
                    content_hash="",
                )
            ),
            "evidence_interpretation_not_separated",
        ),
        (
            lambda essay, packet: _approved(
                replace(
                    essay,
                    claim_index=(
                        ClaimIndexEntry(
                            claim_id="claim.allegation",
                            claim_type="allegation_requires_caution",
                            text="An allegation requiring caution.",
                            source_refs=(),
                            evidence_confidence="unverified",
                            interpretation_status="needs_review",
                        ),
                    ),
                    content_hash="",
                )
            ),
            "unsupported_allegation",
        ),
    ],
)
def test_canonical_governance_blockers(mutator, expected_code) -> None:
    packet = _source_packet()
    essay = _approved(
        CanonicalCivicEssay(
            essay_id="essay.ready",
            issue_id="issue.ready",
            section_id="public_record",
            title="Ready essay",
            body="A source-grounded civic essay.",
            status="canonical",
            source_packet_ids=(packet.source_packet_id,),
            source_limitations=("Minutes may omit side conversations.",),
            claim_index=(_claim("claim.fact", "public_record_fact"),),
            evidence_summary="The minutes document the vote.",
            interpretation_summary="The vote is relevant to accountability analysis.",
            reviewer_ref="human:reviewer",
        )
    )

    result = canonical_essay_governance(mutator(essay, packet), {packet.source_packet_id: packet})
    assert expected_code in {blocker.code for blocker in result.blockers}


def test_service_approval_blocks_hash_mismatch_and_missing_source_packet(tmp_path) -> None:
    service, issue, packet, essay = _reviewed_service_fixture(tmp_path)

    with pytest.raises(WTPUPublicationValidationError) as mismatch:
        service.approve_canonical_essay(
            command_id="approve.bad_hash",
            essay_id=essay.essay_id,
            approved_content_hash=stable_hash({"not": "current"}),
            reviewer_ref="human:reviewer",
        )
    assert "approval_hash_mismatch" in {blocker.code for blocker in mismatch.value.blockers}

    service = _service(tmp_path / "missing-source")
    service.create_section(command_id="section.public_record", section_id="public_record")
    issue = service.create_issue(
        command_id="issue.no_source",
        section_id="public_record",
        title="No source",
        jurisdiction="Indiana",
        scope="state",
    )
    draft = service.create_essay_draft(
        command_id="essay.no_source",
        issue_id=issue.issue_id,
        title="No source essay",
        body="Needs a source packet.",
    )
    draft = service.add_claim_index_entry(
        command_id="claim.no_source",
        essay_id=draft.essay_id,
        claim=_claim("claim.no_source", "public_record_fact").to_dict(),
    )
    draft = service.set_evidence_interpretation_summary(
        command_id="summary.no_source",
        essay_id=draft.essay_id,
        evidence_summary="Evidence is described.",
        interpretation_summary="Interpretation is separate.",
    )
    draft = service.request_editorial_review(command_id="review.no_source", essay_id=draft.essay_id)
    draft = service.mark_reviewed(
        command_id="reviewed.no_source",
        essay_id=draft.essay_id,
        reviewer_ref="human:reviewer",
    )
    with pytest.raises(WTPUPublicationValidationError) as missing_source:
        service.approve_canonical_essay(
            command_id="approve.no_source",
            essay_id=draft.essay_id,
            approved_content_hash=draft.content_hash,
            reviewer_ref="human:reviewer",
        )
    assert "source_packet_missing" in {blocker.code for blocker in missing_source.value.blockers}


def test_review_and_correction_lifecycle_preserves_historical_canonical_content(tmp_path) -> None:
    service, issue, packet, essay = _canonical_service_fixture(tmp_path)
    assert [item.status for item in service.projection().essay_history[essay.essay_id]][:4] == [
        "draft",
        "draft",
        "draft",
        "draft",
    ]
    assert "review_requested" in [item.status for item in service.projection().essay_history[essay.essay_id]]
    assert "reviewed" in [item.status for item in service.projection().essay_history[essay.essay_id]]
    assert "canonical" in [item.status for item in service.projection().essay_history[essay.essay_id]]

    with pytest.raises(WTPUPublicationValidationError) as bad_target:
        service.create_correction_or_update(
            command_id="correction.bad_target_hash",
            target_type="essay",
            target_id=essay.essay_id,
            target_hash=stable_hash({"wrong": "target"}),
            correction_type="correction",
            reason="Wrong target hash.",
        )
    assert "correction_target_hash_mismatch" in {blocker.code for blocker in bad_target.value.blockers}

    pending = service.create_correction_or_update(
        command_id="correction.pending",
        target_type="essay",
        target_id=essay.essay_id,
        target_hash=essay.content_hash,
        correction_type="correction",
        reason="Needs factual correction review.",
        status="correction_pending",
        reviewer_ref="human:reviewer",
    )
    assert pending.target_hash == essay.content_hash
    readiness = service.compute_archive_readiness(issue.issue_id)
    assert readiness.archive_ready is False
    assert "correction_pending" in readiness.blockers

    corrected = service.create_correction_or_update(
        command_id="correction.corrected",
        target_type="essay",
        target_id=essay.essay_id,
        target_hash=essay.content_hash,
        correction_type="correction",
        reason="Correction entered.",
        status="corrected",
        reviewer_ref="human:reviewer",
    )
    assert corrected.status == "corrected"
    projection = service.projection()
    statuses = [item.status for item in projection.essay_history[essay.essay_id]]
    assert "canonical" in statuses
    assert statuses[-1] == "corrected"
    canonical_versions = [item for item in projection.essay_history[essay.essay_id] if item.status == "canonical"]
    assert canonical_versions[-1].approved_content_hash == essay.content_hash


def test_campaign_links_and_adaptation_drafts_do_not_gain_release_authority(tmp_path) -> None:
    service, issue, packet, essay = _canonical_service_fixture(tmp_path)
    link = service.create_campaign_link(
        command_id="campaign.link",
        issue_id=issue.issue_id,
        essay_id=essay.essay_id,
        campaign_id="social.campaign.123",
        campaign_hash=stable_hash({"campaign": "123"}),
    )
    adaptation = service.create_platform_adaptation_draft(
        command_id="adaptation.draft",
        essay_id=essay.essay_id,
        campaign_link_id=link.campaign_link_id,
        platform="internal_social_draft",
        adaptation_type="short_post",
        body="A draft adaptation for internal review.",
        source_refs=("src.minutes",),
        claim_ids=("claim.fact",),
    )

    assert adaptation.status == "draft"
    projection_json = json.dumps(service.projection().to_dict(), sort_keys=True)
    assert "release_eligible" not in projection_json
    assert "external_url" not in projection_json

    with pytest.raises(WTPUModelValidationError, match="publisher_config"):
        service.create_platform_adaptation_draft(
            command_id="adaptation.publisher_config",
            essay_id=essay.essay_id,
            platform="internal_social_draft",
            adaptation_type="short_post",
            body="Forbidden metadata.",
            metadata={"publisher_config": {"account": "nope"}},
        )


def _service(tmp_path) -> WTPUPublicationService:
    return WTPUPublicationService(path=tmp_path / "events.jsonl")


def _reviewed_service_fixture(tmp_path):
    service = _service(tmp_path)
    service.create_section(command_id="section.public_record", section_id="public_record")
    issue = service.create_issue(
        command_id="issue.open_meetings",
        section_id="public_record",
        title="Open meetings",
        jurisdiction="Indiana",
        scope="state",
        topic_tags=("meetings",),
    )
    packet = service.register_source_packet(
        command_id="source.minutes",
        title="Meeting minutes",
        source_refs=(_source_ref("src.minutes"),),
        source_limitations=("Minutes may omit side conversations.",),
        created_by="human:researcher",
    )
    essay = service.create_essay_draft(
        command_id="essay.draft",
        issue_id=issue.issue_id,
        title="Why open meetings matter",
        body="The civic record should stay inspectable.",
    )
    essay = service.attach_source_packet(
        command_id="essay.attach_source",
        essay_id=essay.essay_id,
        source_packet_id=packet.source_packet_id,
    )
    essay = service.add_claim_index_entry(
        command_id="essay.claim",
        essay_id=essay.essay_id,
        claim=_claim("claim.fact", "public_record_fact").to_dict(),
    )
    essay = service.set_evidence_interpretation_summary(
        command_id="essay.summary",
        essay_id=essay.essay_id,
        evidence_summary="The minutes document the public vote.",
        interpretation_summary="That vote supports an accountability analysis.",
    )
    essay = service.request_editorial_review(command_id="essay.review_requested", essay_id=essay.essay_id)
    essay = service.mark_reviewed(
        command_id="essay.reviewed",
        essay_id=essay.essay_id,
        reviewer_ref="human:reviewer",
        review_note="Evidence and interpretation are separated.",
    )
    return service, issue, packet, essay


def _canonical_service_fixture(tmp_path):
    service, issue, packet, essay = _reviewed_service_fixture(tmp_path)
    essay = service.approve_canonical_essay(
        command_id="essay.canonical",
        essay_id=essay.essay_id,
        approved_content_hash=essay.content_hash,
        reviewer_ref="human:reviewer",
        approval_ref="approval.internal.1",
    )
    return service, issue, packet, essay


def _source_ref(source_ref_id: str) -> SourceReference:
    return SourceReference(
        source_ref_id=source_ref_id,
        source_type="meeting_minutes",
        locator=f"file:///{source_ref_id}.pdf",
        source_content_hash=stable_hash({"source_ref_id": source_ref_id, "body": "meeting minutes"}),
        retrieved_at="2026-06-30T00:00:00Z",
        accessed_by="human:researcher",
        provenance_note="Fixture source snapshot.",
    )


def _source_packet() -> SourcePacket:
    return SourcePacket(
        source_packet_id="packet.minutes",
        title="Meeting minutes",
        source_refs=(_source_ref("src.minutes"),),
        source_limitations=("Minutes may omit side conversations.",),
    )


def _claim(claim_id: str, claim_type: str) -> ClaimIndexEntry:
    return ClaimIndexEntry(
        claim_id=claim_id,
        claim_type=claim_type,
        text="The meeting minutes document a public vote.",
        source_refs=("src.minutes",),
        evidence_confidence="direct_primary",
        interpretation_status="evidence_only",
    )


def _approved(essay: CanonicalCivicEssay) -> CanonicalCivicEssay:
    clean = replace(essay, content_hash="", approved_content_hash="")
    return replace(clean, approved_content_hash=clean.content_hash)
