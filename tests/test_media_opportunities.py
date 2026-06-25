from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.media_opportunities.ledgers import MediaOpportunityLedgers
from signal_agent.media_opportunities.models import PUBLIC_EXPORT_KEYS, transition_allowed
from signal_agent.media_opportunities.service import (
    MediaOpportunityError,
    MediaOpportunityService,
    generate_response_draft,
    sanitized_public_reference,
)


NOW = "2026-06-25T12:00:00Z"


def _clock() -> str:
    return NOW


@pytest.fixture
def service(tmp_path: Path) -> MediaOpportunityService:
    return MediaOpportunityService(MediaOpportunityLedgers(tmp_path / "media", clock=_clock), clock=_clock)


def _opportunity(service: MediaOpportunityService, *, relationship: str = "unknown", suffix: str = "") -> dict:
    return service.create_opportunity(
        opportunity_type="podcast_or_interview",
        original_request_text=f"Would Brendon join a podcast conversation about grounded public work? {suffix}".strip(),
        outlet_or_organization="Example Podcast",
        contact_or_source_name="Producer",
        originating_url_or_source_ref="https://example.org/invite",
        topic_or_subject="Grounded public identity",
        deadline="2026-07-01",
        relationship_classification=relationship,
        visibility="private",
        notes="Private scheduling note",
    )


def _awaiting_outcome(
    service: MediaOpportunityService,
    *,
    relationship: str = "independent",
    suffix: str = "",
) -> str:
    opportunity_id = _opportunity(service, relationship=relationship, suffix=suffix)["opportunity"]["opportunity_id"]
    service.transition_opportunity(opportunity_id, "qualified")
    service.transition_opportunity(opportunity_id, "response_ready")
    service.transition_opportunity(opportunity_id, "awaiting_outcome")
    return opportunity_id


def _approval_kwargs() -> dict:
    return {
        "published_url": "https://independent.example.org/story/brendon-profile",
        "title": "Profile of Brendon R. Coleman",
        "outlet": "Independent Example",
        "author": "Reporter Name",
        "published_date": "2026-07-20",
        "coverage_type": "article",
        "short_description": "Independent profile of Brendon R. Coleman and his public work.",
        "substantially_about": True,
        "verification_note": "Public URL reviewed by operator.",
        "evidence": ("Outlet page captured",),
        "approved_by": "operator-1",
        "human_approved": True,
        "relationship_classification": "independent",
    }


def test_valid_state_transitions() -> None:
    assert transition_allowed("captured", "qualified") is True
    assert transition_allowed("qualified", "response_ready") is True
    assert transition_allowed("response_ready", "awaiting_outcome") is True
    assert transition_allowed("awaiting_outcome", "published_candidate") is True
    assert transition_allowed("published_candidate", "independently_verified") is True
    assert transition_allowed("independently_verified", "approved_for_public_reference") is True


def test_invalid_transition_rejected(service: MediaOpportunityService) -> None:
    opportunity_id = _opportunity(service)["opportunity"]["opportunity_id"]

    with pytest.raises(MediaOpportunityError, match="captured->approved_for_public_reference"):
        service.transition_opportunity(opportunity_id, "approved_for_public_reference")


def test_required_fields_for_approval(service: MediaOpportunityService) -> None:
    opportunity_id = _awaiting_outcome(service)
    kwargs = _approval_kwargs()
    kwargs["published_url"] = ""

    with pytest.raises(MediaOpportunityError, match="published_url_required"):
        service.approve_public_reference(opportunity_id, **kwargs)


def test_self_published_and_insufficient_independence_rejected(service: MediaOpportunityService) -> None:
    self_id = _awaiting_outcome(service, relationship="self")
    kwargs = _approval_kwargs()
    kwargs["relationship_classification"] = "self"

    with pytest.raises(MediaOpportunityError, match="independent_relationship_required"):
        service.approve_public_reference(self_id, **kwargs)

    independent_id = _awaiting_outcome(service, relationship="independent", suffix="owned url case")
    kwargs = _approval_kwargs()
    kwargs["published_url"] = "https://brendonrcoleman.com/essays/example/"

    with pytest.raises(MediaOpportunityError, match="published_url_is_owned_or_self_published"):
        service.approve_public_reference(independent_id, **kwargs)

    kwargs = _approval_kwargs()
    kwargs["paid_placement"] = True

    with pytest.raises(MediaOpportunityError, match="paid_placement_not_independent"):
        service.approve_public_reference(independent_id, **kwargs)

    insufficient_id = _awaiting_outcome(service, relationship="affiliated", suffix="terminal independence case")
    service.transition_opportunity(insufficient_id, "insufficient_independence")

    with pytest.raises(MediaOpportunityError, match="media_reference_approval_state_required:insufficient_independence"):
        service.approve_public_reference(insufficient_id, **_approval_kwargs())


def test_sanitized_public_export_excludes_private_fields(service: MediaOpportunityService) -> None:
    opportunity_id = _awaiting_outcome(service)
    result = service.approve_public_reference(opportunity_id, **_approval_kwargs())
    export_path = Path(result["export"]["json_path"])
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert set(payload.keys()) == set(PUBLIC_EXPORT_KEYS)
    rendered = json.dumps(payload, sort_keys=True)
    assert "Producer" not in rendered
    assert "Would Brendon join" not in rendered
    assert "Private scheduling note" not in rendered
    assert "contact_or_source_name" not in rendered
    assert sanitized_public_reference(service.get_opportunity(opportunity_id)) == payload


def test_intake_artifact_creation(service: MediaOpportunityService) -> None:
    opportunity = _opportunity(service)["opportunity"]
    links = opportunity["artifact_links"]

    expected = {
        "opportunity_markdown",
        "response_draft_markdown",
        "facts_and_links_markdown",
        "evidence_checklist_markdown",
        "record_json",
    }
    assert set(links) == expected
    for path in links.values():
        assert Path(path).exists()

    draft = Path(links["response_draft_markdown"]).read_text(encoding="utf-8")
    assert "DRAFT - DO NOT SEND AUTOMATICALLY." in draft
    assert "## Topic Angles" in draft


def test_deterministic_response_draft_generation(service: MediaOpportunityService) -> None:
    opportunity = _opportunity(service)["opportunity"]
    record = service.get_opportunity(opportunity["opportunity_id"])

    first = generate_response_draft(record, service.identity_packet)
    second = generate_response_draft(record, service.identity_packet)

    assert first == second
    assert "Canonical Bio" in first
    assert "Public Links" in first
