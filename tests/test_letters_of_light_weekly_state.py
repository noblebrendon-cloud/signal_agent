from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.letters_of_light.weekly_models import (
    WeeklyTransitionError,
    can_transition,
    load_weekly_letter,
    require_transition,
)
from app.letters_of_light.weekly_store import append_weekly_transition, register_weekly_letter


CANONICAL_LETTER = Path("docs/letters_of_light/letters/2026-05-17.md")


def _state_root(repo_root: Path) -> Path:
    return repo_root / "data" / "state"


def test_valid_state_transitions() -> None:
    assert can_transition(None, "draft")
    assert can_transition("draft", "reviewed")
    assert can_transition("reviewed", "approved")
    assert can_transition("approved", "published")
    assert can_transition("approved", "printed")
    assert can_transition("published", "shared_in_person")
    assert can_transition("shared_in_person", "archived")


def test_invalid_state_transitions_fail_closed() -> None:
    with pytest.raises(WeeklyTransitionError, match="invalid_weekly_transition:draft->published"):
        require_transition("draft", "published")

    with pytest.raises(WeeklyTransitionError, match="invalid_weekly_transition:archived->published"):
        require_transition("archived", "published")


def test_register_weekly_letter_appends_ledgers(tmp_path: Path) -> None:
    (tmp_path / "data" / "state").mkdir(parents=True)
    letter = load_weekly_letter(CANONICAL_LETTER)

    result = register_weekly_letter(letter, actor_id="tester", repo_root=tmp_path)

    assert result["clean"] is True
    letters_path = _state_root(tmp_path) / "letters_of_light_letters.jsonl"
    transitions_path = _state_root(tmp_path) / "letters_of_light_transitions.jsonl"
    assert letters_path.exists()
    assert transitions_path.exists()

    letter_rows = [json.loads(line) for line in letters_path.read_text(encoding="utf-8").splitlines()]
    transition_rows = [json.loads(line) for line in transitions_path.read_text(encoding="utf-8").splitlines()]
    assert letter_rows[0]["letter_id"] == "lol_2026_05_17"
    assert letter_rows[0]["external_action_allowed"] is False
    assert transition_rows[0]["from_state"] is None
    assert transition_rows[0]["to_state"] == "draft"


def test_append_weekly_transition_writes_hash_chained_record(tmp_path: Path) -> None:
    (tmp_path / "data" / "state").mkdir(parents=True)

    record = append_weekly_transition(
        letter_id="lol_2026_05_17",
        from_state="draft",
        to_state="reviewed",
        actor_id="tester",
        repo_root=tmp_path,
    )

    assert record["letter_id"] == "lol_2026_05_17"
    assert record["to_state"] == "reviewed"
    assert record["external_action_allowed"] is False
    assert record["record_hash"].startswith("sha256:")
    assert record["prev_hash"] is None


def test_transition_external_action_true_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "data" / "state").mkdir(parents=True)

    with pytest.raises(Exception, match="external_action_blocked"):
        append_weekly_transition(
            letter_id="lol_2026_05_17",
            from_state="draft",
            to_state="reviewed",
            actor_id="tester",
            repo_root=tmp_path,
            external_action_allowed=True,
        )
