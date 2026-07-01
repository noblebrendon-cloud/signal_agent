from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from app.letters_of_light.release_server import ReleaseRequestHandler, ReleaseServer
from signal_agent.formal_governance.hashing import stable_hash
from signal_agent.wtpu_publication.service import WTPUPublicationService
from signal_agent.wtpu_publication.taxonomy import EDITORIAL_SECTIONS


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def test_empty_dashboard_displays_fixed_sections_without_creating_ledger(tmp_state: Path) -> None:
    assert _ledger_snapshot(tmp_state) is None
    server, thread = _serve()

    try:
        html_status, html, _ = _request(server, "GET", "/wtpu-publication")
        api_status, _, payload = _request(server, "GET", "/api/wtpu-publication/sections")
    finally:
        _stop(server, thread)

    assert html_status == 200
    assert api_status == 200
    assert "No WTPU editorial ledger records exist yet." in html
    assert len(payload["sections"]) == 5
    assert [row["section_id"] for row in payload["sections"]] == list(EDITORIAL_SECTIONS)
    assert all(row["issue_count"] == 0 for row in payload["sections"])
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert _ledger_snapshot(tmp_state) is None


def test_wtpu_dashboard_routes_are_get_only_and_do_not_mutate_ledger(tmp_state: Path) -> None:
    ids = _populate_wtpu_fixture(tmp_state)
    before = _ledger_snapshot(tmp_state)
    assert before
    server, thread = _serve()
    paths = [
        "/wtpu-publication",
        "/api/wtpu-publication/dashboard",
        "/api/wtpu-publication/sections",
        "/api/wtpu-publication/sections/public_record",
        "/api/wtpu-publication/issues",
        f"/api/wtpu-publication/issues/{ids['issue_id']}",
        "/api/wtpu-publication/essays",
        f"/api/wtpu-publication/essays/{ids['essay_id']}",
        f"/api/wtpu-publication/source-packets/{ids['source_packet_id']}",
        f"/api/wtpu-publication/adaptations/{ids['adaptation_id']}",
        f"/api/wtpu-publication/corrections/{ids['correction_id']}",
        "/api/wtpu-publication/archive-readiness",
        f"/api/wtpu-publication/archive-readiness?issue_id={ids['issue_id']}",
        f"/api/wtpu-publication/history/essay/{ids['essay_id']}",
        f"/api/wtpu-publication/history/correction/{ids['essay_id']}",
    ]

    try:
        for path in paths:
            status, _text, payload = _request(server, "GET", path)
            assert status == 200
            if path.startswith("/api/"):
                assert payload["read_only"] is True
                assert payload["mutation_allowed"] is False
                assert payload["authority"] == {
                    "release": False,
                    "publish": False,
                    "schedule": False,
                    "export": False,
                    "approve": False,
                }
            assert _ledger_snapshot(tmp_state) == before

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _text, payload = _request(
                server,
                method,
                "/api/wtpu-publication/dashboard",
                body={"attempt": "mutate"},
            )
            assert status == 405
            assert payload["error"] == "wtpu_publication_read_only"
            assert payload["read_only"] is True
            assert payload["mutation_allowed"] is False
            assert _ledger_snapshot(tmp_state) == before
    finally:
        _stop(server, thread)


def test_dashboard_html_has_no_write_or_external_publication_controls(tmp_state: Path) -> None:
    ids = _populate_wtpu_fixture(tmp_state)
    before = _ledger_snapshot(tmp_state)
    server, thread = _serve()

    try:
        status, html, _ = _request(server, "GET", "/wtpu-publication")
    finally:
        _stop(server, thread)

    lower = html.lower()
    assert status == 200
    assert ids["source_hash"] in html
    assert "file:///src.minutes.pdf" in html
    assert "Editorial status is not release status" in html
    assert "Nothing in this dashboard grants publication authority" in html
    assert "<form" not in lower
    assert "<button" not in lower
    assert "data-action" not in lower
    assert "href=" not in lower
    assert "/api/approve" not in lower
    assert "/api/export" not in lower
    assert "/api/publish" not in lower
    assert "publish youtube" not in lower
    assert "oauth" not in lower
    assert "open platform" not in lower
    assert _ledger_snapshot(tmp_state) == before


def test_source_hash_blockers_corrections_and_brand_isolation_render(tmp_state: Path) -> None:
    ids = _populate_wtpu_fixture(tmp_state)
    before = _ledger_snapshot(tmp_state)
    server, thread = _serve()

    try:
        status, _text, source_payload = _request(
            server,
            "GET",
            f"/api/wtpu-publication/source-packets/{ids['source_packet_id']}",
        )
        archive_status, _archive_text, archive_payload = _request(
            server,
            "GET",
            f"/api/wtpu-publication/archive-readiness?issue_id={ids['issue_id']}",
        )
        correction_status, _correction_text, correction_payload = _request(
            server,
            "GET",
            f"/api/wtpu-publication/corrections/{ids['correction_id']}",
        )
        dashboard_status, _dashboard_text, dashboard_payload = _request(
            server,
            "GET",
            "/api/wtpu-publication/dashboard",
        )
    finally:
        _stop(server, thread)

    assert status == 200
    refs = source_payload["source_packet"]["source_refs"]
    assert refs[0]["source_content_hash"] == ids["source_hash"]
    assert refs[0]["locator"] == "file:///src.minutes.pdf"
    assert refs[0]["locator_rendering"] == "plain_text_only"
    assert "<a " not in json.dumps(source_payload).lower()

    assert archive_status == 200
    blockers = archive_payload["archive_readiness"][0]["blockers"]
    assert "canonical_essay_not_approved" in blockers

    assert correction_status == 200
    chain = correction_payload["correction_chain"]
    assert chain["target_id"] == ids["essay_id"]
    assert chain["hash_groups"][0]["target_hash"] == ids["essay_hash"]
    records = chain["hash_groups"][0]["records"]
    assert [record["status"] for record in records] == ["correction_pending", "corrected"]
    assert all("event_id" not in json.dumps(record) for record in records)

    assert dashboard_status == 200
    assert dashboard_payload["brand_id"] == "we_the_people_united"
    assert dashboard_payload["authority"]["release"] is False
    assert _ledger_snapshot(tmp_state) == before


def test_missing_wtpu_records_return_planned_errors_without_mutation(tmp_state: Path) -> None:
    _populate_wtpu_fixture(tmp_state)
    before = _ledger_snapshot(tmp_state)
    server, thread = _serve()

    try:
        cases = {
            "/api/wtpu-publication/issues/issue_missing": "wtpu_record_missing",
            "/api/wtpu-publication/sections/not_a_section": "wtpu_record_missing",
            "/api/wtpu-publication/source-packets/packet_missing": "wtpu_record_missing",
            "/api/wtpu-publication/history/not-a-type/record": "wtpu_request_invalid",
        }
        for path, error_code in cases.items():
            status, _text, payload = _request(server, "GET", path)
            expected = 400 if error_code == "wtpu_request_invalid" else 404
            assert status == expected
            assert payload["ok"] is False
            assert payload["error"] == error_code
            assert payload["read_only"] is True
            assert payload["mutation_allowed"] is False
            assert _ledger_snapshot(tmp_state) == before
    finally:
        _stop(server, thread)


def _populate_wtpu_fixture(root: Path) -> dict[str, str]:
    service = WTPUPublicationService(root=root)
    service.create_section(command_id="section.public_record", section_id="public_record")
    issue = service.create_issue(
        command_id="issue.open_meetings",
        section_id="public_record",
        title="Open meetings",
        jurisdiction="Indiana",
        scope="state",
        topic_tags=("meetings",),
    )
    source_hash = stable_hash({"source_ref_id": "src.minutes", "body": "meeting minutes"})
    packet = service.register_source_packet(
        command_id="source.minutes",
        title="Meeting minutes",
        source_refs=(
            {
                "source_ref_id": "src.minutes",
                "source_type": "meeting_minutes",
                "locator": "file:///src.minutes.pdf",
                "source_content_hash": source_hash,
                "retrieved_at": "2026-07-01T00:00:00Z",
                "accessed_by": "human:researcher",
                "provenance_note": "Fixture source snapshot.",
            },
        ),
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
        claim={
            "claim_id": "claim.fact",
            "claim_type": "public_record_fact",
            "text": "The meeting minutes document a public vote.",
            "source_refs": ("src.minutes",),
            "evidence_confidence": "direct_primary",
            "interpretation_status": "evidence_only",
        },
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
    )
    essay = service.approve_canonical_essay(
        command_id="essay.canonical",
        essay_id=essay.essay_id,
        approved_content_hash=essay.content_hash,
        reviewer_ref="human:reviewer",
        approval_ref="approval.internal.1",
    )
    service.create_campaign_link(
        command_id="campaign.link",
        issue_id=issue.issue_id,
        essay_id=essay.essay_id,
        campaign_id="social.campaign.123",
        campaign_hash=stable_hash({"campaign": "123"}),
    )
    adaptation = service.create_platform_adaptation_draft(
        command_id="adaptation.draft",
        essay_id=essay.essay_id,
        platform="internal_social_draft",
        adaptation_type="short_post",
        body="A draft adaptation for internal review.",
        source_refs=("src.minutes",),
        claim_ids=("claim.fact",),
    )
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
    service.create_correction_or_update(
        command_id="correction.corrected",
        target_type="essay",
        target_id=essay.essay_id,
        target_hash=essay.content_hash,
        correction_type="correction",
        reason="Correction entered.",
        status="corrected",
        reviewer_ref="human:reviewer",
    )
    return {
        "issue_id": issue.issue_id,
        "source_packet_id": packet.source_packet_id,
        "essay_id": essay.essay_id,
        "essay_hash": essay.content_hash,
        "adaptation_id": adaptation.adaptation_id,
        "correction_id": pending.correction_id,
        "source_hash": source_hash,
    }


def _serve() -> tuple[ReleaseServer, threading.Thread]:
    server = ReleaseServer(("127.0.0.1", 0), ReleaseRequestHandler)
    server.quiet = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server: ReleaseServer, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def _request(
    server: ReleaseServer,
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, str, dict]:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=encoded, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        payload = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else {}
        return response.status, raw, payload
    finally:
        conn.close()


def _ledger_snapshot(root: Path) -> bytes | None:
    path = root / "data" / "state" / "wtpu_publication" / "events.jsonl"
    return path.read_bytes() if path.exists() else None
