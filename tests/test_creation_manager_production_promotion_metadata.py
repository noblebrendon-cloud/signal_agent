from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.letters_of_light import creation_manager
from app.letters_of_light.contract import LetterOfLight
from app.letters_of_light.creation_manager import start_creation_job, wait_for_creation_job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _letters_root(root: Path) -> Path:
    return root / "data" / "state" / "letters_of_light"


def _letter_dir(root: Path, letter_id: str) -> Path:
    return _letters_root(root) / letter_id


def _capture_letter_bytes(root: Path, letter_id: str) -> dict[str, bytes]:
    directory = _letter_dir(root, letter_id)
    return {
        name: (directory / name).read_bytes() if (directory / name).exists() else b""
        for name in ("letter.json", "manifest.json")
    }


def _write_source_letter(root: Path, letter_id: str = "source_governed_001") -> None:
    payload = {
        "letter_id": letter_id,
        "artifact_type": "letter_of_light",
        "theme": "source",
        "title": "Source Governed Draft",
        "text": "Source body must remain unchanged.",
        "lifecycle_state": "draft",
        "metadata": {
            "project_id": "project_source",
            "governed_handoff": {"handoff_id": "handoff_source"},
        },
    }
    _write_json(_letter_dir(root, letter_id) / "letter.json", payload)
    _write_json(_letter_dir(root, letter_id) / "manifest.json", payload)


def _fake_pipeline(root: Path, *, lifecycle_state: str = "draft", calls: list[dict[str, Any]] | None = None):
    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        requested_letter_id: str | None = None,
        initial_metadata: dict[str, Any] | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        del seed
        letter_id = requested_letter_id or "target_from_fake_pipeline"
        metadata = dict(initial_metadata or {})
        if calls is not None:
            calls.append(
                {
                    "theme": theme,
                    "manual_text": manual_text,
                    "requested_letter_id": requested_letter_id,
                    "initial_metadata": metadata,
                }
            )

        if progress_callback:
            progress_callback(
                {
                    "letter_id": letter_id,
                    "lifecycle_state": lifecycle_state,
                    "event_type": "LETTER_CREATED",
                    "timestamp": _now(),
                    "summary": {"letter_id": letter_id},
                }
            )

        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            title=f"The Letter of {theme.title()}",
            text=manual_text or "",
            lifecycle_state=lifecycle_state,
            evaluation={"decision": "accept", "total": 27, "audio_alignment": 4},
            created_at=_now(),
            updated_at=_now(),
            metadata=metadata,
        )
        payload = letter.to_dict()
        _write_json(_letter_dir(root, letter_id) / "letter.json", payload)
        _write_json(_letter_dir(root, letter_id) / "manifest.json", payload)
        return letter

    return fake_pipeline


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def test_governed_production_promotion_metadata_passes_to_target_and_manifest(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source_letter(tmp_state)
    source_before = _capture_letter_bytes(tmp_state, "source_governed_001")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(creation_manager, "run_pipeline", _fake_pipeline(tmp_state, calls=calls))

    job = start_creation_job(
        theme="governed production derivative",
        manual_text="Source body must become target input.",
        parent_letter_id="source_governed_001",
        project_id="project_001",
        source_asset_ids=["asset_001"],
        source_passages=[
            {
                "asset_id": "asset_001",
                "passage_id": "passage_001",
                "page_number": 3,
                "text": "Selected source passage.",
            }
        ],
        brand_id="brendon_r_coleman",
        brand_version="1",
        requested_letter_id="target_governed_001",
        initial_letter_metadata={
            "parent_letter_id": "source_governed_001",
            "revision_of": "source_governed_001",
            "project_id": "project_001",
            "brand_id": "brendon_r_coleman",
            "brand_version": "1",
            "governed_handoff": {"handoff_id": "handoff_001", "proposal_id": "proposal_001"},
            "source_grounding": {"source_snapshot_ref": "snapshot_001"},
            "source_snapshot_ref": "snapshot_001",
            "source_support_refs": ["support_001"],
        },
        production_promotion_receipt={
            "schema_version": "letters_of_light.production_promotion.v1",
            "promotion_id": "governed_production_promotion.test",
            "project_id": "project_001",
            "source_letter_id": "source_governed_001",
            "target_letter_id": "target_governed_001",
            "authority": {
                "production_pipeline": False,
                "release_eligibility": False,
                "approval": False,
                "export": False,
                "schedule": False,
                "publication": False,
                "platform_action": False,
                "oauth": False,
            },
        },
    )

    assert job["production_promotion_receipt"]["authority"]["production_pipeline"] is True
    assert job["created_by_governed_production_promotion"] is True
    assert job["created_by_governed_draft_promotion"] is False
    assert "production_promotion" in job["initial_letter_metadata"]
    assert "production_derivative_promotion" not in job["initial_letter_metadata"]

    finished = wait_for_creation_job(job["job_id"], timeout=5)
    assert finished is not None
    assert finished["status"] == "succeeded"
    assert finished["production_promotion_receipt"]["creation_job_id"] == job["job_id"]

    target_dir = _letter_dir(tmp_state, "target_governed_001")
    target = _read_json(target_dir / "letter.json")
    manifest = _read_json(target_dir / "manifest.json")

    for payload in (target, manifest):
        metadata = payload["metadata"]
        receipt = metadata["production_promotion"]
        assert "production_derivative_promotion" not in metadata
        assert receipt["promotion_id"] == "governed_production_promotion.test"
        assert receipt["creation_job_id"] == job["job_id"]
        assert receipt["authority"]["production_pipeline"] is True
        for key in (
            "release_eligibility",
            "approval",
            "export",
            "schedule",
            "publication",
            "platform_action",
            "oauth",
        ):
            assert receipt["authority"][key] is False

        assert payload["parent_letter_id"] == "source_governed_001"
        assert metadata["parent_letter_id"] == "source_governed_001"
        assert metadata["revision_of"] == "source_governed_001"
        assert metadata["project_id"] == "project_001"
        assert metadata["brand_id"] == "brendon_r_coleman"
        assert metadata["brand_version"] == "1"
        assert metadata["source_asset_ids"] == ["asset_001"]
        assert metadata["selected_source_passages"][0]["passage_id"] == "passage_001"
        assert metadata["governed_handoff"]["handoff_id"] == "handoff_001"
        assert metadata["source_grounding"]["source_snapshot_ref"] == "snapshot_001"
        assert metadata["source_snapshot_ref"] == "snapshot_001"
        assert metadata["source_support_refs"] == ["support_001"]

    assert calls[0]["manual_text"] == "Source body must become target input."
    assert calls[0]["requested_letter_id"] == "target_governed_001"
    assert "production_promotion" in calls[0]["initial_metadata"]
    assert "production_derivative_promotion" not in calls[0]["initial_metadata"]
    assert not (target_dir / "release.json").exists()
    assert _capture_letter_bytes(tmp_state, "source_governed_001") == source_before


def test_governed_registered_job_suppresses_release_eligibility_check(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        creation_manager,
        "run_pipeline",
        _fake_pipeline(tmp_state, lifecycle_state="registered"),
    )

    def fail_if_called(letter_id: str) -> object:
        raise AssertionError(f"check_release_eligibility should not run for {letter_id}")

    monkeypatch.setattr(creation_manager, "check_release_eligibility", fail_if_called)

    job = start_creation_job(
        theme="governed registered",
        requested_letter_id="target_registered_governed",
        production_promotion_receipt={
            "promotion_id": "governed_production_promotion.registered",
            "authority": {"production_pipeline": False},
        },
    )
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert finished["lifecycle_state"] == "registered"
    assert finished["release_eligible"] is False
    assert finished["release_reasons"] == [
        "governed production promotion does not grant release eligibility"
    ]


def test_normal_registered_job_still_uses_release_eligibility_check(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        creation_manager,
        "run_pipeline",
        _fake_pipeline(tmp_state, lifecycle_state="registered"),
    )

    class Check:
        eligible = True
        reasons = ["normal release check ran"]

    def fake_check(letter_id: str) -> Check:
        calls.append(letter_id)
        return Check()

    monkeypatch.setattr(creation_manager, "check_release_eligibility", fake_check)

    job = start_creation_job(theme="normal registered", requested_letter_id="target_registered_normal")
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert calls == ["target_registered_normal"]
    assert finished["release_eligible"] is True
    assert finished["release_reasons"] == ["normal release check ran"]


def test_old_production_derivative_promotion_still_uses_release_eligibility_check(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        creation_manager,
        "run_pipeline",
        _fake_pipeline(tmp_state, lifecycle_state="registered"),
    )

    class Check:
        eligible = True
        reasons = ["old production derivative check ran"]

    def fake_check(letter_id: str) -> Check:
        calls.append(letter_id)
        return Check()

    monkeypatch.setattr(creation_manager, "check_release_eligibility", fake_check)

    job = start_creation_job(
        theme="old production derivative",
        requested_letter_id="target_registered_old_promotion",
        promotion_receipt={
            "promotion_id": "production_derivative_promotion.existing",
            "source_letter_id": "source_governed_001",
            "target_letter_id": "target_registered_old_promotion",
        },
    )
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert calls == ["target_registered_old_promotion"]
    assert finished["release_eligible"] is True
    assert finished["release_reasons"] == ["old production derivative check ran"]
    assert finished["created_by_governed_draft_promotion"] is True
    assert finished["created_by_governed_production_promotion"] is False

    target = _read_json(_letter_dir(tmp_state, "target_registered_old_promotion") / "letter.json")
    assert "production_derivative_promotion" in target["metadata"]
    assert "production_promotion" not in target["metadata"]
