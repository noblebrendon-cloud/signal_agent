from __future__ import annotations

from pathlib import Path

import pytest

from app.letters_of_light.weekly_models import (
    WeeklyExternalActionError,
    WeeklyLetterValidationError,
    content_hash,
    derive_letter_id,
    load_weekly_letter,
    weekly_letter_from_payload,
)


CANONICAL_LETTER = Path("docs/letters_of_light/letters/2026-05-17.md")


def _valid_payload() -> dict:
    return {
        "letter_id": "lol_2026_05_17",
        "title": "Peace For The Next Step",
        "week_date": "2026-05-17",
        "scripture_refs": ["John 14:27"],
        "song": {"title": "Peace Be Still", "reference": "title reference only"},
        "audience_notes": ["weekly readers"],
        "status": "draft",
        "reflection_questions": ["What is one next step?"],
        "closing_prayer": "Amen.",
    }


def test_valid_weekly_letter_loading() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)

    assert letter.letter_id == "lol_2026_05_17"
    assert letter.title == "Peace For The Next Step"
    assert letter.week_date == "2026-05-17"
    assert letter.status == "draft"
    assert letter.external_action_allowed is False
    assert letter.send_externally is False
    assert letter.body


def test_missing_required_fields_fail() -> None:
    payload = _valid_payload()
    payload.pop("title")

    with pytest.raises(WeeklyLetterValidationError, match="missing_required_fields:title"):
        weekly_letter_from_payload(payload, body="Body")


def test_malformed_scripture_refs_fail() -> None:
    payload = _valid_payload()
    payload["scripture_refs"] = "John 14:27"

    with pytest.raises(WeeklyLetterValidationError, match="malformed_scripture_refs"):
        weekly_letter_from_payload(payload, body="Body")


def test_missing_song_reference_fails() -> None:
    payload = _valid_payload()
    payload["song"] = {"title": "Peace Be Still"}

    with pytest.raises(WeeklyLetterValidationError, match="missing_song_reference"):
        weekly_letter_from_payload(payload, body="Body")


def test_deterministic_letter_id_or_hash_behavior() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    second_load = load_weekly_letter(CANONICAL_LETTER)

    assert derive_letter_id("2026-05-17") == "lol_2026_05_17"
    assert letter.content_hash == second_load.content_hash
    assert content_hash(letter.canonical_payload()) == letter.content_hash


def test_external_action_allowed_true_fails_closed() -> None:
    payload = _valid_payload()
    payload["external_action_allowed"] = True

    with pytest.raises(WeeklyExternalActionError, match="external_action_blocked"):
        weekly_letter_from_payload(payload, body="Body")


def test_send_externally_true_fails_closed() -> None:
    payload = _valid_payload()
    payload["send_externally"] = True

    with pytest.raises(WeeklyExternalActionError, match="external_action_blocked"):
        weekly_letter_from_payload(payload, body="Body")
