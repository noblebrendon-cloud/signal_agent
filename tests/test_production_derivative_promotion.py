from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.letters_of_light import creation_manager
from app.letters_of_light.contract import LetterOfLight
from app.letters_of_light.production_derivative_promotion import (
    PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY,
    PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY,
    GovernedDraftPromotionConflict,
    GovernedDraftPromotionRequest,
    promote_governed_draft_to_production_derivative,
    source_letter_body_hash,
    validate_governed_draft_production_derivative_candidate,
)
from app.letters_of_light.project_studio import create_project, import_asset, project_payload
from app.letters_of_light.release import check_release_eligibility
from app.letters_of_light.creation_manager import wait_for_creation_job


NOW = "2026-07-02T00:00:00+00:00"


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _letter_path(tmp_state: Path, letter_id: str) -> Path:
    return tmp_state / "data" / "state" / "letters_of_light" / letter_id / "letter.json"


def _letter_payload(tmp_state: Path, letter_id: str) -> dict:
    return json.loads(_letter_path(tmp_state, letter_id).read_text(encoding="utf-8"))


def _fake_draft_pipeline(tmp_state: Path):
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
        letter_id = requested_letter_id or f"unexpected_{len(calls)}"
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


def _fixture(tmp_state: Path) -> dict[str, Any]:
    source_file = tmp_state / "source.md"
    source_file.write_text("Verified source excerpt.", encoding="utf-8")
    project = create_project(title="Promotion Project", brand_id="brendon_r_coleman")
    asset = import_asset(project["project_id"], source_path=str(source_file))
    source_letter_id = "governed_source_001"
    source_text = "Exact governed draft body for production derivative."
    metadata = {
        "project_id": project["project_id"],
        "brand_id": "brendon_r_coleman",
        "brand_version": "1",
        "parent_root_letter_id": "root_letter_001",
        "governed_handoff_id": "handoff.001",
        "governed_handoff": {
            "handoff_id": "handoff.001",
            "governed_drafting_brief_id": "drafting_brief.001",
            "proposal_id": "proposal.001",
            "canonical_node_id": "node.001",
            "source_snapshot_ref": "snapshot:001",
            "source_support_refs": ["node.001", asset["asset_id"]],
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
                "source_snapshot_ref": "snapshot:001",
                "source_support_refs": ["node.001", asset["asset_id"]],
            },
        },
        "source_snapshot_ref": "snapshot:001",
        "source_support_refs": ["node.001", asset["asset_id"]],
        "source_asset_ids": [asset["asset_id"]],
        "selected_source_passages": [
            {
                "asset_id": asset["asset_id"],
                "passage_id": "source:1",
                "page_number": 1,
                "text": "Verified source excerpt.",
            }
        ],
        "release_eligible": False,
        "approval_status": "unapproved",
        "review_status": "unreviewed",
        "publication_state": "not_started",
    }
    letter = {
        "letter_id": source_letter_id,
        "artifact_type": "letter_of_light",
        "theme": "governed source",
        "title": "Governed Source",
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


def _request(fixture: dict[str, Any], *, intent: str = "promotion-intent:primary") -> GovernedDraftPromotionRequest:
    return GovernedDraftPromotionRequest(
        source_letter_id=fixture["source_letter_id"],
        expected_source_body_hash=source_letter_body_hash(fixture["source_text"]),
        promotion_intent_ref=intent,
        destination_project_id=fixture["project"]["project_id"],
        destination_brand_id="brendon_r_coleman",
        operator_ref="operator.promotion",
    )


def test_valid_governed_promotion_creates_separate_non_release_target(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    fixture = _fixture(tmp_state)
    source_before = fixture["source_path"].read_text(encoding="utf-8")

    result = promote_governed_draft_to_production_derivative(_request(fixture), now=NOW)
    finished = wait_for_creation_job(result.job_id or "", timeout=5)

    assert result.status == "created"
    assert result.target_letter_id != fixture["source_letter_id"]
    assert finished is not None
    assert finished["status"] == "succeeded"
    assert fixture["source_path"].read_text(encoding="utf-8") == source_before
    assert fake_pipeline.calls[0]["manual_text"] == fixture["source_text"]  # type: ignore[attr-defined]
    assert fake_pipeline.calls[0]["requested_letter_id"] == result.target_letter_id  # type: ignore[attr-defined]

    target = _letter_payload(tmp_state, result.target_letter_id)
    receipt = target["metadata"][PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY]
    assert target["text"] == fixture["source_text"]
    assert target["parent_letter_id"] == fixture["source_letter_id"]
    assert target["metadata"]["revision_of"] == fixture["source_letter_id"]
    assert target["metadata"]["parent_root_letter_id"] == "root_letter_001"
    assert receipt["promotion_id"] == result.promotion_id
    assert receipt["source_body_hash"] == source_letter_body_hash(fixture["source_text"])
    assert receipt["creation_job_id"] == result.job_id
    assert receipt["governed_handoff_ids"] == ["handoff.001"]
    assert target["metadata"]["release_eligible"] is False
    assert all(value is False for value in target["metadata"]["authority"].values())
    for forbidden in ("release_state", "approved", "scheduled_at", "exported_at", "published_at"):
        assert forbidden not in target
        assert forbidden not in target["metadata"]

    release_check = check_release_eligibility(result.target_letter_id)
    assert release_check.eligible is False
    assert any("lifecycle_state is not registered" in reason for reason in release_check.reasons)

    project = project_payload(fixture["project"]["project_id"])
    assert project[PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY][result.promotion_id]["target_letter_id"] == result.target_letter_id
    assert any(output.get("promotion_id") == result.promotion_id for output in project["letter_outputs"])


def test_candidate_validation_is_non_mutating_and_uses_deterministic_identity(
    tmp_state: Path,
) -> None:
    fixture = _fixture(tmp_state)
    request = _request(fixture)
    source_before = fixture["source_path"].read_text(encoding="utf-8")
    project_before = project_payload(fixture["project"]["project_id"])

    candidate = validate_governed_draft_production_derivative_candidate(request)

    assert candidate.validation_state == "valid"
    assert candidate.source_letter_id == fixture["source_letter_id"]
    assert candidate.source_body_hash == source_letter_body_hash(fixture["source_text"])
    assert candidate.target_letter_id.startswith("production_derivative_")
    assert candidate.lineage_summary["governed_handoff_ids"] == ["handoff.001"]
    assert candidate.lineage_summary["source_asset_ids"] == [fixture["asset"]["asset_id"]]
    assert fixture["source_path"].read_text(encoding="utf-8") == source_before
    assert not (tmp_state / "data" / "state" / "letters_of_light" / candidate.target_letter_id).exists()

    project_after = project_payload(fixture["project"]["project_id"])
    assert PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY not in project_after
    assert project_after["letter_outputs"] == project_before["letter_outputs"]


def test_identical_promotion_is_idempotent_and_changed_body_conflicts(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    fixture = _fixture(tmp_state)
    request = _request(fixture)

    first = promote_governed_draft_to_production_derivative(request, now=NOW)
    wait_for_creation_job(first.job_id or "", timeout=5)
    second = promote_governed_draft_to_production_derivative(request, now=NOW)

    assert second.status == "already_promoted"
    assert second.target_letter_id == first.target_letter_id
    assert len(fake_pipeline.calls) == 1  # type: ignore[attr-defined]
    project = project_payload(fixture["project"]["project_id"])
    outputs = [output for output in project["letter_outputs"] if output.get("promotion_id") == first.promotion_id]
    assert len(outputs) == 1

    changed = _letter_payload(tmp_state, fixture["source_letter_id"])
    changed["text"] = fixture["source_text"] + "\nEdited inside governed draft workflow."
    _write_json(_letter_path(tmp_state, fixture["source_letter_id"]), changed)
    _write_json(
        tmp_state
        / "data"
        / "state"
        / "letters_of_light"
        / fixture["source_letter_id"]
        / "manifest.json",
        changed,
    )
    changed_request = GovernedDraftPromotionRequest(
        source_letter_id=fixture["source_letter_id"],
        expected_source_body_hash=source_letter_body_hash(changed["text"]),
        promotion_intent_ref=request.promotion_intent_ref,
        destination_project_id=request.destination_project_id,
        destination_brand_id=request.destination_brand_id,
        operator_ref=request.operator_ref,
    )

    with pytest.raises(GovernedDraftPromotionConflict, match="same_source_and_intent_changed_body_hash"):
        promote_governed_draft_to_production_derivative(changed_request, now=NOW)
