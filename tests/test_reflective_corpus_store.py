from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_corpus.models import (
    build_essay_candidate_record,
    build_fragment_record,
    build_pressure_record,
    build_theme_record,
)
from app.reflective_corpus.store import (
    ESSAY_CANDIDATES_FILE,
    FRAGMENTS_FILE,
    PRESSURES_FILE,
    THEMES_FILE,
    append_essay_candidate,
    append_fragment,
    append_pressure,
    append_theme,
    get_essay_candidate_by_id,
    get_fragment_by_id,
    get_pressure_by_id,
    get_theme_by_name,
    list_essay_candidates,
    list_fragments,
    list_pressures,
    list_themes,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_append_fragment_uses_hash_chained_state_file(corpus_root: Path) -> None:
    first = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            captured_at="2026-05-14T12:00:00Z",
            text="Control and surrender keep trading places.",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            captured_at="2026-05-14T12:01:00Z",
            text="The pressure is wanting control while needing surrender.",
        )
    )

    rows = _read_jsonl(corpus_root / "data" / "state" / FRAGMENTS_FILE)
    assert rows == [first, second]
    assert first["prev_hash"] is None
    assert second["prev_hash"] == first["record_hash"]
    assert second["record_hash"].startswith("sha256:")
    assert get_fragment_by_id(first["fragment_id"]) == first
    assert [row["fragment_id"] for row in list_fragments()] == [first["fragment_id"], second["fragment_id"]]


def test_duplicate_fragment_is_rejected(corpus_root: Path) -> None:
    del corpus_root
    fragment = build_fragment_record(
        source_type="note",
        source_ref="journal:001",
        text="The same fragment should not append twice.",
    )
    append_fragment(fragment)

    with pytest.raises(ValueError, match="duplicate_fragment"):
        append_fragment(fragment)


def test_append_theme_and_list_by_status(corpus_root: Path) -> None:
    active = append_theme(
        build_theme_record(
            name="Creative Surrender",
            signal_terms=["control", "surrender"],
            created_at="2026-05-14T12:00:00Z",
        )
    )
    dormant = append_theme(
        build_theme_record(
            name="Dormant Thread",
            signal_terms=["archive"],
            status="dormant",
            created_at="2026-05-14T12:01:00Z",
        )
    )

    rows = _read_jsonl(corpus_root / "data" / "state" / THEMES_FILE)
    assert rows == [active, dormant]
    assert get_theme_by_name("creative surrender") == active
    assert [row["theme_id"] for row in list_themes(status="ACTIVE")] == [active["theme_id"]]


def test_duplicate_theme_is_rejected(corpus_root: Path) -> None:
    del corpus_root
    theme = build_theme_record(name="Creative Surrender")
    append_theme(theme)

    with pytest.raises(ValueError, match="duplicate_theme"):
        append_theme(theme)


def test_append_pressure_and_essay_candidate_state_files(corpus_root: Path) -> None:
    theme = append_theme(
        build_theme_record(
            name="Mission",
            signal_terms=["mission"],
            created_at="2026-05-14T12:00:00Z",
        )
    )
    first = append_fragment(
        build_fragment_record(
            source_type="transcript",
            source_ref="call:001",
            text="Mission keeps colliding with monetization.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="Monetization is starting to bend the mission.",
            captured_at="2026-05-14T12:02:00Z",
        )
    )
    pressure = append_pressure(
        build_pressure_record(
            fragment_ids=[first["fragment_id"], second["fragment_id"]],
            contrast_pair=["mission", "monetization"],
            related_theme_ids=[theme["theme_id"]],
            emotional_weight="medium",
            detected_at="2026-05-14T12:02:00Z",
        )
    )
    candidate = append_essay_candidate(
        build_essay_candidate_record(
            title="Mission vs Monetization",
            pressure_ids=[pressure["pressure_id"]],
            fragment_ids=[first["fragment_id"], second["fragment_id"]],
            theme_ids=[theme["theme_id"]],
            contrast_pair=["mission", "monetization"],
            supporting_fragment_count=2,
            source_types=["transcript", "comment"],
            score=8,
            created_at="2026-05-14T12:02:00Z",
        )
    )

    state_root = corpus_root / "data" / "state"
    assert (state_root / "reflective_fragments.jsonl").exists()
    assert (state_root / "reflective_themes.jsonl").exists()
    assert _read_jsonl(state_root / PRESSURES_FILE) == [pressure]
    assert _read_jsonl(state_root / ESSAY_CANDIDATES_FILE) == [candidate]
    assert pressure["prev_hash"] is None
    assert candidate["prev_hash"] is None
    assert get_pressure_by_id(pressure["pressure_id"]) == pressure
    assert get_essay_candidate_by_id(candidate["candidate_id"]) == candidate
    assert [row["pressure_id"] for row in list_pressures()] == [pressure["pressure_id"]]
    assert [row["candidate_id"] for row in list_essay_candidates(status="seed")] == [candidate["candidate_id"]]


def test_pressure_and_candidate_references_must_exist(corpus_root: Path) -> None:
    del corpus_root
    with pytest.raises(ValueError, match="unknown_fragment:rcf_missing"):
        append_pressure(
            build_pressure_record(
                fragment_ids=["rcf_missing"],
                contrast_pair=["mission", "monetization"],
            )
        )

    with pytest.raises(ValueError, match="unknown_pressure:rcp_missing"):
        append_essay_candidate(
            build_essay_candidate_record(
                title="Mission vs Monetization",
                pressure_ids=["rcp_missing"],
                fragment_ids=["rcf_missing"],
                contrast_pair=["mission", "monetization"],
                supporting_fragment_count=1,
                source_types=["note"],
                score=3,
            )
        )
