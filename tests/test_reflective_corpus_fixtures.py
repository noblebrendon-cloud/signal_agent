from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.reflective_corpus.detection import detect_theme_matches
from app.reflective_corpus.models import build_fragment_record, build_theme_record
from app.reflective_corpus.store import append_fragment, append_theme


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reflective_corpus" / "seed_corpus.json"
SAMPLE_TEXTS = [
    "There is a difference between sustaining a mission and manufacturing one for sustainability.",
    "Christian creators are often building theology, media, community, and education with almost no infrastructure beneath them.",
    "Virality is event-based, but thematic identity is memory-based.",
    "The mission existed before the business model.",
    "Media is not secondary anymore. It is infrastructure.",
    "A living corpus matters more than disposable engagement.",
]


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_seed_fixture_contains_only_declared_test_data() -> None:
    payload = _load_seed()

    assert payload["fixture_scope"] == "test_only"
    assert payload["external_action_allowed"] is False
    assert [fragment["text"] for fragment in payload["fragments"]] == SAMPLE_TEXTS
    assert [theme["name"] for theme in payload["themes"]] == [
        "Mission vs Monetization",
        "Christian Creator Infrastructure",
        "Continuity vs Virality",
    ]
    assert len(payload["themes"]) == 3
    assert len(payload["fragments"]) == 6
    assert set(payload) == {"fixture_scope", "external_action_allowed", "themes", "fragments"}
    assert all("draft" not in fragment for fragment in payload["fragments"])
    assert all("publish" not in fragment for fragment in payload["fragments"])


def test_seed_fixture_theme_matches(corpus_root: Path) -> None:
    inserted = _append_seed(corpus_root)
    matches = detect_theme_matches(repo_root=corpus_root)
    matched_fragments_by_theme = _matched_fragment_numbers_by_theme(inserted, matches)

    assert matched_fragments_by_theme == {
        "Mission vs Monetization": [1, 4],
        "Christian Creator Infrastructure": [2, 5],
        "Continuity vs Virality": [3, 6],
    }
    assert all(match["external_action_allowed"] is False for match in matches)


def test_seed_fixture_outputs_are_deterministic(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = _append_seed(first_root)
    second = _append_seed(second_root)
    first_matches = detect_theme_matches(repo_root=first_root)
    second_matches = detect_theme_matches(repo_root=second_root)

    assert [theme["theme_id"] for theme in first["themes"]] == [theme["theme_id"] for theme in second["themes"]]
    assert [fragment["fragment_id"] for fragment in first["fragments"]] == [
        fragment["fragment_id"] for fragment in second["fragments"]
    ]
    assert first_matches == second_matches


def _load_seed() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _append_seed(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    payload = _load_seed()
    themes = [
        append_theme(
            build_theme_record(
                name=theme["name"],
                signal_terms=theme["signal_terms"],
                created_at="2026-05-16T00:00:00Z",
            ),
            repo_root=repo_root,
        )
        for theme in payload["themes"]
    ]
    fragments = [
        append_fragment(
            build_fragment_record(
                source_type=fragment["source_type"],
                source_ref=fragment["source_ref"],
                text=fragment["text"],
                captured_at=f"2026-05-16T00:0{fragment['number']}:00Z",
            ),
            repo_root=repo_root,
        )
        for fragment in payload["fragments"]
    ]
    return {"themes": themes, "fragments": fragments}


def _matched_fragment_numbers_by_theme(
    inserted: dict[str, list[dict[str, Any]]],
    matches: list[dict[str, Any]],
) -> dict[str, list[int]]:
    payload = _load_seed()
    theme_names_by_id = {theme["theme_id"]: theme["name"] for theme in inserted["themes"]}
    fragment_numbers_by_id = {
        fragment_record["fragment_id"]: fragment_fixture["number"]
        for fragment_record, fragment_fixture in zip(inserted["fragments"], payload["fragments"], strict=True)
    }
    grouped: dict[str, set[int]] = {}
    for match in matches:
        grouped.setdefault(theme_names_by_id[match["theme_id"]], set()).add(
            fragment_numbers_by_id[match["fragment_id"]]
        )
    return {theme_name: sorted(numbers) for theme_name, numbers in grouped.items()}
