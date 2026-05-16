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
from app.reflective_corpus.reconcile import reconcile_reflective_corpus_state
from app.reflective_corpus.store import (
    ESSAY_CANDIDATES_FILE,
    FRAGMENTS_FILE,
    PRESSURES_FILE,
    append_essay_candidate,
    append_fragment,
    append_pressure,
    append_theme,
)


@pytest.fixture
def corpus_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_clean_corpus_passes(corpus_root: Path) -> None:
    theme = append_theme(build_theme_record(name="Mission", signal_terms=["mission"]))
    fragment = append_fragment(
        build_fragment_record(
            source_type="note",
            source_ref="journal:001",
            text="Mission and monetization need to be held honestly.",
        )
    )
    pressure = append_pressure(
        build_pressure_record(
            fragment_ids=[fragment["fragment_id"]],
            contrast_pair=["mission", "monetization"],
            related_theme_ids=[theme["theme_id"]],
        )
    )
    append_essay_candidate(
        build_essay_candidate_record(
            title="Mission vs Monetization",
            pressure_ids=[pressure["pressure_id"]],
            fragment_ids=[fragment["fragment_id"]],
            theme_ids=[theme["theme_id"]],
            contrast_pair=["mission", "monetization"],
            supporting_fragment_count=1,
            source_types=["note"],
            score=3,
        )
    )

    report = reconcile_reflective_corpus_state(repo_root=corpus_root)

    assert report["clean"] is True
    assert report["summary"]["failure_count"] == 0
    assert report["summary"]["fragment_count"] == 1
    assert report["summary"]["theme_count"] == 1
    assert report["summary"]["pressure_count"] == 1
    assert report["summary"]["essay_candidate_count"] == 1


def test_broken_references_fail(corpus_root: Path) -> None:
    pressure = build_pressure_record(
        fragment_ids=["rcf_missing"],
        contrast_pair=["mission", "monetization"],
        related_theme_ids=["rct_missing"],
    )
    _write_jsonl(corpus_root / "data" / "state" / PRESSURES_FILE, [pressure])
    candidate = build_essay_candidate_record(
        title="Mission vs Monetization",
        pressure_ids=[pressure["pressure_id"], "rcp_missing"],
        fragment_ids=["rcf_missing"],
        theme_ids=["rct_missing"],
        contrast_pair=["mission", "monetization"],
        supporting_fragment_count=1,
        source_types=["note"],
        score=3,
    )
    _write_jsonl(corpus_root / "data" / "state" / ESSAY_CANDIDATES_FILE, [candidate])

    report = reconcile_reflective_corpus_state(repo_root=corpus_root)
    issue_types = {failure["issue_type"] for failure in report["failures"]}

    assert report["clean"] is False
    assert "missing_fragment_reference" in issue_types
    assert "missing_theme_reference" in issue_types
    assert "missing_pressure_reference" in issue_types


def test_external_action_allowed_true_fails(corpus_root: Path) -> None:
    fragment = build_fragment_record(
        source_type="note",
        source_ref="journal:001",
        text="This stays local.",
    )
    fragment["external_action_allowed"] = True
    _write_jsonl(corpus_root / "data" / "state" / FRAGMENTS_FILE, [fragment])

    report = reconcile_reflective_corpus_state(repo_root=corpus_root)

    assert report["clean"] is False
    assert any(failure["issue_type"] == "external_action_boundary_violation" for failure in report["failures"])


def test_malformed_jsonl_and_empty_candidate_support_fail(corpus_root: Path) -> None:
    state_root = corpus_root / "data" / "state"
    pressure = build_pressure_record(
        fragment_ids=["rcf_missing"],
        contrast_pair=["mission", "monetization"],
    )
    candidate = dict(
        build_essay_candidate_record(
            title="Mission vs Monetization",
            pressure_ids=[pressure["pressure_id"]],
            fragment_ids=["rcf_missing"],
            contrast_pair=["mission", "monetization"],
            supporting_fragment_count=1,
            source_types=["note"],
            score=3,
        )
    )
    candidate["fragment_ids"] = []
    candidate["supporting_fragment_count"] = 0

    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / PRESSURES_FILE).write_text("{not-json}\n", encoding="utf-8")
    _write_jsonl(state_root / ESSAY_CANDIDATES_FILE, [candidate])

    report = reconcile_reflective_corpus_state(repo_root=corpus_root)
    issue_types = {failure["issue_type"] for failure in report["failures"]}

    assert report["clean"] is False
    assert "malformed_jsonl_record" in issue_types
    assert "essay_candidate_without_supporting_fragments" in issue_types


def test_invalid_status_duplicate_ids_and_empty_text_fail(corpus_root: Path) -> None:
    fragment = build_fragment_record(
        source_type="note",
        source_ref="journal:001",
        text="This text will be emptied.",
    )
    duplicate = dict(fragment)
    fragment["text"] = ""
    theme = build_theme_record(name="Mission")
    theme["status"] = "retired"

    _write_jsonl(corpus_root / "data" / "state" / FRAGMENTS_FILE, [fragment, duplicate])
    _write_jsonl(corpus_root / "data" / "state" / "reflective_themes.jsonl", [theme])

    report = reconcile_reflective_corpus_state(repo_root=corpus_root)
    issue_types = {failure["issue_type"] for failure in report["failures"]}

    assert report["clean"] is False
    assert "empty_fragment_text" in issue_types
    assert "duplicate_id" in issue_types
    assert "invalid_status" in issue_types


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
