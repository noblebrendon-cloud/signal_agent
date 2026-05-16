from __future__ import annotations

import pytest

from app.reflective_corpus.models import (
    build_essay_candidate_record,
    build_fragment_record,
    build_pressure_record,
    build_theme_record,
    validate_essay_candidate_record,
    validate_fragment_record,
    validate_pressure_record,
    validate_theme_record,
)


def test_fragment_id_is_deterministic_from_normalized_material() -> None:
    first = build_fragment_record(
        source_type="note",
        source_ref=" journal:001 ",
        captured_at="2026-05-14T12:00:00Z",
        text="  Control loosens when attention gets honest. ",
        tags=["Attention", " control "],
    )
    second = build_fragment_record(
        source_type="NOTE",
        source_ref="journal:001",
        captured_at="2026-05-15T12:00:00Z",
        text="Control loosens when attention gets honest.",
        tags=["control", "attention"],
    )

    assert first["fragment_id"] == second["fragment_id"]
    assert first["fragment_id"].startswith("rcf_")
    assert first["external_action_allowed"] is False
    assert first["tags"] == ["attention", "control"]
    validate_fragment_record(first)


def test_fragment_rejects_unsupported_source_and_external_action() -> None:
    with pytest.raises(ValueError, match="unsupported_source_type"):
        build_fragment_record(
            source_type="linkedin",
            source_ref="manual",
            text="not supported for this local corpus",
        )

    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_fragment_record(
            source_type="note",
            source_ref="manual",
            text="local only",
            external_action_allowed=True,
        )


def test_theme_validation_normalizes_terms_and_status() -> None:
    theme = build_theme_record(
        name="Creative Surrender",
        aliases=["letting go", "Letting Go"],
        description=" Work that stops trying to control the signal. ",
        signal_terms=["control", "surrender", "attention"],
        created_at="2026-05-14",
        status="ACTIVE",
    )

    assert theme["theme_id"].startswith("rct_")
    assert theme["created_at"] == "2026-05-14T00:00:00Z"
    assert theme["aliases"] == ["letting go"]
    assert theme["description"] == "Work that stops trying to control the signal."
    assert theme["signal_terms"] == ["attention", "control", "surrender"]
    assert theme["status"] == "active"
    assert theme["external_action_allowed"] is False
    validate_theme_record(theme)


def test_theme_rejects_invalid_status_and_external_action() -> None:
    with pytest.raises(ValueError, match="unsupported_theme_status"):
        build_theme_record(name="Drift", status="retired")

    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_theme_record(name="Drift", external_action_allowed=True)


def test_pressure_validation_normalizes_support_and_weight() -> None:
    pressure = build_pressure_record(
        fragment_ids=["rcf_b", "rcf_a"],
        contrast_pair=["mission", "monetization"],
        matched_terms=["Monetization", "mission"],
        related_theme_ids=["rct_b", "rct_a"],
        emotional_weight="HIGH",
        detected_at="2026-05-14",
    )

    assert pressure["pressure_id"].startswith("rcp_")
    assert pressure["fragment_ids"] == ["rcf_a", "rcf_b"]
    assert pressure["contrast_pair"] == ["mission", "monetization"]
    assert pressure["matched_terms"] == ["mission", "monetization"]
    assert pressure["related_theme_ids"] == ["rct_a", "rct_b"]
    assert pressure["emotional_weight"] == "high"
    assert pressure["detected_at"] == "2026-05-14T00:00:00Z"
    assert pressure["external_action_allowed"] is False
    validate_pressure_record(pressure)


def test_essay_candidate_validation_normalizes_seed_record() -> None:
    candidate = build_essay_candidate_record(
        title="Mission vs Monetization",
        pressure_ids=["rcp_1"],
        fragment_ids=["rcf_2", "rcf_1", "rcf_3"],
        theme_ids=["rct_2", "rct_1"],
        contrast_pair=["mission", "monetization"],
        supporting_fragment_count=3,
        source_types=["note", "comment"],
        score=10,
        created_at="2026-05-14T12:00:00Z",
    )

    assert candidate["candidate_id"].startswith("rce_")
    assert candidate["status"] == "seed"
    assert candidate["score"] == 10
    assert candidate["source_types"] == ["comment", "note"]
    assert candidate["external_action_allowed"] is False
    validate_essay_candidate_record(candidate)


def test_pressure_and_candidate_reject_external_action() -> None:
    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_pressure_record(
            fragment_ids=["rcf_1"],
            contrast_pair=["mission", "monetization"],
            external_action_allowed=True,
        )

    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_essay_candidate_record(
            title="Mission vs Monetization",
            pressure_ids=["rcp_1"],
            fragment_ids=["rcf_1"],
            contrast_pair=["mission", "monetization"],
            supporting_fragment_count=1,
            source_types=["note"],
            score=3,
            external_action_allowed=True,
        )
