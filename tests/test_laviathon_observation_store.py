from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention.jsonl_store import compute_record_hash
from app.spine_observability.laviathon import normalize_observation
from app.spine_observability.laviathon_store import (
    LAVIATHON_OBSERVATIONS_FILE,
    append_laviathon_observation,
    list_laviathon_observations,
    list_review_candidates,
)


def _base_observation() -> dict:
    return {
        "entity_id": "entity.alpha",
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
    assert stored["entity_id"] == "entity.alpha"
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


def test_new_observation_write_requires_entity_id(laviathon_root: Path) -> None:
    observation = _base_observation()
    del observation["entity_id"]

    with pytest.raises(ValueError, match="missing_entity_id"):
        append_laviathon_observation(observation)

    assert not _state_path(laviathon_root).exists()


def test_legacy_observation_without_entity_id_remains_readable(laviathon_root: Path) -> None:
    legacy = _base_observation()
    del legacy["entity_id"]
    stored = append_laviathon_observation(_base_observation())
    legacy_payload = {
        **legacy,
        "observation_id": normalize_observation(legacy)["observation_id"],
        "recorded_at": "2026-05-15T12:05:00Z",
        "prev_hash": stored["record_hash"],
    }
    legacy_payload["record_hash"] = compute_record_hash(legacy_payload)
    with open(_state_path(laviathon_root), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(legacy_payload, sort_keys=True) + "\n")

    listed = list_laviathon_observations()

    assert listed[-1] == legacy_payload
    assert "entity_id" not in listed[-1]


def test_legacy_observation_hash_fixture_remains_stable() -> None:
    legacy = _base_observation()
    del legacy["entity_id"]
    normalized = normalize_observation(legacy)
    payload = {
        **normalized,
        "recorded_at": "2026-05-15T12:00:00Z",
        "prev_hash": None,
    }

    assert normalized["observation_id"] == "lob_22d83919abce8999"
    assert compute_record_hash(payload) == (
        "sha256:a8072150e21abd8d43ede4e16919e75a55c6673f3f5bb48d2b9802b7a428ab75"
    )


def test_new_observation_hash_incorporates_entity_identity() -> None:
    first = normalize_observation(_base_observation(), require_entity_id=True)
    second_record = _base_observation()
    second_record["entity_id"] = "entity.beta"
    second = normalize_observation(second_record, require_entity_id=True)

    first_hash = compute_record_hash(
        {**first, "recorded_at": "2026-05-15T12:00:00Z", "prev_hash": None}
    )
    second_hash = compute_record_hash(
        {**second, "recorded_at": "2026-05-15T12:00:00Z", "prev_hash": None}
    )

    assert first["observation_id"] == "lob_bd72216553078c45"
    assert second["observation_id"] == "lob_f817c1a1758cc1f2"
    assert first_hash == "sha256:58d369c0409d8ca5b38998011f8d2a186587584255e056af00ea9152e2ac39c4"
    assert second_hash == "sha256:e30a9498851843e05b746234bbb0cd695cfb8a3292a68a156f949e061bcc291b"
    assert first_hash != second_hash


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


def test_list_review_candidates_returns_pending_human_review_observations(laviathon_root: Path) -> None:
    stored = append_laviathon_observation(_base_observation())

    candidates = list_review_candidates()

    assert candidates == [stored]
    assert _state_path(laviathon_root).exists()


def test_list_review_candidates_excludes_non_human_review_observations(laviathon_root: Path) -> None:
    observation = _base_observation()
    observation["requires_human_review"] = False
    stored = append_laviathon_observation(observation)

    assert stored["requires_human_review"] is False
    assert list_review_candidates() == []
    assert len(_read_jsonl(_state_path(laviathon_root))) == 1


def test_list_review_candidates_excludes_approved_and_rejected_by_default(laviathon_root: Path) -> None:
    del laviathon_root
    approved = _base_observation()
    approved["claim"] = "An approved local observation exists."
    approved["review_status"] = "approved"
    append_laviathon_observation(approved)
    rejected = _base_observation()
    rejected["claim"] = "A rejected local observation exists."
    rejected["review_status"] = "rejected"
    append_laviathon_observation(rejected)
    pending = _base_observation()
    pending["claim"] = "A pending local observation exists."
    pending_stored = append_laviathon_observation(pending)

    candidates = list_review_candidates()

    assert candidates == [pending_stored]


def test_list_review_candidates_include_all_statuses_includes_reviewed_records(laviathon_root: Path) -> None:
    del laviathon_root
    approved = _base_observation()
    approved["claim"] = "An approved local observation exists."
    approved["review_status"] = "approved"
    approved_stored = append_laviathon_observation(approved)
    rejected = _base_observation()
    rejected["claim"] = "A rejected local observation exists."
    rejected["review_status"] = "rejected"
    rejected_stored = append_laviathon_observation(rejected)

    candidates = list_review_candidates(include_all_statuses=True)

    assert candidates == sorted(
        [approved_stored, rejected_stored],
        key=lambda row: (row["created_at"], row["observation_id"]),
    )


def test_list_review_candidates_filters_by_public_post_candidate(laviathon_root: Path) -> None:
    del laviathon_root
    critique = _base_observation()
    critique["claim"] = "A critique candidate exists."
    append_laviathon_observation(critique)
    public_candidate = _base_observation()
    public_candidate["observation_type"] = "public_post_candidate"
    public_candidate["claim"] = "A public candidate requires human review."
    public_candidate["public_safe"] = True
    public_stored = append_laviathon_observation(public_candidate)

    candidates = list_review_candidates(observation_type="public_post_candidate")

    assert candidates == [public_stored]
    assert candidates[0]["requires_human_review"] is True
    assert candidates[0]["review_status"] == "pending"


def test_list_review_candidates_ordering_is_deterministic(laviathon_root: Path) -> None:
    del laviathon_root
    later = _base_observation()
    later["created_at"] = "2026-05-15T13:00:00Z"
    later["claim"] = "Later candidate."
    later_stored = append_laviathon_observation(later)
    earlier = _base_observation()
    earlier["created_at"] = "2026-05-15T11:00:00Z"
    earlier["claim"] = "Earlier candidate."
    earlier_stored = append_laviathon_observation(earlier)
    same_time = _base_observation()
    same_time["created_at"] = "2026-05-15T11:00:00Z"
    same_time["claim"] = "Same timestamp candidate."
    same_time_stored = append_laviathon_observation(same_time)

    candidates = list_review_candidates()

    assert candidates == sorted(
        [later_stored, earlier_stored, same_time_stored],
        key=lambda row: (row["created_at"], row["observation_id"]),
    )


def test_list_review_candidates_does_not_mutate_state_file(laviathon_root: Path) -> None:
    append_laviathon_observation(_base_observation())
    path = _state_path(laviathon_root)
    before = path.read_text(encoding="utf-8")

    assert list_review_candidates()

    after = path.read_text(encoding="utf-8")
    assert after == before


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
