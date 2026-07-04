from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from app.letters_of_light import creation_manager
from app.letters_of_light.contract import LetterOfLight
from app.letters_of_light.governed_production_promotion import (
    GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY,
    PRODUCTION_PROMOTION_METADATA_KEY,
    RECEIPT_SCHEMA_VERSION,
    GovernedProductionPromotionConflict,
    GovernedProductionPromotionIntegrityError,
    GovernedProductionPromotionRequest,
    GovernedProductionPromotionValidationError,
    build_governed_production_promotion_receipt,
    compute_target_letter_id,
    compute_source_body_hash,
    compute_source_lineage_hash,
    compute_source_manifest_hash,
    compute_source_record_hash,
    promote_governed_draft_to_production_derivative,
    validate_governed_draft_for_production_promotion,
)
from app.letters_of_light.source_grounded_drafting import (
    SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY,
    SOURCE_GROUNDED_DRAFTING_METADATA_KEY,
)
from app.letters_of_light.source_grounded_prose_apply import (
    SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY,
    SOURCE_GROUNDED_PROSE_APPLICATION_METADATA_KEY,
)


PROJECT_ID = "project_governed_promotion"
SOURCE_LETTER_ID = "governed_source_letter_001"
_USE_CURRENT_MANIFEST = object()


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_path(root: Path, project_id: str = PROJECT_ID) -> Path:
    return root / "data" / "state" / "studio" / "projects" / project_id / "project.json"


def _letter_dir(root: Path, letter_id: str = SOURCE_LETTER_ID) -> Path:
    return root / "data" / "state" / "letters_of_light" / letter_id


def _letter_path(root: Path, letter_id: str = SOURCE_LETTER_ID) -> Path:
    return _letter_dir(root, letter_id) / "letter.json"


def _manifest_path(root: Path, letter_id: str = SOURCE_LETTER_ID) -> Path:
    return _letter_dir(root, letter_id) / "manifest.json"


def _capture_source_bytes(root: Path, letter_id: str = SOURCE_LETTER_ID) -> dict[str, bytes]:
    letter = _letter_path(root, letter_id)
    manifest = _manifest_path(root, letter_id)
    routing = _letter_dir(root, letter_id) / "routing.json"
    interaction = _letter_dir(root, letter_id) / "interaction.json"
    release = _letter_dir(root, letter_id) / "release.json"
    return {
        "letter.json": letter.read_bytes() if letter.exists() else b"",
        "manifest.json": manifest.read_bytes() if manifest.exists() else b"",
        "routing.json": routing.read_bytes() if routing.exists() else b"",
        "interaction.json": interaction.read_bytes() if interaction.exists() else b"",
        "release.json": release.read_bytes() if release.exists() else b"",
    }


def _assert_validation_does_not_mutate(root: Path, call: Callable[[], Any]) -> Any:
    before = _capture_source_bytes(root)
    try:
        return call()
    finally:
        assert _capture_source_bytes(root) == before


def _base_fixture(root: Path) -> dict[str, Any]:
    project = {
        "project_id": PROJECT_ID,
        "title": "Governed Promotion Project",
        "brand_id": "brendon_r_coleman",
        "brand_version": "1",
        "assets": [
            {
                "asset_id": "asset_source_001",
                "kind": "source",
                "title": "Primary source packet",
            }
        ],
    }
    _write_json(_project_path(root), project)

    letter = {
        "letter_id": SOURCE_LETTER_ID,
        "artifact_type": "letter_of_light",
        "theme": "Production promotion source",
        "title": "A Governed Source Draft",
        "text": "Exact governed draft body for future production promotion.",
        "lifecycle_state": "draft",
        "created_at": "2026-07-02T00:00:00+00:00",
        "updated_at": "2026-07-02T00:00:00+00:00",
        "metadata": {
            "project_id": PROJECT_ID,
            "brand_id": "brendon_r_coleman",
            "brand_version": "1",
            "parent_letter_id": "parent_letter_001",
            "parent_root_letter_id": "root_letter_001",
            "revision_of": "parent_letter_001",
            "governed_derivative_draft": True,
            "governed_handoff_id": "handoff_001",
            "governed_handoff": {
                "handoff_id": "handoff_001",
                "governed_drafting_brief_id": "brief_001",
                "proposal_id": "proposal_001",
                "canonical_node_id": "node_001",
                "source_snapshot_ref": "snapshot_001",
                "source_support_refs": ["support_001"],
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
            },
            "source_asset_ids": ["asset_source_001"],
            "selected_source_passages": [
                {
                    "asset_id": "asset_source_001",
                    "passage_id": "passage_001",
                    "text": "Verified selected source passage.",
                }
            ],
            "source_snapshot_ref": "snapshot_001",
            "source_support_refs": ["support_001"],
            "release_eligible": False,
            "approval_status": "unapproved",
            "review_status": "unreviewed",
            "publication_state": "not_started",
        },
    }
    manifest = copy.deepcopy(letter)
    _write_json(_letter_path(root), letter)
    _write_json(_manifest_path(root), manifest)
    _write_json(_letter_dir(root) / "routing.json", {"youtube": {"title": "source route"}})
    _write_json(_letter_dir(root) / "interaction.json", {"questions": ["source question"]})
    return {"project": project, "letter": letter, "manifest": manifest}


def _load_letter(root: Path) -> dict[str, Any]:
    return _read_json(_letter_path(root))


def _load_manifest(root: Path) -> dict[str, Any]:
    return _read_json(_manifest_path(root))


def _request(
    root: Path,
    *,
    operator_ref: str = "operator:phase1",
    promotion_intent_ref: str = "promotion-intent:primary",
    expected_source_manifest_hash: str | None | object = _USE_CURRENT_MANIFEST,
) -> GovernedProductionPromotionRequest:
    letter = _load_letter(root)
    if expected_source_manifest_hash is _USE_CURRENT_MANIFEST:
        expected_manifest = compute_source_manifest_hash(_load_manifest(root))
    else:
        expected_manifest = expected_source_manifest_hash
    return GovernedProductionPromotionRequest(
        project_id=PROJECT_ID,
        source_letter_id=SOURCE_LETTER_ID,
        operator_ref=operator_ref,
        promotion_intent_ref=promotion_intent_ref,
        expected_source_body_hash=compute_source_body_hash(letter),
        expected_source_record_hash=compute_source_record_hash(letter),
        expected_source_lineage_hash=compute_source_lineage_hash(letter),
        expected_source_manifest_hash=expected_manifest,  # type: ignore[arg-type]
    )


def _request_from_hashes(
    *,
    body_hash: str,
    record_hash: str,
    lineage_hash: str,
    manifest_hash: str | None,
    operator_ref: str = "operator:phase1",
    promotion_intent_ref: str = "promotion-intent:primary",
) -> GovernedProductionPromotionRequest:
    return GovernedProductionPromotionRequest(
        project_id=PROJECT_ID,
        source_letter_id=SOURCE_LETTER_ID,
        operator_ref=operator_ref,
        promotion_intent_ref=promotion_intent_ref,
        expected_source_body_hash=body_hash,
        expected_source_record_hash=record_hash,
        expected_source_lineage_hash=lineage_hash,
        expected_source_manifest_hash=manifest_hash,
    )


def _write_letter(root: Path, letter: dict[str, Any]) -> None:
    _write_json(_letter_path(root), letter)


def _promotion_kwargs(root: Path, **overrides: Any) -> dict[str, Any]:
    request = _request(root)
    kwargs = {
        "project_id": request.project_id,
        "source_letter_id": request.source_letter_id,
        "operator_ref": request.operator_ref,
        "promotion_intent_ref": request.promotion_intent_ref,
        "expected_source_body_hash": request.expected_source_body_hash,
        "expected_source_record_hash": request.expected_source_record_hash,
        "expected_source_lineage_hash": request.expected_source_lineage_hash,
        "expected_source_manifest_hash": request.expected_source_manifest_hash or "",
    }
    kwargs.update(overrides)
    return kwargs


def _fake_draft_pipeline(root: Path):
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
        letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            title=theme,
            text=manual_text or "",
            lifecycle_state="draft",
            created_at="2026-07-04T00:00:00+00:00",
            updated_at="2026-07-04T00:00:00+00:00",
            metadata=dict(initial_metadata or {}),
        )
        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        return letter

    fake_pipeline.calls = calls  # type: ignore[attr-defined]
    return fake_pipeline


def test_valid_governed_draft_yields_deterministic_hashes_promotion_id_and_receipt(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    letter = _load_letter(tmp_state)
    manifest = _load_manifest(tmp_state)
    assert SOURCE_GROUNDED_DRAFTING_METADATA_KEY not in letter["metadata"]
    assert SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY not in letter["metadata"]
    assert SOURCE_GROUNDED_PROSE_APPLICATION_METADATA_KEY not in letter["metadata"]
    assert SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY not in letter["metadata"]

    request = _request(tmp_state)
    receipt = _assert_validation_does_not_mutate(
        tmp_state,
        lambda: build_governed_production_promotion_receipt(request),
    )
    context = _assert_validation_does_not_mutate(
        tmp_state,
        lambda: validate_governed_draft_for_production_promotion(request),
    )

    assert receipt["schema_version"] == RECEIPT_SCHEMA_VERSION
    assert receipt["status"] == "validated"
    assert receipt["project_id"] == PROJECT_ID
    assert receipt["source_letter_id"] == SOURCE_LETTER_ID
    assert receipt["operator_ref"] == "operator:phase1"
    assert receipt["promotion_intent_ref"] == "promotion-intent:primary"
    assert receipt["source_body_hash"] == compute_source_body_hash(letter)
    assert receipt["source_record_hash"] == compute_source_record_hash(letter)
    assert receipt["source_lineage_hash"] == compute_source_lineage_hash(letter)
    assert receipt["source_manifest_hash"] == compute_source_manifest_hash(manifest)
    assert receipt["target_input_text_hash"] == receipt["source_body_hash"]
    assert receipt["authority"] == {
        "production_pipeline": False,
        "release_eligibility": False,
        "approval": False,
        "export": False,
        "schedule": False,
        "publication": False,
        "platform_action": False,
        "oauth": False,
    }
    assert receipt["lineage"]["governed_handoff_id"] == "handoff_001"
    assert receipt["lineage"]["proposal_id"] == "proposal_001"
    assert receipt["lineage"]["canonical_node_id"] == "node_001"
    assert receipt["lineage"]["source_snapshot_ref"] == "snapshot_001"
    assert receipt["lineage"]["source_asset_ids"] == ["asset_source_001"]
    assert receipt["lineage"]["selected_source_passages"] == [
        {
            "asset_id": "asset_source_001",
            "passage_id": "passage_001",
            "text": "Verified selected source passage.",
        }
    ]
    assert context["hashes"]["source_body_hash"] == receipt["source_body_hash"]


def test_same_source_state_and_intent_yields_same_promotion_id(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    request = _request(tmp_state)

    first = _assert_validation_does_not_mutate(
        tmp_state,
        lambda: build_governed_production_promotion_receipt(request),
    )
    second = _assert_validation_does_not_mutate(
        tmp_state,
        lambda: build_governed_production_promotion_receipt(request),
    )

    assert first["promotion_id"] == second["promotion_id"]
    assert first == second


def test_different_promotion_intent_changes_promotion_id(tmp_state: Path) -> None:
    _base_fixture(tmp_state)

    first = build_governed_production_promotion_receipt(_request(tmp_state, promotion_intent_ref="promotion-intent:primary"))
    second = build_governed_production_promotion_receipt(_request(tmp_state, promotion_intent_ref="promotion-intent:secondary"))

    assert first["promotion_id"] != second["promotion_id"]


def test_changed_source_body_rejects_expected_body_hash(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    original = _request(tmp_state)
    changed = _load_letter(tmp_state)
    changed["text"] = "Changed governed draft body."
    _write_letter(tmp_state, changed)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_body_hash_mismatch"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(original),
        )


def test_changed_governed_lineage_rejects_expected_lineage_hash(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    original = _request(tmp_state)
    changed = _load_letter(tmp_state)
    changed["metadata"]["selected_source_passages"][0]["passage_id"] = "passage_002"
    _write_letter(tmp_state, changed)

    request = _request_from_hashes(
        body_hash=original.expected_source_body_hash,
        record_hash=compute_source_record_hash(changed),
        lineage_hash=original.expected_source_lineage_hash,
        manifest_hash=None,
    )
    with pytest.raises(GovernedProductionPromotionValidationError, match="source_lineage_hash_mismatch"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_optional_manifest_hash_mismatch_rejects_when_supplied(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    request = _request(tmp_state, expected_source_manifest_hash="sha256:not-the-manifest")

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_manifest_hash_mismatch"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_missing_governed_handoff_metadata_is_rejected(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    letter = _load_letter(tmp_state)
    letter["metadata"].pop("governed_handoff", None)
    letter["metadata"].pop("governed_handoff_id", None)
    _write_letter(tmp_state, letter)
    request = _request(tmp_state, expected_source_manifest_hash=None)

    with pytest.raises(GovernedProductionPromotionValidationError, match="governed_handoff_metadata_required"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_non_draft_source_lifecycle_is_rejected(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    letter = _load_letter(tmp_state)
    letter["lifecycle_state"] = "registered"
    _write_letter(tmp_state, letter)
    request = _request(tmp_state, expected_source_manifest_hash=None)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_lifecycle_state_not_draft"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_source_with_release_json_is_rejected(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    _write_json(_letter_dir(tmp_state) / "release.json", {"release_id": "release_001"})
    request = _request(tmp_state)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_release_json_not_allowed"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_source_carrying_public_or_release_authority_is_rejected(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    letter = _load_letter(tmp_state)
    letter["metadata"]["governed_handoff"]["authority"]["publication"] = True
    _write_letter(tmp_state, letter)
    request = _request(tmp_state, expected_source_manifest_hash=None)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_authority_not_allowed:governed_handoff.publication"):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


@pytest.mark.parametrize(
    ("operator_ref", "promotion_intent_ref", "expected"),
    [
        ("", "promotion-intent:primary", "operator_ref_required"),
        ("operator:phase1", "", "promotion_intent_ref_required"),
    ],
)
def test_missing_operator_or_promotion_intent_is_rejected(
    tmp_state: Path,
    operator_ref: str,
    promotion_intent_ref: str,
    expected: str,
) -> None:
    _base_fixture(tmp_state)
    request = _request(
        tmp_state,
        operator_ref=operator_ref,
        promotion_intent_ref=promotion_intent_ref,
    )

    with pytest.raises(GovernedProductionPromotionValidationError, match=expected):
        _assert_validation_does_not_mutate(
            tmp_state,
            lambda: build_governed_production_promotion_receipt(request),
        )


def test_absent_manifest_is_allowed_when_manifest_hash_is_not_expected(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    _manifest_path(tmp_state).unlink()
    request = _request(tmp_state, expected_source_manifest_hash=None)

    receipt = _assert_validation_does_not_mutate(
        tmp_state,
        lambda: build_governed_production_promotion_receipt(request),
    )

    assert receipt["source_manifest_hash"] == ""


def test_promote_governed_draft_starts_one_job_and_writes_governed_project_receipt(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    before_source = _capture_source_bytes(tmp_state)
    source_text = _load_letter(tmp_state)["text"]

    result = promote_governed_draft_to_production_derivative(
        **_promotion_kwargs(tmp_state),
        wait_for_completion=True,
        wait_timeout=5,
    )

    assert result.status == "creation_job_started"
    assert result.creation_job_id
    assert result.target_letter_id == compute_target_letter_id(result.promotion_id)
    assert result.promotion_receipt["status"] == "creation_job_started"
    assert result.promotion_receipt["authority"]["production_pipeline"] is True
    assert _capture_source_bytes(tmp_state) == before_source

    assert len(fake_pipeline.calls) == 1  # type: ignore[attr-defined]
    call = fake_pipeline.calls[0]  # type: ignore[attr-defined]
    assert call["manual_text"] == source_text
    assert call["requested_letter_id"] == result.target_letter_id
    assert PRODUCTION_PROMOTION_METADATA_KEY in call["initial_metadata"]
    assert "production_derivative_promotion" not in call["initial_metadata"]

    project = _read_json(_project_path(tmp_state))
    entry = project[GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY][result.promotion_id]
    assert entry["schema_version"] == RECEIPT_SCHEMA_VERSION
    assert entry["status"] == "creation_job_started"
    assert entry["target_letter_id"] == result.target_letter_id
    assert entry["creation_job_id"] == result.creation_job_id
    assert entry["authority"]["production_pipeline"] is True
    for key in ("release_eligibility", "approval", "export", "schedule", "publication", "platform_action", "oauth"):
        assert entry["authority"][key] is False

    target = _read_json(_letter_path(tmp_state, result.target_letter_id))
    metadata = target["metadata"]
    assert target["text"] == _load_letter(tmp_state)["text"]
    assert target["parent_letter_id"] == SOURCE_LETTER_ID
    assert metadata["parent_letter_id"] == SOURCE_LETTER_ID
    assert metadata["revision_of"] == SOURCE_LETTER_ID
    assert metadata["project_id"] == PROJECT_ID
    assert metadata["brand_id"] == "brendon_r_coleman"
    assert metadata["source_asset_ids"] == ["asset_source_001"]
    assert metadata["selected_source_passages"][0]["passage_id"] == "passage_001"
    assert metadata["governed_handoff"]["handoff_id"] == "handoff_001"
    assert metadata[PRODUCTION_PROMOTION_METADATA_KEY]["promotion_id"] == result.promotion_id
    assert metadata[PRODUCTION_PROMOTION_METADATA_KEY]["creation_job_id"] == result.creation_job_id
    assert metadata[PRODUCTION_PROMOTION_METADATA_KEY]["authority"]["production_pipeline"] is True
    assert "production_derivative_promotion" not in metadata


def test_promoted_target_carries_no_release_or_public_authority(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)

    result = promote_governed_draft_to_production_derivative(
        **_promotion_kwargs(tmp_state),
        wait_for_completion=True,
        wait_timeout=5,
    )

    target_dir = _letter_dir(tmp_state, result.target_letter_id)
    target = _read_json(target_dir / "letter.json")
    metadata = target["metadata"]
    assert not (target_dir / "release.json").exists()
    assert metadata["release_eligible"] is False
    assert metadata["approval_status"] == "unapproved"
    assert metadata["review_status"] == "unreviewed"
    assert metadata["publication_state"] == "not_started"
    for key in ("release_eligibility", "approval", "export", "schedule", "publication", "platform_action", "oauth"):
        assert metadata["authority"][key] is False
        assert metadata[PRODUCTION_PROMOTION_METADATA_KEY]["authority"][key] is False
    combined = json.dumps(target, sort_keys=True)
    for forbidden in ("release_state", "scheduled_at", "exported_at", "published_at", "platform_state", "oauth_state"):
        assert forbidden not in combined


def test_promote_governed_draft_is_idempotent_for_same_validated_request(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    kwargs = _promotion_kwargs(tmp_state)

    first = promote_governed_draft_to_production_derivative(
        **kwargs,
        wait_for_completion=True,
        wait_timeout=5,
    )
    second = promote_governed_draft_to_production_derivative(**kwargs)

    assert second.promotion_id == first.promotion_id
    assert second.target_letter_id == first.target_letter_id
    assert second.creation_job_id == first.creation_job_id
    assert len(fake_pipeline.calls) == 1  # type: ignore[attr-defined]
    targets = [
        path
        for path in (tmp_state / "data" / "state" / "letters_of_light").iterdir()
        if path.is_dir() and path.name == first.target_letter_id
    ]
    assert len(targets) == 1
    assert len(creation_manager.list_creation_jobs()) == 1


def test_changed_source_body_blocks_before_any_write(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    kwargs = _promotion_kwargs(tmp_state)
    original_receipt = build_governed_production_promotion_receipt(_request(tmp_state))
    target_id = compute_target_letter_id(original_receipt["promotion_id"])
    changed = _load_letter(tmp_state)
    changed["text"] = "Changed body before promotion."
    _write_letter(tmp_state, changed)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_body_hash_mismatch"):
        promote_governed_draft_to_production_derivative(**kwargs)

    project = _read_json(_project_path(tmp_state))
    assert GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY not in project
    assert creation_manager.list_creation_jobs() == []
    assert not _letter_dir(tmp_state, target_id).exists()
    assert len(fake_pipeline.calls) == 0  # type: ignore[attr-defined]


def test_changed_source_lineage_blocks_before_any_write(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    kwargs = _promotion_kwargs(tmp_state)
    original_receipt = build_governed_production_promotion_receipt(_request(tmp_state))
    target_id = compute_target_letter_id(original_receipt["promotion_id"])
    changed = _load_letter(tmp_state)
    changed["metadata"]["selected_source_passages"][0]["passage_id"] = "changed_passage"
    _write_letter(tmp_state, changed)

    with pytest.raises(GovernedProductionPromotionValidationError, match="source_lineage_hash_mismatch"):
        promote_governed_draft_to_production_derivative(**kwargs)

    project = _read_json(_project_path(tmp_state))
    assert GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY not in project
    assert creation_manager.list_creation_jobs() == []
    assert not _letter_dir(tmp_state, target_id).exists()
    assert len(fake_pipeline.calls) == 0  # type: ignore[attr-defined]


def test_missing_project_index_repairs_from_existing_target_metadata(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    fake_pipeline = _fake_draft_pipeline(tmp_state)
    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)
    receipt = build_governed_production_promotion_receipt(_request(tmp_state))
    target_id = compute_target_letter_id(receipt["promotion_id"])
    repaired_receipt = {
        **receipt,
        "target_letter_id": target_id,
        "creation_job_id": "create_existing",
        "status": "creation_job_started",
        "created_at": "2026-07-04T00:00:00+00:00",
        "authority": {**receipt["authority"], "production_pipeline": True},
    }
    target = copy.deepcopy(_load_letter(tmp_state))
    target["letter_id"] = target_id
    target["parent_letter_id"] = SOURCE_LETTER_ID
    target["metadata"] = {
        "parent_letter_id": SOURCE_LETTER_ID,
        "revision_of": SOURCE_LETTER_ID,
        PRODUCTION_PROMOTION_METADATA_KEY: repaired_receipt,
    }
    _write_json(_letter_path(tmp_state, target_id), target)

    result = promote_governed_draft_to_production_derivative(**_promotion_kwargs(tmp_state))

    assert result.target_letter_id == target_id
    assert result.creation_job_id == "create_existing"
    assert len(fake_pipeline.calls) == 0  # type: ignore[attr-defined]
    project = _read_json(_project_path(tmp_state))
    assert project[GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY][receipt["promotion_id"]]["target_letter_id"] == target_id


def test_failed_job_start_is_recorded_and_not_retried(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_fixture(tmp_state)
    calls = {"count": 0}

    def fail_start(**_: Any) -> dict[str, Any]:
        calls["count"] += 1
        raise RuntimeError("job start failed")

    monkeypatch.setattr(creation_manager, "start_creation_job", fail_start)
    kwargs = _promotion_kwargs(tmp_state)

    with pytest.raises(RuntimeError, match="job start failed"):
        promote_governed_draft_to_production_derivative(**kwargs)
    retry = promote_governed_draft_to_production_derivative(**kwargs)

    assert retry.status == "failed_to_start"
    assert retry.creation_job_id is None
    assert calls["count"] == 1
    project = _read_json(_project_path(tmp_state))
    entry = next(iter(project[GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY].values()))
    assert entry["status"] == "failed_to_start"
    assert entry["authority"]["production_pipeline"] is False


def test_duplicate_targets_with_same_promotion_id_raise_integrity_error(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    receipt = build_governed_production_promotion_receipt(_request(tmp_state))
    for target_id in ("target_dup_001", "target_dup_002"):
        target = copy.deepcopy(_load_letter(tmp_state))
        target["letter_id"] = target_id
        target["metadata"] = {PRODUCTION_PROMOTION_METADATA_KEY: receipt}
        _write_json(_letter_path(tmp_state, target_id), target)

    with pytest.raises(GovernedProductionPromotionIntegrityError, match="duplicate_targets"):
        promote_governed_draft_to_production_derivative(**_promotion_kwargs(tmp_state))


def test_project_index_target_metadata_disagreement_raises_integrity_error(tmp_state: Path) -> None:
    _base_fixture(tmp_state)
    receipt = build_governed_production_promotion_receipt(_request(tmp_state))
    target_id = compute_target_letter_id(receipt["promotion_id"])
    project = _read_json(_project_path(tmp_state))
    project[GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY] = {
        receipt["promotion_id"]: {
            **receipt,
            "target_letter_id": target_id,
            "creation_job_id": "create_existing",
            "status": "creation_job_started",
            "created_at": "2026-07-04T00:00:00+00:00",
            "promotion_receipt": {**receipt, "target_letter_id": target_id},
        }
    }
    _write_json(_project_path(tmp_state), project)
    target = copy.deepcopy(_load_letter(tmp_state))
    target["letter_id"] = target_id
    target["metadata"] = {
        PRODUCTION_PROMOTION_METADATA_KEY: {
            **receipt,
            "promotion_id": "governed_production_promotion.other",
            "target_letter_id": target_id,
        }
    }
    _write_json(_letter_path(tmp_state, target_id), target)

    with pytest.raises(GovernedProductionPromotionIntegrityError, match="target_metadata_disagrees"):
        promote_governed_draft_to_production_derivative(**_promotion_kwargs(tmp_state))
