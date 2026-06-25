from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.media_opportunities.ledgers import MediaOpportunityLedgers
from signal_agent.media_opportunities.service import MediaOpportunityService


NOW = "2026-06-25T15:00:00Z"


def _clock() -> str:
    return NOW


class FakeGmailSource:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.mutation_calls: list[str] = []

    def messages_for_label(self, label: str, *, limit: int | None = None) -> list[dict]:
        selected = list(self.messages)
        if limit is not None:
            selected = selected[:limit]
        return selected

    def mutate(self) -> None:
        self.mutation_calls.append("mutate")


@pytest.fixture
def service(tmp_path: Path) -> MediaOpportunityService:
    return MediaOpportunityService(MediaOpportunityLedgers(tmp_path / "media", clock=_clock), clock=_clock)


def _message(**overrides: object) -> dict:
    payload = {
        "id": "msg-1",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "subject": "Podcast invitation: public work",
        "from": "Producer Person <producer@example.org>",
        "sender_name": "Producer Person",
        "text": (
            "Hello Brendon,\n\n"
            "Would you join our podcast for an interview?\n"
            "Outlet: Example Podcast\n"
            "Topic: grounded public identity\n"
            "Deadline: 2026-07-01\n"
        ),
    }
    payload.update(overrides)
    return payload


def test_labeled_email_ingestion_creates_captured_record(service: MediaOpportunityService) -> None:
    source = FakeGmailSource([_message()])

    result = service.ingest_gmail_label(label="Media Opportunity", source=source)

    assert result["clean"] is True
    assert result["created_count"] == 1
    opportunity_id = result["created"][0]["opportunity_id"]
    record = service.get_opportunity(opportunity_id)
    assert record.current_state == "captured"
    assert record.opportunity_type == "podcast_or_interview"
    assert record.relationship_classification == "unknown"
    assert record.outlet_or_organization == "Example Podcast"
    assert record.contact_or_source_name == "Producer Person"
    assert record.source_metadata["source_kind"] == "gmail"
    assert record.source_metadata["source_email_mutated"] is False


def test_repeated_ingestion_does_not_duplicate_records(service: MediaOpportunityService) -> None:
    source = FakeGmailSource([_message()])

    first = service.ingest_gmail_label(label="Media Opportunity", source=source)
    second = service.ingest_gmail_label(label="Media Opportunity", source=source)

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["skipped_count"] == 1
    assert len(service.opportunities()) == 1
    assert len(service.ledgers.read("gmail_intake_audit")) == 2


def test_missing_ambiguous_metadata_remains_unset_or_other(service: MediaOpportunityService) -> None:
    source = FakeGmailSource(
        [
            _message(
                id="msg-2",
                message_id="msg-2",
                thread_id="thread-2",
                subject="Quick question",
                sender_name=None,
                text="Hello, I wanted to ask about your work sometime.",
                **{"from": "someone@example.org"},
            )
        ]
    )

    result = service.ingest_gmail_label(label="Media Opportunity", source=source)
    record = service.get_opportunity(result["created"][0]["opportunity_id"])

    assert record.opportunity_type == "other"
    assert record.relationship_classification == "unknown"
    assert record.outlet_or_organization is None
    assert record.deadline is None


def test_private_email_fields_do_not_appear_in_sanitized_public_export(service: MediaOpportunityService) -> None:
    result = service.ingest_gmail_label(label="Media Opportunity", source=FakeGmailSource([_message()]))
    opportunity_id = result["created"][0]["opportunity_id"]
    service.transition_opportunity(opportunity_id, "qualified")
    service.transition_opportunity(opportunity_id, "response_ready")
    service.transition_opportunity(opportunity_id, "awaiting_outcome")
    approval = service.approve_public_reference(
        opportunity_id,
        published_url="https://independent.example.org/story",
        title="Independent story",
        outlet="Independent Example",
        author="Reporter",
        published_date="2026-07-20",
        coverage_type="article",
        short_description="Independent coverage of Brendon R. Coleman's public work.",
        substantially_about=True,
        verification_note="Public URL verified.",
        approved_by="operator-1",
        human_approved=True,
        relationship_classification="independent",
    )
    payload = json.loads(Path(approval["export"]["json_path"]).read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)

    assert "producer@example.org" not in rendered
    assert "Producer Person" not in rendered
    assert "msg-1" not in rendered
    assert "thread-1" not in rendered
    assert "Would you join our podcast" not in rendered


def test_no_source_email_mutation_occurs(service: MediaOpportunityService) -> None:
    source = FakeGmailSource([_message()])

    service.ingest_gmail_label(label="Media Opportunity", source=source)

    assert source.mutation_calls == []


def test_generated_artifacts_match_manual_intake_structure(service: MediaOpportunityService) -> None:
    result = service.ingest_gmail_label(label="Media Opportunity", source=FakeGmailSource([_message()]))
    record = service.get_opportunity(result["created"][0]["opportunity_id"])
    links = record.artifact_links

    assert set(links) == {
        "opportunity_markdown",
        "response_draft_markdown",
        "facts_and_links_markdown",
        "evidence_checklist_markdown",
        "record_json",
    }
    for path in links.values():
        assert Path(path).exists()
    opportunity_md = Path(links["opportunity_markdown"]).read_text(encoding="utf-8")
    assert "Source: Gmail label intake. Human qualification still required." in opportunity_md
    assert "Gmail-derived private intake." in opportunity_md
