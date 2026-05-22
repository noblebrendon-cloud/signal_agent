from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_pressure.classify import classify_input
from app.reflective_pressure.generate import generate_draft
from app.reflective_pressure.models import build_input_record
from app.reflective_pressure.observe import record_observation
from app.reflective_pressure.store import (
    CLASSIFICATIONS_FILE,
    DRAFTS_FILE,
    INPUTS_FILE,
    OBSERVATIONS_FILE,
    append_classification,
    append_draft,
    append_input,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def rp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_valid_input_creation(rp_root: Path) -> None:
    record = build_input_record(
        source_platform="facebook_group",
        source_type="comment",
        raw_text="People keep turning deeper discussion back into slogans.",
        intended_spine="reflective",
        tags=["Slogans", "pressure"],
        created_at="2026-05-14T12:00:00Z",
    )
    written = append_input(record)

    rows = _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE)
    assert rows == [written]
    assert written["input_id"].startswith("rpi_")
    assert written["source_platform"] == "facebook_group"
    assert written["source_type"] == "comment"
    assert written["intended_spine"] == "reflective"
    assert written["external_action_allowed"] is False
    assert written["irreversible_action_allowed"] is False
    assert written["prev_hash"] is None
    assert written["record_hash"].startswith("sha256:")


def test_invalid_platform_rejected(rp_root: Path) -> None:
    with pytest.raises(ValueError, match="unsupported_source_platform"):
        build_input_record(
            source_platform="myspace",
            source_type="comment",
            raw_text="pressure",
            created_at="2026-05-14T12:00:00Z",
        )
    assert _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE) == []


def test_invalid_source_type_rejected(rp_root: Path) -> None:
    with pytest.raises(ValueError, match="unsupported_source_type"):
        build_input_record(
            source_platform="facebook_group",
            source_type="quote_tweet",
            raw_text="pressure",
            created_at="2026-05-14T12:00:00Z",
        )
    assert _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE) == []


def test_external_action_allowed_true_rejected(rp_root: Path) -> None:
    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="pressure",
            external_action_allowed=True,
            created_at="2026-05-14T12:00:00Z",
        )
    assert _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE) == []


def test_irreversible_action_allowed_true_rejected(rp_root: Path) -> None:
    with pytest.raises(ValueError, match="irreversible_action_allowed_not_allowed"):
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="pressure",
            irreversible_action_allowed=True,
            created_at="2026-05-14T12:00:00Z",
        )
    assert _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE) == []


def test_classification_references_existing_input(rp_root: Path) -> None:
    input_record = _seed_input()
    classification = classify_input(input_record, created_at="2026-05-14T12:01:00Z")

    with pytest.raises(ValueError, match="unknown_input"):
        append_classification(classification)

    append_input(input_record)
    written = append_classification(classification)
    rows = _read_jsonl(rp_root / "data" / "state" / CLASSIFICATIONS_FILE)
    assert rows == [written]
    assert written["input_id"] == input_record["input_id"]


def test_draft_references_input_and_classification(rp_root: Path) -> None:
    input_record, classification = _seed_classification()
    draft = generate_draft(
        input_record,
        classification,
        output_type="reply",
        target_platform="facebook_group",
        created_at="2026-05-14T12:02:00Z",
    )
    written = append_draft(draft)

    rows = _read_jsonl(rp_root / "data" / "state" / DRAFTS_FILE)
    assert rows == [written]
    assert written["human_approved"] is False
    assert written["published"] is False
    assert written["external_action_allowed"] is False


def test_observation_references_draft(rp_root: Path) -> None:
    input_record, classification = _seed_classification()
    draft = append_draft(
        generate_draft(
            input_record,
            classification,
            output_type="reply",
            target_platform="facebook_group",
            created_at="2026-05-14T12:02:00Z",
        )
    )

    observation = record_observation(
        input_id=input_record["input_id"],
        draft_id=draft["draft_id"],
        views=100,
        reactions=12,
        comments=3,
        shares=1,
        recognition_events=2,
        created_at="2026-05-14T13:00:00Z",
    )

    rows = _read_jsonl(rp_root / "data" / "state" / OBSERVATIONS_FILE)
    assert rows == [observation]
    assert observation["views"] == 100
    assert observation["recognition_events"] == 2


def test_append_only_hash_chain_on_inputs(rp_root: Path) -> None:
    first = append_input(
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="first pressure",
            created_at="2026-05-14T12:00:00Z",
        )
    )
    second = append_input(
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="second pressure",
            created_at="2026-05-14T12:01:00Z",
        )
    )

    rows = _read_jsonl(rp_root / "data" / "state" / INPUTS_FILE)
    assert rows == [first, second]
    assert second["prev_hash"] == first["record_hash"]


def _seed_input() -> dict:
    return build_input_record(
        source_platform="facebook_group",
        source_type="comment",
        raw_text="People keep turning every deeper discussion back into slogans instead of pressure.",
        intended_spine="reflective",
        created_at="2026-05-14T12:00:00Z",
    )


def _seed_classification() -> tuple[dict, dict]:
    input_record = append_input(_seed_input())
    classification = append_classification(
        classify_input(input_record, created_at="2026-05-14T12:01:00Z")
    )
    return input_record, classification
