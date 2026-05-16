from __future__ import annotations

from pathlib import Path

import pytest

from app.reflective_corpus.models import (
    build_essay_candidate_record,
    build_fragment_record,
    build_pressure_record,
    build_theme_record,
)
from app.reflective_corpus.report import REPORT_PATH, generate_corpus_report, render_corpus_report
from app.reflective_corpus.store import append_essay_candidate, append_fragment, append_pressure, append_theme


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_report_is_deterministic(corpus_root: Path) -> None:
    mission = append_theme(build_theme_record(name="Mission", signal_terms=["mission"]))
    monetization = append_theme(build_theme_record(name="Monetization", signal_terms=["monetization"]))
    first = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission keeps getting reframed as monetization.",
            captured_at="2026-05-14T12:00:00Z",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="Monetization should serve mission instead of replacing it.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )
    pressure = append_pressure(
        build_pressure_record(
            fragment_ids=[first["fragment_id"], second["fragment_id"]],
            contrast_pair=["mission", "monetization"],
            related_theme_ids=[mission["theme_id"], monetization["theme_id"]],
            emotional_weight="medium",
            detected_at="2026-05-14T12:01:00Z",
        )
    )
    append_essay_candidate(
        build_essay_candidate_record(
            title="Mission vs Monetization",
            pressure_ids=[pressure["pressure_id"]],
            fragment_ids=[first["fragment_id"], second["fragment_id"]],
            theme_ids=[mission["theme_id"], monetization["theme_id"]],
            contrast_pair=["mission", "monetization"],
            supporting_fragment_count=2,
            source_types=["note", "comment"],
            score=10,
            created_at="2026-05-14T12:01:00Z",
        )
    )

    first_text = render_corpus_report(repo_root=corpus_root)
    second_text = render_corpus_report(repo_root=corpus_root)
    result = generate_corpus_report(repo_root=corpus_root)
    written = (corpus_root / REPORT_PATH).read_text(encoding="utf-8")

    assert first_text == second_text
    assert written == first_text
    assert result["external_action_allowed"] is False
    assert result["path"].endswith("data\\outputs\\reflective_corpus\\corpus_report.md") or result["path"].endswith(
        "data/outputs/reflective_corpus/corpus_report.md"
    )
    assert "## Total Fragments\n- Total fragments: 2" in first_text
    assert "## Active Themes\n- Active themes: 2" in first_text
    assert "## Detected Pressures\n- Detected pressures: 1" in first_text
    assert "## Essay Candidates by Score\n- 10: Mission vs Monetization (seed)" in first_text
    assert "## Top Recurring Themes" in first_text
    assert "## Unresolved Tensions\n- Mission vs Monetization" in first_text
    assert "## Next 5 Essay Candidates\n- Mission vs Monetization (score 10, 2 fragments)" in first_text
