from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.spine_observability.laviathon_store import (
    LAVIATHON_OBSERVATIONS_FILE,
    append_laviathon_observation,
    list_laviathon_observations,
)


def _base_observation() -> dict:
    return {
        "created_at": "2026-05-15T12:00:00Z",
        "source_context": "stage_1_spine_summary_review",
        "spine_target": "governance",
        "observation_type": "critique",
        "claim": "The summary is useful but still manual-only.",
        "evidence": "The current module accepts operator-entered snapshots only.",
        "recommendation": "Keep persistence local and append-only.",
        "public_safe": False,
        "requires_human_review": True,
        "review_status": "pending",
        "external_action_allowed": False,
    }


def _state_path(root: Path) -> Path:
    return root / "data" / "state" / LAVIATHON_OBSERVATIONS_FILE


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def laviathon_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_valid_observation_appends_to_isolated_state(laviathon_root: Path) -> None:
    stored = append_laviathon_observation(_base_observation())
    rows = _read_jsonl(_state_path(laviathon_root))

    assert len(rows) == 1
    assert rows[0] == stored
    assert stored["observation_id"].startswith("lob_")
    assert stored["external_action_allowed"] is False
    assert stored["recorded_at"] == "2026-05-15T12:00:00Z"
    assert stored["prev_hash"] is None
    assert stored["record_hash"].startswith("sha256:")


def test_list_returns_appended_observations(laviathon_root: Path) -> None:
    first = append_laviathon_observation(_base_observation())
    second_observation = _base_observation()
    second_observation["claim"] = "A second local-only observation is available."
    second = append_laviathon_observation(second_observation)

    listed = list_laviathon_observations()

    assert listed == [first, second]
    assert listed[1]["prev_hash"] == listed[0]["record_hash"]
    assert _state_path(laviathon_root).exists()


def test_invalid_observation_does_not_append(laviathon_root: Path) -> None:
    observation = _base_observation()
    del observation["claim"]

    with pytest.raises(ValueError, match="missing_required_fields:claim"):
        append_laviathon_observation(observation)

    assert not _state_path(laviathon_root).exists()


def test_external_action_allowed_true_does_not_append(laviathon_root: Path) -> None:
    observation = _base_observation()
    observation["external_action_allowed"] = True

    with pytest.raises(ValueError, match="external_action_not_allowed"):
        append_laviathon_observation(observation)

    assert not _state_path(laviathon_root).exists()


def test_public_post_candidate_persists_with_human_review_required(laviathon_root: Path) -> None:
    observation = _base_observation()
    observation["observation_type"] = "public_post_candidate"
    observation["public_safe"] = True
    del observation["requires_human_review"]
    del observation["review_status"]

    stored = append_laviathon_observation(observation)

    assert stored["observation_type"] == "public_post_candidate"
    assert stored["requires_human_review"] is True
    assert stored["review_status"] == "pending"
    assert stored["external_action_allowed"] is False
    assert len(_read_jsonl(_state_path(laviathon_root))) == 1


def test_runtime_state_file_is_created_only_under_signal_agent_root(laviathon_root: Path) -> None:
    append_laviathon_observation(_base_observation())

    path = _state_path(laviathon_root).resolve()
    assert path.exists()
    assert path.name == LAVIATHON_OBSERVATIONS_FILE
    assert path.parent == (laviathon_root / "data" / "state").resolve()
    assert path.relative_to(laviathon_root.resolve())


def test_append_only_behavior_preserves_existing_lines(laviathon_root: Path) -> None:
    append_laviathon_observation(_base_observation())
    path = _state_path(laviathon_root)
    before = path.read_text(encoding="utf-8")

    observation = _base_observation()
    observation["claim"] = "The append-only store preserves existing observation rows."
    append_laviathon_observation(observation)

    after = path.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert len(_read_jsonl(path)) == 2


def test_source_scan_has_no_network_or_external_action_primitives() -> None:
    module_root = Path(__file__).resolve().parents[1] / "app" / "spine_observability"
    source = "\n".join(
        (module_root / name).read_text(encoding="utf-8")
        for name in ("laviathon.py", "laviathon_store.py")
    )

    forbidden_tokens = (
        "requests",
        "urllib",
        "http.client",
        "socket",
        ".post(",
        "send_message",
        "smtp",
        "scrape",
        "schedule",
    )
    for token in forbidden_tokens:
        assert token not in source

