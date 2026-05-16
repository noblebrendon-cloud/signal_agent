from __future__ import annotations

from pathlib import Path
import socket

import pytest

from app.reflective_corpus.detection import detect_pressures, detect_theme_matches, score_essay_candidate, suggest_essay_candidates
from app.reflective_corpus.models import build_fragment_record, build_theme_record
from app.reflective_corpus.store import append_fragment, append_theme


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_exact_alias_match(corpus_root: Path) -> None:
    del corpus_root
    fragment = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="The work keeps asking for letting go instead of tighter control.",
        )
    )
    theme = append_theme(
        build_theme_record(
            name="Creative Surrender",
            aliases=["letting go"],
            signal_terms=["release"],
        )
    )

    assert detect_theme_matches() == [
        {
            "fragment_id": fragment["fragment_id"],
            "theme_id": theme["theme_id"],
            "matched_terms": ["letting go"],
            "confidence": "medium",
            "external_action_allowed": False,
        }
    ]


def test_signal_term_match(corpus_root: Path) -> None:
    del corpus_root
    fragment = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="Honest attention changed the whole room.",
        )
    )
    theme = append_theme(
        build_theme_record(
            name="Creative Surrender",
            aliases=["letting go"],
            signal_terms=["attention"],
        )
    )

    assert detect_theme_matches() == [
        {
            "fragment_id": fragment["fragment_id"],
            "theme_id": theme["theme_id"],
            "matched_terms": ["attention"],
            "confidence": "low",
            "external_action_allowed": False,
        }
    ]


def test_no_false_match_when_terms_absent(corpus_root: Path) -> None:
    del corpus_root
    append_fragment(
        build_fragment_record(
            source_type="transcript",
            source_ref="call:001",
            text="The discussion stayed practical and concrete.",
        )
    )
    append_theme(
        build_theme_record(
            name="Creative Surrender",
            aliases=["letting go"],
            signal_terms=["attention", "release"],
        )
    )

    assert detect_theme_matches() == []


def test_output_ordering_is_deterministic(corpus_root: Path) -> None:
    del corpus_root
    first = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:b",
            text="Surrender and attention both showed up.",
            captured_at="2026-05-14T12:02:00Z",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:a",
            text="Attention arrived first, then surrender.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )
    surrender = append_theme(
        build_theme_record(
            name="Creative Surrender",
            signal_terms=["surrender"],
        )
    )
    attention = append_theme(
        build_theme_record(
            name="Attention Practice",
            signal_terms=["attention"],
        )
    )

    matches = detect_theme_matches()

    assert matches == sorted(
        matches,
        key=lambda match: (
            match["fragment_id"],
            match["theme_id"],
            tuple(match["matched_terms"]),
        ),
    )
    assert [(match["fragment_id"], match["theme_id"]) for match in matches] == sorted(
        [
            (first["fragment_id"], surrender["theme_id"]),
            (first["fragment_id"], attention["theme_id"]),
            (second["fragment_id"], surrender["theme_id"]),
            (second["fragment_id"], attention["theme_id"]),
        ]
    )
    assert all(match["external_action_allowed"] is False for match in matches)


def test_pressure_detection_for_contrast_pair(corpus_root: Path) -> None:
    del corpus_root
    first = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="The mission is getting pressed by monetization.",
            captured_at="2026-05-14T12:00:00Z",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="Monetization cannot become the mission.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )

    pressures = detect_pressures()

    assert len(pressures) == 1
    assert pressures[0]["contrast_pair"] == ["mission", "monetization"]
    assert pressures[0]["fragment_ids"] == sorted([first["fragment_id"], second["fragment_id"]])
    assert pressures[0]["matched_terms"] == ["mission", "monetization"]
    assert pressures[0]["emotional_weight"] == "medium"
    assert pressures[0]["external_action_allowed"] is False


def test_essay_candidate_scoring_formula_caps_at_ten() -> None:
    assert (
        score_essay_candidate(
            supporting_fragment_count=3,
            source_types=["note", "comment"],
            emotional_weight="high",
            theme_ids=["rct_mission", "rct_money"],
            contrast_pair=["mission", "monetization"],
        )
        == 10
    )
    assert (
        score_essay_candidate(
            supporting_fragment_count=1,
            source_types=["note"],
            emotional_weight="low",
            theme_ids=[],
            contrast_pair=["mission", "monetization"],
        )
        == 3
    )


def test_deterministic_essay_candidate_generation(corpus_root: Path) -> None:
    del corpus_root
    mission = append_theme(build_theme_record(name="Mission", signal_terms=["mission"]))
    money = append_theme(build_theme_record(name="Monetization", signal_terms=["monetization"]))
    append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission keeps getting translated into monetization.",
            captured_at="2026-05-14T12:00:00Z",
        )
    )
    append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="The mission loses coherence when monetization leads.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )
    append_fragment(
        build_fragment_record(
            source_type="transcript",
            source_ref="call:001",
            text="Monetization should serve the mission, not rename it.",
            captured_at="2026-05-14T12:02:00Z",
        )
    )

    first = suggest_essay_candidates()
    second = suggest_essay_candidates()

    assert first == second
    assert len(first) == 1
    candidate = first[0]
    assert candidate["title"] == "Mission vs Monetization"
    assert candidate["status"] == "seed"
    assert candidate["score"] == 10
    assert candidate["supporting_fragment_count"] == 3
    assert candidate["theme_ids"] == sorted([mission["theme_id"], money["theme_id"]])
    assert candidate["external_action_allowed"] is False
    assert "draft" not in candidate


def test_detection_uses_no_network_and_keeps_external_action_false(
    corpus_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del corpus_root

    def _fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network_not_allowed")

    monkeypatch.setattr(socket, "create_connection", _fail_network)
    append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission and monetization are tangled.",
        )
    )

    pressures = detect_pressures()
    candidates = suggest_essay_candidates(pressures=pressures)

    assert all(pressure["external_action_allowed"] is False for pressure in pressures)
    assert all(candidate["external_action_allowed"] is False for candidate in candidates)
