from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_corpus import cli
from app.reflective_corpus.models import build_fragment_record, build_theme_record
from app.reflective_corpus.store import append_fragment, append_theme


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_corpus_detect_themes_outputs_matches(corpus_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del corpus_root
    fragment = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Letting go returned as the useful phrase.",
        )
    )
    theme = append_theme(
        build_theme_record(
            name="Creative Surrender",
            aliases=["letting go"],
        )
    )

    result = cli.main(["corpus-detect-themes"])
    payload = _read_stdout_json(capsys)

    assert result == 0
    assert payload["external_action_allowed"] is False
    assert payload["matches"] == [
        {
            "fragment_id": fragment["fragment_id"],
            "theme_id": theme["theme_id"],
            "matched_terms": ["letting go"],
            "confidence": "medium",
            "external_action_allowed": False,
        }
    ]


def test_corpus_detect_pressures_outputs_pressures(corpus_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del corpus_root
    first = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission is being shaped by monetization.",
        )
    )
    second = append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="Monetization should not swallow mission.",
        )
    )

    result = cli.main(["corpus-detect-pressures"])
    payload = _read_stdout_json(capsys)

    assert result == 0
    assert payload["external_action_allowed"] is False
    assert len(payload["pressures"]) == 1
    assert payload["pressures"][0]["contrast_pair"] == ["mission", "monetization"]
    assert payload["pressures"][0]["fragment_ids"] == sorted([first["fragment_id"], second["fragment_id"]])
    assert payload["pressures"][0]["external_action_allowed"] is False


def test_corpus_suggest_essays_acceptance_demo(corpus_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del corpus_root
    append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission keeps getting reframed as monetization.",
            captured_at="2026-05-14T12:00:00Z",
        )
    )
    append_fragment(
        build_fragment_record(
            source_type="comment",
            source_ref="reply:001",
            text="The mission feels thinner when monetization becomes the center.",
            captured_at="2026-05-14T12:01:00Z",
        )
    )
    append_fragment(
        build_fragment_record(
            source_type="transcript",
            source_ref="call:001",
            text="Monetization can support mission, but it cannot replace it.",
            captured_at="2026-05-14T12:02:00Z",
        )
    )

    result = cli.main(["corpus-suggest-essays"])
    payload = _read_stdout_json(capsys)

    assert result == 0
    assert payload["external_action_allowed"] is False
    assert len(payload["candidates"]) == 1
    candidate = payload["candidates"][0]
    assert candidate["title"] == "Mission vs Monetization"
    assert candidate["status"] == "seed"
    assert candidate["score"] == 10
    assert candidate["supporting_fragment_count"] == 3
    assert candidate["external_action_allowed"] is False
    assert "draft" not in candidate


def test_corpus_reconcile_cli_outputs_clean_report(corpus_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del corpus_root
    append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="A small local fragment.",
        )
    )

    result = cli.main(["corpus-reconcile"])
    payload = _read_stdout_json(capsys)

    assert result == 0
    assert payload["clean"] is True
    assert payload["command"] == "corpus-reconcile"


def test_corpus_report_cli_writes_markdown(corpus_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="A small local fragment.",
        )
    )

    result = cli.main(["corpus-report"])
    payload = _read_stdout_json(capsys)

    assert result == 0
    assert payload["external_action_allowed"] is False
    report_path = corpus_root / "data" / "outputs" / "reflective_corpus" / "corpus_report.md"
    assert report_path.exists()
    assert "## Total Fragments\n- Total fragments: 1" in report_path.read_text(encoding="utf-8")
