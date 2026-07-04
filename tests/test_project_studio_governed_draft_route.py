from __future__ import annotations

import json
import threading
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

import pytest

from app.letters_of_light import release_server
from app.letters_of_light import creation_manager
from app.letters_of_light.contract import LetterOfLight
from app.letters_of_light.project_studio import create_project, import_asset, project_dir, project_payload
from app.letters_of_light.production_derivative_promotion import (
    PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY,
    PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY,
    source_letter_body_hash,
)
from app.letters_of_light.release_server import ReleaseRequestHandler, ReleaseServer, _render_page
from app.letters_of_light.source_grounded_drafting import (
    SOURCE_GROUNDED_ACCEPTANCE_INDEX_KEY,
    SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED,
    SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE,
    SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY,
    SOURCE_GROUNDED_DRAFTING_METADATA_KEY,
)
from app.letters_of_light.source_grounded_prose_apply import CandidateEnvelopeSigner
from app.letters_of_light.source_grounded_prose_candidates import (
    ProseCandidateSegmentAnnotation,
    SourceGroundedProseCandidateProviderOutput,
)
from signal_agent.governed_publishing import (
    CanonicalContentNode,
    ContentHorizonProposalCreateRequest,
    ContentHorizonProposalPromotionRequest,
    ContentHorizonProposalRetirementRequest,
    ContentHorizonProposalReviewRequest,
    ContentJob,
    GovernedPublishingLedger,
    PublicationLedgerEvent,
    TimingWindow,
    create_content_horizon_proposal,
    promote_content_horizon_proposal_to_draft_candidate,
    retire_content_horizon_proposal,
    review_content_horizon_proposal,
)


NOW = "2026-06-29T00:00:00Z"
HTTP_TEST_TIMEOUT_SECONDS = 15


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _fake_success_pipeline_factory(prefix: str = "governed-route-letter"):
    counter = {"value": 0}

    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        counter["value"] += 1
        letter_id = f"{prefix}-{counter['value']}"
        root = Path(__import__("os").environ["SIGNAL_AGENT_ROOT"])
        letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            title=theme,
            text=manual_text or "",
            lifecycle_state="registered",
            evaluation={"decision": "accept", "total": 27, "audio_alignment": 4},
            created_at=NOW,
            updated_at=NOW,
            metadata={},
        )
        if progress_callback:
            progress_callback(
                {
                    "letter_id": letter_id,
                    "lifecycle_state": "draft",
                    "event_type": "LetterDraftCreated",
                    "timestamp": NOW,
                    "summary": {},
                }
            )
            progress_callback(
                {
                    "letter_id": letter_id,
                    "lifecycle_state": "registered",
                    "event_type": "LETTER_CREATED",
                    "timestamp": NOW,
                    "summary": {"letter_id": letter_id},
                }
            )
        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        _write_json(letter_dir / "routing.json", {})
        _write_json(letter_dir / "interaction.json", {})
        return letter

    fake_pipeline.counter = counter  # type: ignore[attr-defined]
    return fake_pipeline


def _ledger(tmp_state: Path) -> GovernedPublishingLedger:
    return GovernedPublishingLedger(
        root=tmp_state / "data" / "state" / "governed_publishing",
        clock=lambda: NOW,
    )


def _project_with_source(tmp_state: Path) -> tuple[dict, dict]:
    source = tmp_state / "route-source.md"
    source.write_text("Project source excerpt for governed route.", encoding="utf-8")
    project = create_project(title="Governed Draft Route Project", brand_id="brendon_r_coleman")
    asset = import_asset(project["project_id"], source_path=str(source))
    return project, asset


def _append_node(ledger: GovernedPublishingLedger, project: dict, asset: dict) -> CanonicalContentNode:
    node = CanonicalContentNode(
        node_id="node.route.001",
        brand_id="brendon_r_coleman",
        brand_version="1",
        source_hash="sha256:route-source",
        source_refs=(project["project_id"], asset["asset_id"]),
        canonical_title="Governed route source",
        project_id=project["project_id"],
        source_asset_ids=(asset["asset_id"],),
        lineage_refs=("source:route-root",),
        created_at=NOW,
    )
    ledger.append(
        PublicationLedgerEvent(
            event_id="event.route.node",
            event_type="canonical_node_created",
            occurred_at=NOW,
            actor_id="operator.route",
            actor_type="operator",
            node_id=node.node_id,
            metadata={"node": node.to_dict()},
        )
    )
    return node


def _create_proposal(
    ledger: GovernedPublishingLedger,
    node: CanonicalContentNode,
    asset: dict,
    *,
    promote: bool = True,
    retire: bool = False,
    suffix: str = "001",
    destination_brand_ref: str = "brendon_r_coleman",
    destination_surface_ref: str = "internal_drafting_surface",
    content_job: ContentJob = ContentJob.CLARIFICATION,
    horizon_class: str = "near_term_follow_up",
    thesis_or_claim: str = "A governed promoted proposal can open an editable source-selected Letter.",
    source_support_refs: tuple[str, ...] | None = None,
    source_snapshot_ref: str | None = None,
    promotion_ref: str = "draft-intent:primary",
):
    proposal = create_content_horizon_proposal(
        ledger,
        ContentHorizonProposalCreateRequest(
            command_id=f"cmd.route.create.{suffix}",
            canonical_node_id=node.node_id,
            origin_brand_ref="brendon_r_coleman",
            destination_brand_ref=destination_brand_ref,
            content_job=content_job,
            horizon_class=horizon_class,
            intended_audience="Project Studio operators",
            destination_surface_ref=destination_surface_ref,
            thesis_or_claim=thesis_or_claim,
            source_support_refs=source_support_refs or (node.node_id, asset["asset_id"]),
            reason_now="Phase 1J connects the governed handoff to Project Studio.",
            timing_window=TimingWindow(label="near_term_follow_up", review_date="2026-07-06"),
            review_date="2026-07-06",
            dependency_refs=("source_selection",),
            proposed_next_action="Open the governed drafting brief in Project Studio.",
            proposal_intent_ref=f"proposal-intent:route:{suffix}",
            source_snapshot_ref=source_snapshot_ref or f"snapshot:route:{suffix}",
            actor_ref="operator.route",
            actor_type="operator",
            occurred_at=NOW,
        ),
    ).proposal
    if not promote:
        return proposal
    review_content_horizon_proposal(
        ledger,
        ContentHorizonProposalReviewRequest(
            command_id=f"cmd.route.review.{suffix}",
            proposal_id=proposal.proposal_id,
            expected_current_state="proposed",
            review_outcome="ready_for_draft",
            reviewer_ref="human.route",
            reviewer_type="human",
            review_ref="review:route:ready",
            reason="source grounded enough for drafting",
            occurred_at=NOW,
        ),
    )
    promoted = promote_content_horizon_proposal_to_draft_candidate(
        ledger,
        ContentHorizonProposalPromotionRequest(
            command_id=f"cmd.route.promote.{suffix}",
            proposal_id=proposal.proposal_id,
            expected_current_state="reviewed_ready_for_draft",
            promotion_ref=promotion_ref,
            actor_ref="operator.route",
            actor_type="operator",
            reason="ready for Project Studio handoff",
            occurred_at=NOW,
        ),
    ).proposal
    if retire:
        promoted = retire_content_horizon_proposal(
            ledger,
            ContentHorizonProposalRetirementRequest(
                command_id=f"cmd.route.retire.{suffix}",
                proposal_id=promoted.proposal_id,
                expected_current_state="promoted_to_draft_candidate",
                reason="superseded before discovery",
                actor_ref="operator.route",
                actor_type="operator",
                occurred_at=NOW,
            ),
        ).proposal
    return promoted


def _selected_passage(asset: dict) -> dict:
    return {
        "asset_id": asset["asset_id"],
        "source_asset_id": asset["asset_id"],
        "passage_id": "route-passage-001",
        "page_number": 1,
        "passage_index": 1,
        "heading": "Route passage",
        "classification": "passage",
        "source_char_range": {},
        "raw_fragment_refs": [],
        "text": "Project source excerpt for governed route.",
    }


def _serve():
    server = ReleaseServer(("127.0.0.1", 0), ReleaseRequestHandler)
    server.quiet = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post_json(server: ReleaseServer, path: str, body: dict) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=HTTP_TEST_TIMEOUT_SECONDS)
    try:
        conn.request(
            "POST",
            path,
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        conn.close()


def _get_json(server: ReleaseServer, path: str) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=HTTP_TEST_TIMEOUT_SECONDS)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        conn.close()


def _context_path(project_id: str, proposal_id: str = "", draft_intent_ref: str = "draft-intent:primary") -> str:
    query = urlencode({"proposal_id": proposal_id, "draft_intent_ref": draft_intent_ref})
    return f"/api/projects/{project_id}/governed-drafts/context?{query}"


def _proposals_path(project_id: str, **params: str) -> str:
    query = urlencode({key: value for key, value in params.items() if value})
    suffix = f"?{query}" if query else ""
    return f"/api/projects/{project_id}/governed-drafts/proposals{suffix}"


def _open_body(proposal_id: str, asset: dict, *, draft_intent_ref: str = "draft-intent:primary") -> dict:
    return {
        "proposal_id": proposal_id,
        "draft_intent_ref": draft_intent_ref,
        "selected_passages": [_selected_passage(asset)],
        "working_title": "Governed route working title",
        "writer_note": "Keep source provenance visible.",
        "actor_ref": "operator.route",
    }


def _outline_preview_body(
    parent_letter_id: str,
    asset: dict,
    *,
    selected_passages: list[dict] | None = None,
    preview_intent_ref: str = "outline-preview:intent:primary",
    writer_note: str = "",
    format_intent: str = "",
) -> dict:
    selected = [_selected_passage(asset)] if selected_passages is None else selected_passages
    return {
        "parent_letter_id": parent_letter_id,
        "selected_source_asset_ids": [asset["asset_id"]] if selected else [],
        "selected_passages": selected,
        "preview_intent_ref": preview_intent_ref,
        "writer_note": writer_note,
        "format_intent": format_intent,
        "actor_ref": "operator.route",
    }


def _outline_acceptance_body(parent_letter_id: str, asset: dict, preview: dict, **kwargs: object) -> dict:
    body = _outline_preview_body(parent_letter_id, asset, **kwargs)
    body["preview_id"] = preview["preview_id"]
    return body


class RouteProseGenerationResult:
    def __init__(self, value: object) -> None:
        self.value = value
        self.receipt = SimpleNamespace(
            model_dump=lambda mode="json": {
                "provider": "fake",
                "model": "fake-phase3d",
                "schema_name": "SourceGroundedProseCandidateProviderOutput",
                "timestamp": NOW,
                "cost_status": "unavailable",
            }
        )


class RouteProseGenerator:
    def __init__(self, output: SourceGroundedProseCandidateProviderOutput) -> None:
        self.output = output
        self.calls = 0
        self.kwargs: dict[str, Any] = {}

    def generate(self, prompt: str, schema: type, **kwargs: object):
        assert prompt
        self.calls += 1
        self.kwargs = dict(kwargs)
        return RouteProseGenerationResult(schema.model_validate(self.output))


def _route_prose_provider_output(asset: dict, outline_section_id: str, **overrides: object) -> SourceGroundedProseCandidateProviderOutput:
    payload: dict[str, Any] = {
        "candidate_text": "The selected passage supports a careful draft candidate while keeping provenance visible.",
        "section_id": outline_section_id,
        "segment_annotations": [
            ProseCandidateSegmentAnnotation(
                segment_id="segment-route-1",
                segment_index=0,
                text_span="sentence:1",
                classification="observation",
                supporting_source_refs=[asset["asset_id"]],
                supporting_passage_refs=["route-passage-001"],
                support_status="supported",
            )
        ],
        "warnings": ["source_refs_not_fact_verification"],
        "used_source_refs": [asset["asset_id"]],
        "used_passage_refs": ["route-passage-001"],
        "output_classification_summary": ["observation"],
        "model_metadata": {"request_label": "phase3d-route-test", "api_key": "must-not-leak"},
    }
    payload.update(overrides)
    return SourceGroundedProseCandidateProviderOutput.model_validate(payload)


def _install_route_prose_provider(
    monkeypatch: pytest.MonkeyPatch,
    output: SourceGroundedProseCandidateProviderOutput,
) -> RouteProseGenerator:
    generator = RouteProseGenerator(output)
    monkeypatch.setattr(
        release_server,
        "_resolve_source_grounded_prose_provider",
        lambda: (generator, object(), object()),
    )
    monkeypatch.setenv("SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY", "phase3d-test-signing-material")
    monkeypatch.setenv("SOURCE_GROUNDED_CANDIDATE_SIGNER_ID", "phase3d-test")
    return generator


def _accepted_scaffold_for_prose_route(
    server: ReleaseServer,
    project: dict,
    asset: dict,
    proposal_id: str,
) -> dict:
    _, opened = _post_json(
        server,
        f"/api/projects/{project['project_id']}/governed-drafts/open",
        _open_body(proposal_id, asset),
    )
    _, preview = _post_json(
        server,
        f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
        _outline_preview_body(opened["letter_id"], asset),
    )
    _, accepted = _post_json(
        server,
        f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
        _outline_acceptance_body(opened["letter_id"], asset, preview),
    )
    return {
        "opened": opened,
        "preview": preview,
        "accepted": accepted,
        "scaffold_letter_id": accepted["child_letter_id"],
        "outline_section_id": preview["outline_sections"][0]["item_id"],
    }


def _prose_candidate_body(scaffold: dict, asset: dict, **overrides: object) -> dict:
    body: dict[str, Any] = {
        "accepted_scaffold_letter_id": scaffold["scaffold_letter_id"],
        "accepted_outline_section_id": scaffold["outline_section_id"],
        "selected_source_asset_ids": [asset["asset_id"]],
        "selected_source_passage_refs": ["route-passage-001"],
        "candidate_intent_ref": "candidate-intent:route",
        "requested_length_or_format": "section_paragraph",
        "writer_instruction": "Keep provenance visible.",
        "actor_ref": "operator.route",
    }
    body.update(overrides)
    return body


def _fake_production_derivative_pipeline(tmp_state: Path):
    calls: list[dict[str, Any]] = []

    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        requested_letter_id: str | None = None,
        initial_metadata: dict | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        del seed, progress_callback
        calls.append(
            {
                "theme": theme,
                "manual_text": manual_text,
                "requested_letter_id": requested_letter_id,
                "initial_metadata": initial_metadata,
            }
        )
        letter_id = requested_letter_id or f"unexpected-production-derivative-{len(calls)}"
        letter_dir = tmp_state / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            title=theme,
            text=manual_text or "",
            lifecycle_state="draft",
            created_at=NOW,
            updated_at=NOW,
            metadata=dict(initial_metadata or {}),
        )
        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        return letter

    fake_pipeline.calls = calls  # type: ignore[attr-defined]
    return fake_pipeline


def _production_derivative_source_fixture(tmp_state: Path) -> dict[str, Any]:
    project, asset = _project_with_source(tmp_state)
    source_letter_id = "governed_route_source_001"
    source_text = "Exact governed route source body for production derivative."
    metadata = {
        "project_id": project["project_id"],
        "brand_id": "brendon_r_coleman",
        "brand_version": "1",
        "parent_root_letter_id": "root-route-letter",
        "governed_handoff_id": "handoff.route.001",
        "governed_handoff": {
            "handoff_id": "handoff.route.001",
            "governed_drafting_brief_id": "drafting_brief.route.001",
            "proposal_id": "proposal.route.001",
            "canonical_node_id": "node.route.001",
            "source_snapshot_ref": "snapshot:route:001",
            "source_support_refs": ["node.route.001", asset["asset_id"]],
            "destination_brand_ref": "brendon_r_coleman",
            "authority": {
                "approval": False,
                "package_readiness": False,
                "release_eligibility": False,
                "schedule": False,
                "export": False,
                "publication": False,
                "queue": False,
                "platform_action": False,
                "oauth": False,
            },
            "source_grounding": {
                "source_snapshot_ref": "snapshot:route:001",
                "source_support_refs": ["node.route.001", asset["asset_id"]],
            },
        },
        "source_snapshot_ref": "snapshot:route:001",
        "source_support_refs": ["node.route.001", asset["asset_id"]],
        "source_asset_ids": [asset["asset_id"]],
        "selected_source_passages": [_selected_passage(asset)],
        "release_eligible": False,
        "approval_status": "unapproved",
        "review_status": "unreviewed",
        "publication_state": "not_started",
    }
    letter = {
        "letter_id": source_letter_id,
        "artifact_type": "letter_of_light",
        "theme": "governed route source",
        "title": "Governed Route Source",
        "text": source_text,
        "lifecycle_state": "draft",
        "evaluation": {"decision": "not_evaluated", "total": 0, "audio_alignment": 0},
        "metadata": metadata,
    }
    source_dir = tmp_state / "data" / "state" / "letters_of_light" / source_letter_id
    _write_json(source_dir / "letter.json", letter)
    _write_json(source_dir / "manifest.json", letter)
    return {
        "project": project,
        "asset": asset,
        "source_letter_id": source_letter_id,
        "source_text": source_text,
        "source_path": source_dir / "letter.json",
    }


def _production_derivative_candidate_body(fixture: dict[str, Any], **overrides: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "expected_source_body_hash": source_letter_body_hash(fixture["source_text"]),
        "promotion_intent_ref": "production-derivative:intent:route",
        "destination_brand_id": "brendon_r_coleman",
        "operator_ref": "operator.route",
        "target_theme": "route production derivative",
        "operator_note": "route test",
    }
    body.update(overrides)
    return body


def _production_derivative_candidate_path(fixture: dict[str, Any]) -> str:
    return (
        f"/api/projects/{fixture['project']['project_id']}/governed-drafts/"
        f"{fixture['source_letter_id']}/production-derivative-candidate"
    )


def _production_derivative_apply_path(fixture: dict[str, Any]) -> str:
    return (
        f"/api/projects/{fixture['project']['project_id']}/governed-drafts/"
        f"{fixture['source_letter_id']}/production-derivative-apply"
    )


def _letter_payload(tmp_state: Path, letter_id: str) -> dict:
    return json.loads(
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / letter_id
            / "letter.json"
        ).read_text(encoding="utf-8")
    )


def _project_file_payload(project_id: str) -> dict:
    return json.loads((project_dir(project_id) / "project.json").read_text(encoding="utf-8"))


def test_ui_html_includes_governed_draft_panel_and_blocks_empty_action() -> None:
    html = _render_page()
    panel = html.split('id="governed-draft-panel"', 1)[1].split('id="source-preview"', 1)[0]

    assert "Open Governed Draft" in panel
    assert "Check Proposal" in panel
    assert "Open Existing Draft" in panel
    assert "Find Governed Proposal" in panel
    assert "Source-Grounded Outline" in panel
    assert "Preview Grounded Outline" in panel
    assert "Accept Outline into Child Draft" in panel
    assert "Open Existing Child Draft" in panel
    assert "Grounded Prose Candidate" in panel
    assert "Generate Grounded Candidate" in panel
    assert "Apply Candidate to Child Draft" in panel
    assert "Open Existing Applied Draft" in panel
    assert "Production Derivative" in panel
    assert "Validate Production Derivative" in panel
    assert "Create Production Derivative" in panel
    assert "Actionable" in html
    assert "Needs Attention" in html
    assert "/governed-drafts/proposals" in html
    assert "/governed-drafts/context" in html
    assert "/governed-drafts/open" in html
    assert "/governed-drafts/outline-preview" in html
    assert "/governed-drafts/outline-acceptance" in html
    assert "/governed-drafts/prose-candidate" in html
    assert "/governed-drafts/prose-apply" in html
    assert "/production-derivative-candidate" in html
    assert "/production-derivative-apply" in html
    assert "This opens an editable Project Studio draft." in panel
    assert "This creates an editable scaffold-only child draft." in panel
    assert "This generates a draft candidate for review." in panel
    assert "This creates a separate production derivative for normal pipeline processing." in panel
    assert "It does not approve, release, export, schedule, publish, or grant platform authority." in panel
    assert "not independent fact verification" in panel
    assert "Check Proposal before opening; source passages are still required." in html
    assert 'id="governed-open-draft" type="button" disabled' in panel
    assert 'id="outline-preview-action" type="button" disabled' in panel
    assert 'id="outline-accept-action" type="button" disabled' in panel
    assert 'id="prose-generate-action" type="button" disabled' in panel
    assert 'id="prose-apply-action" type="button" disabled' in panel
    assert 'id="production-derivative-validate" type="button" disabled' in panel
    assert 'id="production-derivative-create" type="button" disabled' in panel
    assert "governedPreviewIsFresh" in html
    assert "invalidateGovernedPreview" in html
    assert "outlinePreviewIsFresh" in html
    assert "invalidateOutlinePreview" in html
    assert "proseCandidateIsFresh" in html
    assert "invalidateProseCandidate" in html
    assert "productionDerivativeCandidateIsFresh" in html
    assert "invalidateProductionDerivative" in html
    assert "data-governed-select-proposal" in html
    assert "governedProposalId.value = button.dataset.governedSelectProposal" in html
    assert "promote-render" not in panel
    assert "/api/export" not in panel
    assert "/api/publish" not in panel


def test_ui_changing_proposal_or_draft_intent_invalidates_prior_preview_state() -> None:
    html = _render_page()

    assert 'governedProposalId.addEventListener("input", invalidateGovernedPreview)' in html
    assert 'governedDraftIntent.addEventListener("input", () =>' in html
    assert "resetGovernedDiscovery();" in html
    assert 'governedPreviewKey === governedInputKey()' in html
    assert "!governedPreviewIsFresh() || !governedPreview.governed_brief_ready" in html
    assert "outlinePreviewKeyValue === outlinePreviewKey()" in html
    assert 'outlinePreviewIntent.addEventListener("input", invalidateOutlinePreview)' in html
    assert 'outlineFormatIntent.addEventListener("input", invalidateOutlinePreview)' in html
    assert 'outlineWriterNote.addEventListener("input", invalidateOutlinePreview)' in html
    assert "Preview is stale. Generate a new grounded outline before accepting it." in html
    assert "Candidate is stale. Generate a new grounded candidate before applying it." in html
    assert 'proseCandidateIntent.addEventListener("input", invalidateProseCandidate)' in html
    assert 'proseFormatConstraint.addEventListener("change", invalidateProseCandidate)' in html
    assert 'proseWriterInstruction.addEventListener("input", invalidateProseCandidate)' in html
    assert 'proseScaffoldLetter.addEventListener("change", invalidateProseCandidate)' in html
    assert 'proseOutlineSection.addEventListener("change", invalidateProseCandidate)' in html
    assert "selectedPassages.set(id, passage);" in html
    assert "invalidateOutlinePreview();" in html


def test_ui_production_derivative_panel_has_no_release_or_platform_controls() -> None:
    html = _render_page()
    panel = html.split('id="production-derivative-panel"', 1)[1].split('id="source-preview"', 1)[0]

    assert "Validate Production Derivative" in panel
    assert "Create Production Derivative" in panel
    for forbidden in (
        "Approve",
        "Export",
        "Schedule",
        "Publish",
        "OAuth",
        "Queue",
        "Platform",
        "Release Candidate",
    ):
        assert f">{forbidden}<" not in panel
    assert "/api/approve" not in panel
    assert "/api/export" not in panel
    assert "/api/publish" not in panel
    assert "promote-render" not in panel


def test_ui_stale_outline_preview_wording_and_acceptance_state() -> None:
    html = _render_page()

    stale_copy = "Preview is stale. Generate a new grounded outline before accepting it."
    assert stale_copy in html
    assert "let outlinePreviewStale = false;" in html
    assert "if (outlinePreview && outlinePreview.ready) outlinePreviewStale = true;" in html
    assert "} else if (outlinePreviewStale || (outlinePreview && !previewFresh)) {" in html
    assert "outlinePreviewStatus.textContent = stale_copy" not in html
    assert "outlineAcceptActionBtn.disabled = outlineAcceptanceInFlight || !previewReady || childAvailable;" in html
    assert "outlinePreviewActionBtn.disabled = outlinePreviewInFlight || !hasParent || !hasSelectedPassages || !hasIntent;" in html


def test_ui_all_preview_defining_inputs_mark_outline_preview_stale() -> None:
    html = _render_page()

    assert 'outlinePreviewIntent.addEventListener("input", invalidateOutlinePreview)' in html
    assert 'outlineFormatIntent.addEventListener("input", invalidateOutlinePreview)' in html
    assert 'outlineWriterNote.addEventListener("input", invalidateOutlinePreview)' in html
    assert 'governedProposalId.addEventListener("input", invalidateGovernedPreview)' in html
    assert 'governedDraftIntent.addEventListener("input", () =>' in html
    assert "selectedPassages.set(id, passage);" in html
    assert "selectedPassages = new Map();" in html
    assert "outlinePreviewKey()" in html
    assert "parent ? parent.letter_id : \"\"" in html
    assert "selectedPassageKey()" in html
    assert "outlinePreviewIntent.value.trim()" in html
    assert "outlineWriterNote.value.trim()" in html
    assert "outlineFormatIntent.value.trim()" in html


def test_ui_fresh_outline_preview_clears_stale_warning() -> None:
    html = _render_page()

    assert "outlinePreviewInFlight = true;" in html
    assert "outlinePreviewStale = false;" in html
    assert "outlinePreview = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/outline-preview`, outlineRequestBody(parent));" in html
    assert "outlinePreviewKeyValue = outlinePreviewKey();" in html
    assert "workspaceStatusEl.textContent = outlinePreview.ready ? \"Source-grounded outline preview ready\" : \"Source-grounded outline preview blocked\";" in html


def test_production_derivative_candidate_route_is_signed_and_non_mutating(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_TTL_SECONDS", "120")
    fixture = _production_derivative_source_fixture(tmp_state)
    source_before = fixture["source_path"].read_text(encoding="utf-8")
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["validation_state"] == "valid"
    assert payload["promotion_id"].startswith("production_derivative_promotion.")
    assert payload["target_letter_id"].startswith("production_derivative_")
    assert payload["source_body_hash"] == source_letter_body_hash(fixture["source_text"])
    assert payload["lineage_summary"]["governed_handoff_ids"] == ["handoff.route.001"]
    assert payload["authority_notice"].startswith("This creates a separate production derivative")

    envelope = payload["candidate_envelope"]
    envelope_payload = envelope["payload"]
    assert envelope_payload["project_id"] == fixture["project"]["project_id"]
    assert envelope_payload["destination_project_id"] == fixture["project"]["project_id"]
    assert envelope_payload["source_letter_id"] == fixture["source_letter_id"]
    assert envelope_payload["source_body_hash"] == source_letter_body_hash(fixture["source_text"])
    assert envelope_payload["destination_brand_id"] == "brendon_r_coleman"
    assert envelope_payload["operator_ref"] == "operator.route"
    assert envelope_payload["promotion_intent_ref"] == "production-derivative:intent:route"
    assert envelope_payload["target_letter_id"] == payload["target_letter_id"]
    issued = datetime.fromisoformat(envelope_payload["issued_at"])
    expires = datetime.fromisoformat(envelope_payload["expires_at"])
    assert int((expires - issued).total_seconds()) == 120

    project = project_payload(fixture["project"]["project_id"])
    assert PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY not in project
    assert not (tmp_state / "data" / "state" / "letters_of_light" / payload["target_letter_id"]).exists()
    assert creation_manager.list_creation_jobs() == []
    assert fixture["source_path"].read_text(encoding="utf-8") == source_before


def test_production_derivative_candidate_requires_own_signing_key_without_fallback(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", raising=False)
    monkeypatch.setenv("SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY", "must-not-be-used")
    fixture = _production_derivative_source_fixture(tmp_state)
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 503
    assert payload["status"] == "provider_not_authorized"
    assert "production_derivative_promotion_envelope_signing_key_not_configured" in payload["error"]
    assert "candidate_envelope" not in payload
    project = project_payload(fixture["project"]["project_id"])
    assert PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY not in project


def test_production_derivative_apply_route_creates_target_and_retries_idempotently(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_production_derivative_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    fixture = _production_derivative_source_fixture(tmp_state)
    source_before = fixture["source_path"].read_text(encoding="utf-8")
    server, thread = _serve()

    try:
        _, candidate = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
        apply_body = {
            "candidate_envelope": candidate["candidate_envelope"],
            "expected_source_body_hash": candidate["source_body_hash"],
            "promotion_intent_ref": "production-derivative:intent:route",
            "operator_ref": "operator.route",
            "operator_note": "create route derivative",
        }
        first_status, first = _post_json(server, _production_derivative_apply_path(fixture), apply_body)
        finished = creation_manager.wait_for_creation_job(first["creation_job_id"], timeout=5)
        second_status, second = _post_json(server, _production_derivative_apply_path(fixture), apply_body)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first_status == 201
    assert second_status == 200
    assert first["validation_state"] == "applied"
    assert second["validation_state"] == "already_promoted"
    assert second["target_letter_id"] == first["target_letter_id"]
    assert second["creation_job_id"] == first["creation_job_id"]
    assert finished is not None
    assert finished["status"] == "succeeded"
    assert len(fake_pipeline.calls) == 1  # type: ignore[attr-defined]
    assert fake_pipeline.calls[0]["manual_text"] == fixture["source_text"]  # type: ignore[attr-defined]
    assert fake_pipeline.calls[0]["requested_letter_id"] == first["target_letter_id"]  # type: ignore[attr-defined]
    assert fixture["source_path"].read_text(encoding="utf-8") == source_before

    target = _letter_payload(tmp_state, first["target_letter_id"])
    assert target["text"] == fixture["source_text"]
    assert target["parent_letter_id"] == fixture["source_letter_id"]
    assert target["lifecycle_state"] == "draft"
    metadata = target["metadata"]
    assert metadata[PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY]["promotion_id"] == first["promotion_id"]
    assert metadata["release_eligible"] is False
    assert metadata["approval_status"] == "unapproved"
    assert metadata["publication_state"] == "not_started"
    assert all(value is False for value in metadata["authority"].values())
    combined = json.dumps(target, sort_keys=True)
    for forbidden in ("release_state", "scheduled_at", "exported_at", "published_at", "platform_state", "oauth_state"):
        assert forbidden not in combined

    project = project_payload(fixture["project"]["project_id"])
    assert project[PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY][first["promotion_id"]]["target_letter_id"] == first["target_letter_id"]


def test_production_derivative_apply_rejects_operator_mismatch_and_empty_operator(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    fixture = _production_derivative_source_fixture(tmp_state)
    server, thread = _serve()

    try:
        _, candidate = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
        base = {
            "candidate_envelope": candidate["candidate_envelope"],
            "expected_source_body_hash": candidate["source_body_hash"],
            "promotion_intent_ref": "production-derivative:intent:route",
        }
        empty_status, empty = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {**base, "operator_ref": ""},
        )
        mismatch_status, mismatch = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {**base, "operator_ref": "operator.other"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert empty_status == 400
    assert empty["status"] == "invalid_request"
    assert "operator_ref is required" in empty["error"]
    assert mismatch_status == 400
    assert mismatch["status"] == "invalid_request"
    assert "candidate_envelope_operator_ref_mismatch" in mismatch["error"]


def test_production_derivative_apply_rejects_expired_stale_and_mismatched_envelopes(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    fixture = _production_derivative_source_fixture(tmp_state)
    server, thread = _serve()

    try:
        _, candidate = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
        envelope_payload = dict(candidate["candidate_envelope"]["payload"])
        expired_payload = {
            **envelope_payload,
            "issued_at": "2000-01-01T00:00:00+00:00",
            "expires_at": "2000-01-01T00:00:01+00:00",
        }
        expired = release_server._seal_production_derivative_promotion_envelope(expired_payload)
        expired_status, expired_response = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {
                "candidate_envelope": expired,
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )
        mismatch_status, mismatch = _post_json(
            server,
            (
                f"/api/projects/{fixture['project']['project_id']}/governed-drafts/"
                "governed_route_source_mismatch/production-derivative-apply"
            ),
            {
                "candidate_envelope": candidate["candidate_envelope"],
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )
        project_mismatch_status, project_mismatch = _post_json(
            server,
            (
                "/api/projects/project_mismatch/governed-drafts/"
                f"{fixture['source_letter_id']}/production-derivative-apply"
            ),
            {
                "candidate_envelope": candidate["candidate_envelope"],
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )
        brand_payload = {
            **envelope_payload,
            "destination_brand_id": "letters_of_light",
        }
        brand_envelope = release_server._seal_production_derivative_promotion_envelope(brand_payload)
        brand_mismatch_status, brand_mismatch = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {
                "candidate_envelope": brand_envelope,
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )

        changed = _letter_payload(tmp_state, fixture["source_letter_id"])
        changed["text"] = fixture["source_text"] + "\nEdited before apply."
        source_dir = tmp_state / "data" / "state" / "letters_of_light" / fixture["source_letter_id"]
        _write_json(source_dir / "letter.json", changed)
        _write_json(source_dir / "manifest.json", changed)
        stale_status, stale = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {
                "candidate_envelope": candidate["candidate_envelope"],
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert expired_status == 400
    assert "production_derivative_promotion_candidate_envelope_expired" in expired_response["error"]
    assert mismatch_status == 400
    assert "candidate_envelope_source_letter_id_mismatch" in mismatch["error"]
    assert project_mismatch_status == 400
    assert "candidate_envelope_project_id_mismatch" in project_mismatch["error"]
    assert brand_mismatch_status == 400
    assert "destination_brand_mismatch" in brand_mismatch["error"]
    assert stale_status == 400
    assert "source_body_hash_mismatch" in stale["error"]


def test_production_derivative_routes_reject_forbidden_authority_fields(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    fixture = _production_derivative_source_fixture(tmp_state)
    server, thread = _serve()

    try:
        candidate_body = _production_derivative_candidate_body(
            fixture,
            authorized=True,
            target_letter_id="client_target",
        )
        candidate_status, candidate_response = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            candidate_body,
        )
        _, candidate = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
        apply_status, apply_response = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {
                "candidate_envelope": candidate["candidate_envelope"],
                "expected_source_body_hash": candidate["source_body_hash"],
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
                "release_state": "approved",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert candidate_status == 400
    assert "production_derivative_promotion_candidate_client_fields_forbidden" in candidate_response["error"]
    assert "authorized" in candidate_response["error"]
    assert "target_letter_id" in candidate_response["error"]
    assert apply_status == 400
    assert "production_derivative_promotion_apply_client_fields_forbidden" in apply_response["error"]
    assert "release_state" in apply_response["error"]


def test_production_derivative_apply_conflicts_when_source_body_changed_under_same_intent(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_production_derivative_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    monkeypatch.setenv("GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY", "route-promotion-key")
    fixture = _production_derivative_source_fixture(tmp_state)
    server, thread = _serve()

    try:
        _, candidate = _post_json(
            server,
            _production_derivative_candidate_path(fixture),
            _production_derivative_candidate_body(fixture),
        )
        apply_body = {
            "candidate_envelope": candidate["candidate_envelope"],
            "expected_source_body_hash": candidate["source_body_hash"],
            "promotion_intent_ref": "production-derivative:intent:route",
            "operator_ref": "operator.route",
        }
        first_status, first = _post_json(server, _production_derivative_apply_path(fixture), apply_body)
        creation_manager.wait_for_creation_job(first["creation_job_id"], timeout=5)

        changed = _letter_payload(tmp_state, fixture["source_letter_id"])
        changed["text"] = fixture["source_text"] + "\nEdited under same governed intent."
        source_dir = tmp_state / "data" / "state" / "letters_of_light" / fixture["source_letter_id"]
        _write_json(source_dir / "letter.json", changed)
        _write_json(source_dir / "manifest.json", changed)
        changed_hash = source_letter_body_hash(changed["text"])
        changed_payload = {
            **candidate["candidate_envelope"]["payload"],
            "source_body_hash": changed_hash,
            "promotion_id": "production_derivative_promotion.changed_body",
            "target_letter_id": "production_derivative_changed_body",
        }
        changed_envelope = release_server._seal_production_derivative_promotion_envelope(changed_payload)
        conflict_status, conflict = _post_json(
            server,
            _production_derivative_apply_path(fixture),
            {
                "candidate_envelope": changed_envelope,
                "expected_source_body_hash": changed_hash,
                "promotion_intent_ref": "production-derivative:intent:route",
                "operator_ref": "operator.route",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first_status == 201
    assert conflict_status == 409
    assert conflict["status"] == "conflict"
    assert "same_source_and_intent_changed_body_hash" in conflict["error"]
    assert len(fake_pipeline.calls) == 1  # type: ignore[attr-defined]


def test_ui_governed_blocker_codes_render_friendly_operator_copy() -> None:
    html = _render_page()

    assert "governedBlockerMessages" in html
    assert "This proposal does not yet include required source support." in html
    assert "This proposal does not yet include a source snapshot reference." in html
    assert "This proposal does not identify a destination brand." in html
    assert "This proposal does not identify a destination surface." in html
    assert "This proposal is for a different brand than the selected project." in html
    assert "A linked draft exists, but it is no longer available to open." in html
    assert "This proposal is missing required governed drafting information." in html
    assert "governedBlockerMessage(blocker)" in html
    assert "governed-blocker-code" in html
    assert 'blockers.map((blocker) => blocker.code || "blocked").filter(Boolean).join(", ")' not in html


def test_ui_existing_linked_status_prioritizes_missing_source_selection() -> None:
    html = _render_page()

    source_status = "Select source passages before continuing this handoff. Linked draft already exists:"
    linked_status = "Existing governed draft linked:"
    assert "Source step" in html
    assert "Select source passages before opening this governed draft." in html
    assert source_status in html
    assert linked_status in html
    assert html.index(source_status) < html.index(linked_status)
    assert "missingSourcePassages" in html
    assert "governedOpenExistingDraftBtn.disabled = !existingLetterId" in html


def test_discovery_valid_promoted_proposal_returns_actionable_without_side_effects(
    tmp_state: Path,
) -> None:
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    before_records = ledger.read_records()
    before_project = _project_file_payload(project["project_id"])
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _proposals_path(project["project_id"], draft_intent_ref="draft-intent:primary"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["ok"] is True
    assert payload["advisory_only"] is True
    assert payload["check_proposal_required"] is True
    assert payload["open_governed_draft_required"] is True
    assert payload["counts"] == {"actionable": 1, "needs_attention": 0}
    candidate = payload["actionable"][0]
    assert candidate["proposal_id"] == proposal.proposal_id
    assert candidate["canonical_node_id"] == node.node_id
    assert candidate["content_job"] == "clarification"
    assert candidate["horizon_class"] == "near_term_follow_up"
    assert candidate["origin_brand_ref"] == "brendon_r_coleman"
    assert candidate["destination_brand_ref"] == "brendon_r_coleman"
    assert candidate["destination_surface_ref"] == "internal_drafting_surface"
    assert candidate["source_support_reference_count"] == 2
    assert candidate["source_snapshot_ref"] == "snapshot:route:001"
    assert candidate["review_outcome"] == "ready_for_draft"
    assert candidate["promotion_state"] == "promoted_to_draft_candidate"
    assert candidate["actionable"] is True
    assert candidate["blockers"] == []
    assert candidate["status_label"] == "Ready"
    assert candidate["linked_letter"] == {"exists": False, "available": False, "status": "none"}
    assert "project_studio_handoff_id" not in candidate
    assert ledger.read_records() == before_records
    assert _project_file_payload(project["project_id"]) == before_project
    assert not (tmp_state / "data" / "state" / "letters_of_light").exists()
    response_text = json.dumps(payload).lower()
    forbidden = ("release", "publish", "schedule", "export", "platform", "oauth", "approval")
    assert all(term not in response_text for term in forbidden)


def test_discovery_default_omits_retired_and_unpromoted_proposals(tmp_state: Path) -> None:
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    unpromoted = _create_proposal(ledger, node, asset, promote=False, suffix="unpromoted")
    retired = _create_proposal(ledger, node, asset, retire=True, suffix="retired")
    server, thread = _serve()

    try:
        status, payload = _get_json(server, _proposals_path(project["project_id"]))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    proposal_ids = {
        item["proposal_id"]
        for group in ("actionable", "needs_attention")
        for item in payload[group]
    }
    assert status == 200
    assert unpromoted.proposal_id not in proposal_ids
    assert retired.proposal_id not in proposal_ids
    assert payload["counts"] == {"actionable": 0, "needs_attention": 0}


def test_discovery_project_brand_incompatibility_is_needs_attention(tmp_state: Path) -> None:
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(
        ledger,
        node,
        asset,
        suffix="brand-mismatch",
        destination_brand_ref="letters_of_light",
        thesis_or_claim="A promoted proposal for another brand should not open here.",
    )
    server, thread = _serve()

    try:
        status, payload = _get_json(server, _proposals_path(project["project_id"]))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["actionable"] == []
    assert len(payload["needs_attention"]) == 1
    item = payload["needs_attention"][0]
    assert item["proposal_id"] == proposal.proposal_id
    assert item["actionable"] is False
    assert item["status_label"] == "Brand mismatch"
    assert "incompatible_project_brand" in {blocker["code"] for blocker in item["blockers"]}


def test_discovery_promoted_source_blocked_projection_is_needs_attention(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _ = _project_with_source(tmp_state)
    blocked = SimpleNamespace(
        proposal_id="proposal.source-blocked",
        source_node_id="node.source-blocked",
        content_job=ContentJob.CLARIFICATION,
        audience="Project Studio operators",
        brand_id="brendon_r_coleman",
        platform="internal_drafting_surface",
        thesis_or_claim="A promoted proposal missing source grounding should be blocked.",
        source_support=(),
        reason_now="It is missing source grounding fields.",
        timing_window=TimingWindow(label="near_term_follow_up", review_date="2026-07-06"),
        review_date="2026-07-06",
        dependencies=(),
        proposed_next_action="Fix source grounding.",
        review_window_ref="",
        origin_brand_id="brendon_r_coleman",
        package_id="",
        horizon_class="near_term_follow_up",
        proposal_intent_ref="proposal-intent:blocked",
        source_snapshot_ref="",
        proposal_identity="proposal-identity:blocked",
        creation_command_id="cmd.blocked",
        actor_ref="operator.route",
        review_outcome="ready_for_draft",
        review_ref="review:blocked",
        promotion_ref="draft-intent:primary",
        status="promoted_to_draft_candidate",
    )
    projection = SimpleNamespace(
        canonical_nodes={"node.source-blocked": object()},
        horizon_proposals={blocked.proposal_id: blocked},
    )
    monkeypatch.setattr(release_server, "replay_governed_publishing_events", lambda _: projection)
    server, thread = _serve()

    try:
        status, payload = _get_json(server, _proposals_path(project["project_id"]))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["actionable"] == []
    assert len(payload["needs_attention"]) == 1
    blockers = {blocker["code"] for blocker in payload["needs_attention"][0]["blockers"]}
    assert "draft_brief_blocked" in blockers
    assert "missing_source_support" in blockers
    assert "missing_source_snapshot" in blockers


def test_discovery_filters_only_read_replayed_metadata(tmp_state: Path) -> None:
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    alpha = _create_proposal(
        ledger,
        node,
        asset,
        suffix="alpha",
        thesis_or_claim="Alpha governed proposal for discovery.",
    )
    _create_proposal(
        ledger,
        node,
        asset,
        suffix="beta",
        content_job=ContentJob.EVIDENCE,
        destination_surface_ref="internal_research_surface",
        thesis_or_claim="Beta governed proposal for another surface.",
    )
    before_records = ledger.read_records()
    before_project = _project_file_payload(project["project_id"])
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _proposals_path(
                project["project_id"],
                q="Alpha",
                content_job="clarification",
                destination_surface_ref="internal_drafting_surface",
                proposal_id=alpha.proposal_id[:18],
            ),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert [item["proposal_id"] for item in payload["actionable"]] == [alpha.proposal_id]
    assert payload["needs_attention"] == []
    assert ledger.read_records() == before_records
    assert _project_file_payload(project["project_id"]) == before_project


def test_discovery_existing_linked_letter_status_is_visible(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        status, payload = _get_json(
            server,
            _proposals_path(project["project_id"], draft_intent_ref="draft-intent:primary"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert len(payload["actionable"]) == 1
    item = payload["actionable"][0]
    assert item["status_label"] == "Linked"
    assert item["linked_project_studio_letter_exists"] is True
    assert item["linked_letter"]["available"] is True
    assert item["linked_letter"]["letter_id"] == opened["letter_id"]
    assert item["linked_letter"]["title"] == "Governed route working title"
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_discovery_unavailable_linked_letter_is_visible_without_recreation(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / opened["letter_id"]
            / "letter.json"
        ).unlink()
        status, payload = _get_json(
            server,
            _proposals_path(project["project_id"], draft_intent_ref="draft-intent:primary"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["actionable"] == []
    assert len(payload["needs_attention"]) == 1
    item = payload["needs_attention"][0]
    assert item["linked_letter"]["available"] is False
    assert item["linked_letter"]["status"] == "linked_draft_unavailable"
    assert "linked_draft_unavailable" in {blocker["code"] for blocker in item["blockers"]}
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_discovery_query_rejects_client_authority_fields(tmp_state: Path) -> None:
    project, _ = _project_with_source(tmp_state)
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _proposals_path(
                project["project_id"],
                release_state="candidate",
                source_snapshot_ref="snapshot:client",
            ),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "governed_draft_discovery_client_authority_fields_forbidden" in payload["error"]
    assert "release_state" in payload["error"]
    assert "source_snapshot_ref" in payload["error"]


def test_context_valid_promoted_proposal_returns_governed_preview_without_side_effects(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    before_records = ledger.read_records()
    before_project = _project_file_payload(project["project_id"])
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _context_path(project["project_id"], proposal.proposal_id),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "ready"
    assert payload["governed_brief_ready"] is True
    assert payload["proposal_id"] == proposal.proposal_id
    assert payload["canonical_node_id"] == node.node_id
    assert payload["content_job"] == "clarification"
    assert payload["origin_brand_ref"] == "brendon_r_coleman"
    assert payload["destination_brand_ref"] == "brendon_r_coleman"
    assert payload["destination_surface_ref"] == "internal_drafting_surface"
    assert payload["horizon_class"] == "near_term_follow_up"
    assert payload["thesis_or_claim"] == "A governed promoted proposal can open an editable source-selected Letter."
    assert payload["reason_now"] == "Phase 1J connects the governed handoff to Project Studio."
    assert payload["source_support_reference_count"] == 2
    assert payload["source_snapshot_ref"] == "snapshot:route:001"
    assert payload["promotion_state"] == "promoted_to_draft_candidate"
    assert payload["review_outcome"] == "ready_for_draft"
    assert payload["readiness_state"] == "ready"
    assert payload["blockers"] == []
    assert payload["project_studio_handoff_id"]
    assert payload["linked_project_studio_letter_exists"] is False
    assert payload["linked_letter"] == {"exists": False, "available": False, "status": "none"}
    assert ledger.read_records() == before_records
    assert _project_file_payload(project["project_id"]) == before_project
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_context_unpromoted_proposal_returns_visible_blockers(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset, promote=False)
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _context_path(project["project_id"], proposal.proposal_id),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "blocked"
    assert payload["governed_brief_ready"] is False
    assert "proposal_not_promoted_to_draft_candidate" in {
        blocker["code"] for blocker in payload["blockers"]
    }
    assert payload["promotion_state"] == "proposed"
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_context_missing_required_query_fields_are_rejected(tmp_state: Path) -> None:
    project, _ = _project_with_source(tmp_state)
    server, thread = _serve()

    try:
        missing_proposal_status, missing_proposal = _get_json(
            server,
            _context_path(project["project_id"], proposal_id=""),
        )
        missing_intent_status, missing_intent = _get_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/context?{urlencode({'proposal_id': 'proposal.001', 'draft_intent_ref': ''})}",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert missing_proposal_status == 400
    assert missing_proposal["status"] == "validation_error"
    assert "proposal_id is required" in missing_proposal["error"]
    assert missing_intent_status == 400
    assert missing_intent["status"] == "validation_error"
    assert "draft_intent_ref is required" in missing_intent["error"]


def test_context_missing_project_is_rejected(tmp_state: Path) -> None:
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _context_path("project_missing", "proposal.001"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 404
    assert payload["status"] == "validation_error"
    assert "Project not found" in payload["error"]


def test_context_response_contains_no_authority_changing_state(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            _context_path(project["project_id"], proposal.proposal_id),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    response_text = json.dumps(payload).lower()
    forbidden = ("release", "publish", "schedule", "export", "platform", "approval", "package_readiness")
    assert all(term not in response_text for term in forbidden)
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_context_existing_linked_letter_is_reported_openable(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        status, payload = _get_json(
            server,
            _context_path(project["project_id"], proposal.proposal_id),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["linked_project_studio_letter_exists"] is True
    assert payload["linked_letter"]["available"] is True
    assert payload["linked_letter"]["status"] == "available"
    assert payload["linked_letter"]["letter_id"] == opened["letter_id"]
    assert payload["linked_letter"]["title"] == "Governed route working title"
    assert payload["linked_letter"]["lifecycle_state"] == "draft"
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_context_unavailable_linked_letter_is_reported_without_recreation(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / opened["letter_id"]
            / "letter.json"
        ).unlink()
        status, payload = _get_json(
            server,
            _context_path(project["project_id"], proposal.proposal_id),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["linked_project_studio_letter_exists"] is True
    assert payload["linked_letter"]["available"] is False
    assert payload["linked_letter"]["status"] == "linked_draft_unavailable"
    assert payload["linked_letter"]["letter_id"] == opened["letter_id"]
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_context_query_rejects_client_supplied_authority_fields(tmp_state: Path) -> None:
    project, _ = _project_with_source(tmp_state)
    query = urlencode(
        {
            "proposal_id": "proposal.001",
            "draft_intent_ref": "draft-intent:primary",
            "destination_brand_ref": "letters_of_light",
            "publish_state": "ready",
        }
    )
    server, thread = _serve()

    try:
        status, payload = _get_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/context?{query}",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "governed_draft_client_authority_fields_forbidden" in payload["error"]
    assert "destination_brand_ref" in payload["error"]
    assert "publish_state" in payload["error"]


def test_valid_promoted_proposal_route_opens_source_selected_letter_without_authority_writes(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    before_records = ledger.read_records()
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 201
    assert payload["status"] == "created"
    assert payload["letter_id"] == "governed-route-letter-1"
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]
    assert ledger.read_records() == before_records
    response_text = json.dumps(payload).lower()
    forbidden = ("release", "publish", "schedule", "export", "platform", "approval", "package_readiness")
    assert all(term not in response_text for term in forbidden)
    assert "handoff_id" not in payload

    letter = _letter_payload(tmp_state, payload["letter_id"])
    metadata = letter["metadata"]
    assert letter["lifecycle_state"] == "draft"
    assert metadata["release_eligible"] is False
    assert metadata["governed_handoff"]["authority"]["publication"] is False
    assert metadata["governed_handoff"]["authority"]["release_eligibility"] is False


def test_outline_preview_route_blocks_without_selected_passages_and_does_not_mutate(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        before_project = _project_file_payload(project["project_id"])
        before_records = ledger.read_records()
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset, selected_passages=[]),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert "selected_source_passages_required" in {blocker["code"] for blocker in payload["blockers"]}
    assert _project_file_payload(project["project_id"]) == before_project
    assert ledger.read_records() == before_records
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_outline_preview_route_returns_structured_governed_context_without_writes(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        before_project = _project_file_payload(project["project_id"])
        before_records = ledger.read_records()
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset, writer_note="Use a gentle opening.", format_intent="brief essay outline"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["preview_id"].startswith("outline_preview.")
    assert payload["semantic_resolution_status"] == SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE
    assert payload["parent_letter"]["letter_id"] == opened["letter_id"]
    assert payload["proposal_id"] == proposal.proposal_id
    assert payload["canonical_node_id"] == node.node_id
    assert payload["thesis_or_claim"] == "A governed promoted proposal can open an editable source-selected Letter."
    assert payload["reason_now"] == "Phase 1J connects the governed handoff to Project Studio."
    assert payload["destination_brand_ref"] == "brendon_r_coleman"
    assert payload["destination_surface_ref"] == "internal_drafting_surface"
    assert payload["source_snapshot_ref"] == "snapshot:route:001"
    assert payload["selected_passage_count"] == 1
    assert payload["claim_classifications"] == ["observation", "observation"]
    assert payload["outline_sections"]
    assert any(item["selected_passage_refs"] for item in payload["outline_sections"])
    assert payload["existing_child"]["exists"] is False
    assert payload["authority"]["release_eligibility"] is False
    assert payload["authority"]["publication"] is False
    assert "source_assets" not in payload
    assert _project_file_payload(project["project_id"]) == before_project
    assert ledger.read_records() == before_records


def test_outline_preview_route_shows_semantic_authority_block(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        ledger.path.unlink()
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["semantic_resolution_status"] == SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED
    assert "horizon_proposal_missing" in {blocker["code"] for blocker in payload["blockers"]}


def test_outline_acceptance_route_rejects_preview_id_mismatch(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        _, preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
        body = _outline_acceptance_body(opened["letter_id"], asset, preview)
        body["preview_id"] = "outline_preview.stale"
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert payload["error"] == "source_grounded_preview_id_mismatch"


def test_outline_acceptance_route_creates_one_scaffold_child_without_release_or_authority_writes(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        before_records = ledger.read_records()
        _, preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            _outline_acceptance_body(opened["letter_id"], asset, preview),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 201
    assert payload["status"] == "created"
    assert payload["child_letter_id"].startswith("source_grounded_letter")
    assert payload["child_letter"]["open_url"] == f"/?letter_id={payload['child_letter_id']}"
    assert payload["authority"]["release_eligibility"] is False
    assert payload["authority"]["publication"] is False
    assert payload["authority"]["governed_publishing_ledger_write"] is False
    assert ledger.read_records() == before_records

    child = _letter_payload(tmp_state, payload["child_letter_id"])
    assert child["parent_letter_id"] == opened["letter_id"]
    assert child["lifecycle_state"] == "draft"
    assert child["metadata"]["editable"] is True
    assert child["metadata"]["release_eligible"] is False
    assert child["metadata"]["source_grounded_drafting_candidate"] is True
    assert "release_state" not in child
    assert "published" not in child
    assert "scheduled_at" not in child
    assert "queue" not in child
    assert "platform" not in child
    plan = child["metadata"][SOURCE_GROUNDED_DRAFTING_METADATA_KEY][SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY]
    assert plan["accepted_preview_id"] == preview["preview_id"]
    assert plan["semantic_resolution_status"] == SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE
    assert plan["authority"]["release_eligibility"] is False
    assert plan["authority"]["publication"] is False


def test_repeated_outline_acceptance_returns_existing_child_and_preview_reports_it(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        _, preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
        first_status, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            _outline_acceptance_body(opened["letter_id"], asset, preview),
        )
        second_status, second = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            _outline_acceptance_body(opened["letter_id"], asset, preview),
        )
        _, after_preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first_status == 201
    assert second_status == 200
    assert first["status"] == "created"
    assert second["status"] == "linked_existing"
    assert second["child_letter_id"] == first["child_letter_id"]
    assert after_preview["existing_child"]["available"] is True
    assert after_preview["existing_child"]["child_letter_id"] == first["child_letter_id"]
    project_after = project_payload(project["project_id"])
    assert len(project_after[SOURCE_GROUNDED_ACCEPTANCE_INDEX_KEY]) == 1
    children = [
        path
        for path in (tmp_state / "data" / "state" / "letters_of_light").iterdir()
        if path.is_dir() and path.name.startswith("source_grounded_letter")
    ]
    assert len(children) == 1


def test_unavailable_accepted_child_returns_conflict_without_recreation(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        _, preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
        _, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            _outline_acceptance_body(opened["letter_id"], asset, preview),
        )
        child_path = tmp_state / "data" / "state" / "letters_of_light" / first["child_letter_id"] / "letter.json"
        child = json.loads(child_path.read_text(encoding="utf-8"))
        child["lifecycle_state"] = "archived"
        _write_json(child_path, child)
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-acceptance",
            _outline_acceptance_body(opened["letter_id"], asset, preview),
        )
        _, after_preview = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            _outline_preview_body(opened["letter_id"], asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 409
    assert payload["status"] == "conflict"
    assert "accepted_drafting_candidate_unavailable" in payload["error"] or "child_drafting_candidate_unavailable" in payload["error"]
    assert after_preview["existing_child"]["available"] is False
    assert after_preview["existing_child"]["status"] == "accepted_child_unavailable"
    children = [
        path
        for path in (tmp_state / "data" / "state" / "letters_of_light").iterdir()
        if path.is_dir() and path.name.startswith("source_grounded_letter")
    ]
    assert len(children) == 1


def test_prose_candidate_route_provider_not_authorized_fails_closed(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    monkeypatch.delenv("STRUCTURED_GENERATION_PROVIDER", raising=False)
    monkeypatch.delenv("SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY", raising=False)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        before_project = _project_file_payload(project["project_id"])
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        after_project = _project_file_payload(project["project_id"])
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 503
    assert payload["status"] == "provider_not_authorized"
    assert before_project == after_project
    assert "candidate_envelope" not in payload


def test_prose_candidate_route_rejects_client_candidate_and_authority_fields(
    tmp_state: Path,
) -> None:
    project, _ = _project_with_source(tmp_state)
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            {
                "candidate_text": "browser supplied prose",
                "provider_output": {"candidate_text": "browser provider output"},
                "publish_state": "published",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "source_grounded_prose_candidate_client_authority_fields_forbidden" in payload["error"]
    assert "candidate_text" in payload["error"]
    assert "provider_output" in payload["error"]
    assert "publish_state" in payload["error"]


def test_prose_candidate_route_returns_valid_sealed_candidate_without_secret_leak(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        generator = _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"]),
        )
        before_project = _project_file_payload(project["project_id"])
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        after_project = _project_file_payload(project["project_id"])
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "generated_candidate"
    assert payload["candidate_text"]
    assert payload["candidate_envelope"]["payload"]["candidate_text"] == payload["candidate_text"]
    assert payload["candidate_envelope"]["payload"]["accepted_scaffold_letter_id"] == scaffold["scaffold_letter_id"]
    assert payload["candidate_envelope_id"].startswith("source_grounded_candidate_envelope.")
    assert payload["direct_quotations_supported"] is False
    assert generator.calls == 1
    assert before_project == after_project
    serialized = json.dumps(payload, sort_keys=True)
    assert "phase3d-test-signing-material" not in serialized
    assert "api_key" not in serialized
    assert "must-not-leak" not in serialized


@pytest.mark.parametrize(
    ("provider_overrides", "expected_code"),
    [
        ({"candidate_text": 'This includes "a direct quotation".'}, "direct_quotation_text_not_supported_phase3b"),
        ({"used_source_refs": ["invented-source"]}, "invented_source_ref"),
        ({"used_passage_refs": ["invented-passage"]}, "invented_passage_ref"),
        (
            {
                "segment_annotations": [
                    ProseCandidateSegmentAnnotation(
                        segment_id="unsupported-claim",
                        segment_index=0,
                        text_span="sentence:1",
                        classification="factual_claim",
                        supporting_source_refs=[],
                        supporting_passage_refs=[],
                        support_status="insufficient_support",
                    )
                ],
                "output_classification_summary": ["factual_claim"],
            },
            "factual_claim_support_required",
        ),
    ],
)
def test_prose_candidate_route_blocks_invalid_provider_output(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_overrides: dict[str, object],
    expected_code: str,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"], **provider_overrides),
        )
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 200
    assert payload["status"] == "validation_error"
    assert expected_code in {blocker["code"] for blocker in payload["blockers"]}
    assert "candidate_envelope" not in payload


def test_prose_apply_route_requires_verified_envelope_and_rejects_tampering(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"]),
        )
        _, candidate = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        envelope = candidate["candidate_envelope"]
        envelope["payload"]["candidate_text"] = "Tampered browser candidate text."
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            {
                "accepted_scaffold_letter_id": scaffold["scaffold_letter_id"],
                "candidate_envelope": envelope,
                "expected_scaffold_body_hash": candidate["candidate_envelope"]["payload"]["accepted_scaffold_body_hash"],
                "apply_intent_ref": "apply-intent:route",
                "actor_ref": "operator.route",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "candidate_envelope_signature_invalid" in payload["error"]


def test_prose_apply_route_rejects_expired_envelope(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"]),
        )
        _, candidate = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        expired_payload = dict(candidate["candidate_envelope"]["payload"])
        expired_payload["expires_at"] = "2026-01-01T00:00:00+00:00"
        expired = CandidateEnvelopeSigner(
            key_material="phase3d-test-signing-material",
            signer_id="phase3d-test",
        ).seal(expired_payload).to_dict()
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            {
                "accepted_scaffold_letter_id": scaffold["scaffold_letter_id"],
                "candidate_envelope": expired,
                "expected_scaffold_body_hash": expired_payload["accepted_scaffold_body_hash"],
                "apply_intent_ref": "apply-intent:route",
                "actor_ref": "operator.route",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "candidate_envelope_expired" in payload["error"]


def test_prose_apply_route_creates_one_child_and_repeated_apply_returns_existing(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"]),
        )
        before_records = ledger.read_records()
        _, candidate = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        apply_body = {
            "accepted_scaffold_letter_id": scaffold["scaffold_letter_id"],
            "candidate_envelope": candidate["candidate_envelope"],
            "expected_scaffold_body_hash": candidate["candidate_envelope"]["payload"]["accepted_scaffold_body_hash"],
            "apply_intent_ref": "apply-intent:route",
            "actor_ref": "operator.route",
        }
        first_status, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            apply_body,
        )
        second_status, second = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            apply_body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first_status == 201
    assert second_status == 200
    assert first["status"] == "created"
    assert second["status"] == "linked_existing"
    assert second["child_letter_id"] == first["child_letter_id"]
    assert first["child_letter"]["open_url"] == f"/?letter_id={first['child_letter_id']}"
    assert first["authority"]["release_eligibility"] is False
    assert first["authority"]["publication"] is False
    assert ledger.read_records() == before_records

    scaffold_letter = _letter_payload(tmp_state, scaffold["scaffold_letter_id"])
    child = _letter_payload(tmp_state, first["child_letter_id"])
    assert scaffold_letter["letter_id"] == scaffold["scaffold_letter_id"]
    assert child["parent_letter_id"] == scaffold["scaffold_letter_id"]
    assert child["lifecycle_state"] == "draft"
    assert child["metadata"]["editable"] is True
    assert child["metadata"]["release_eligible"] is False
    assert candidate["candidate_text"] in child["text"]
    combined = json.dumps({"child": child, "project": project_payload(project["project_id"])}, sort_keys=True)
    assert "release_state" not in combined
    assert "scheduled_at" not in combined
    assert "published" not in combined
    assert "platform_state" not in combined
    applied_metadata = child["metadata"]["source_grounded_prose_application"]["applied_candidate"]
    assert applied_metadata["authority"]["oauth"] is False
    assert applied_metadata["authority"]["queue"] is False
    assert applied_metadata["authority"]["platform_action"] is False
    children = [
        path
        for path in (tmp_state / "data" / "state" / "letters_of_light").iterdir()
        if path.is_dir() and path.name.startswith("source_grounded_prose_letter")
    ]
    assert len(children) == 1


def test_unavailable_linked_prose_child_returns_conflict_without_recreation(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        scaffold = _accepted_scaffold_for_prose_route(server, project, asset, proposal.proposal_id)
        _install_route_prose_provider(
            monkeypatch,
            _route_prose_provider_output(asset, scaffold["outline_section_id"]),
        )
        _, candidate = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-candidate",
            _prose_candidate_body(scaffold, asset),
        )
        apply_body = {
            "accepted_scaffold_letter_id": scaffold["scaffold_letter_id"],
            "candidate_envelope": candidate["candidate_envelope"],
            "expected_scaffold_body_hash": candidate["candidate_envelope"]["payload"]["accepted_scaffold_body_hash"],
            "apply_intent_ref": "apply-intent:route",
            "actor_ref": "operator.route",
        }
        _, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            apply_body,
        )
        child_path = tmp_state / "data" / "state" / "letters_of_light" / first["child_letter_id"] / "letter.json"
        child = json.loads(child_path.read_text(encoding="utf-8"))
        child["lifecycle_state"] = "archived"
        _write_json(child_path, child)
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/prose-apply",
            apply_body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 409
    assert payload["status"] == "conflict"
    assert "applied_child_unavailable" in payload["error"]
    children = [
        path
        for path in (tmp_state / "data" / "state" / "letters_of_light").iterdir()
        if path.is_dir() and path.name.startswith("source_grounded_prose_letter")
    ]
    assert len(children) == 1


def test_outline_routes_reject_client_supplied_authority_fields(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        body = _outline_preview_body(opened["letter_id"], asset)
        body["proposal_id"] = proposal.proposal_id
        body["publish_state"] = "published"
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/outline-preview",
            body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "source_grounded_outline_client_authority_fields_forbidden" in payload["error"]
    assert "proposal_id" in payload["error"]
    assert "publish_state" in payload["error"]


def test_repeat_open_is_idempotent_and_links_existing_letter(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        first_status, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        second_status, second = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first_status == 201
    assert second_status == 200
    assert first["status"] == "created"
    assert second["status"] == "linked_existing"
    assert second["letter_id"] == first["letter_id"]
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_distinct_draft_intent_opens_distinct_letter(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        second_status, second = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset, draft_intent_ref="draft-intent:secondary"),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert second_status == 201
    assert second["status"] == "created"
    assert second["letter_id"] != first["letter_id"]
    assert fake_pipeline.counter["value"] == 2  # type: ignore[attr-defined]


def test_unpromoted_proposal_is_blocked(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset, promote=False)
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "blocked"
    assert "proposal_not_promoted_to_draft_candidate" in {
        blocker["code"] for blocker in payload["blockers"]
    }
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_missing_project_and_invalid_source_are_validation_errors(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    invalid_body = _open_body(proposal.proposal_id, asset)
    invalid_body["selected_passages"] = [
        {
            **_selected_passage(asset),
            "asset_id": "asset_missing",
            "source_asset_id": "asset_missing",
        }
    ]
    server, thread = _serve()

    try:
        missing_status, missing = _post_json(
            server,
            "/api/projects/project_missing/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        invalid_status, invalid = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            invalid_body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert missing_status == 404
    assert missing["status"] == "validation_error"
    assert invalid_status == 400
    assert invalid["status"] == "validation_error"
    assert "selected_source_passage_asset_not_in_project" in invalid["error"]
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_route_rejects_client_supplied_governed_authority_fields(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    body = _open_body(proposal.proposal_id, asset)
    body["destination_brand_ref"] = "letters_of_light"
    body["release_state"] = "candidate"
    server, thread = _serve()

    try:
        status, payload = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            body,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert status == 400
    assert payload["status"] == "validation_error"
    assert "governed_draft_client_authority_fields_forbidden" in payload["error"]
    assert "destination_brand_ref" in payload["error"]
    assert "release_state" in payload["error"]
    assert fake_pipeline.counter["value"] == 0  # type: ignore[attr-defined]


def test_unavailable_linked_letter_returns_conflict(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, first = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / first["letter_id"]
            / "letter.json"
        ).unlink()
        conflict_status, conflict = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert conflict_status == 409
    assert conflict["status"] == "conflict"
    assert "linked_draft_unavailable" in conflict["error"]
    assert fake_pipeline.counter["value"] == 1  # type: ignore[attr-defined]


def test_project_payload_represents_existing_linked_governed_draft(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_success_pipeline_factory()
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    project, asset = _project_with_source(tmp_state)
    ledger = _ledger(tmp_state)
    node = _append_node(ledger, project, asset)
    proposal = _create_proposal(ledger, node, asset)
    server, thread = _serve()

    try:
        _, opened = _post_json(
            server,
            f"/api/projects/{project['project_id']}/governed-drafts/open",
            _open_body(proposal.proposal_id, asset),
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    payload = project_payload(project["project_id"])
    linked = [
        entry
        for entry in payload["governed_handoffs"].values()
        if entry.get("letter_id") == opened["letter_id"]
    ]
    assert len(linked) == 1
    assert linked[0]["proposal_id"] == proposal.proposal_id
    assert linked[0]["status"] == "linked"
