from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.reflective_corpus.detection import detect_pressures, detect_theme_matches, suggest_essay_candidates
from app.reflective_corpus.store import (
    list_essay_candidates,
    list_fragments,
    list_pressures,
    list_themes,
)
from app.retention.identity import get_repo_root
from app.utils.io_contract import atomic_write_text


REPORT_PATH = Path("data") / "outputs" / "reflective_corpus" / "corpus_report.md"


def generate_corpus_report(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or get_repo_root()
    output_path = root / REPORT_PATH
    markdown = render_corpus_report(repo_root=root)
    result = atomic_write_text(output_path, markdown if markdown.endswith("\n") else f"{markdown}\n")
    return {
        "path": str(result.final_path.resolve()),
        "bytes_written": result.bytes_written,
        "external_action_allowed": False,
    }


def render_corpus_report(*, repo_root: Path | None = None) -> str:
    fragments = list_fragments(repo_root=repo_root)
    themes = list_themes(repo_root=repo_root)
    active_themes = [theme for theme in themes if theme["status"] == "active"]
    stored_pressures = list_pressures(repo_root=repo_root)
    detected_pressures = detect_pressures(fragments=fragments, themes=themes, repo_root=repo_root)
    pressures = stored_pressures if stored_pressures else detected_pressures
    stored_candidates = list_essay_candidates(repo_root=repo_root)
    suggested_candidates = suggest_essay_candidates(pressures=pressures, fragments=fragments, themes=themes, repo_root=repo_root)
    candidates = stored_candidates if stored_candidates else suggested_candidates
    theme_matches = detect_theme_matches(fragments=fragments, themes=themes, repo_root=repo_root)

    lines = [
        "# Reflective Corpus Report",
        "",
        "## Total Fragments",
        f"- Total fragments: {len(fragments)}",
        "",
        "## Active Themes",
        f"- Active themes: {len(active_themes)}",
        *_theme_lines(active_themes),
        "",
        "## Detected Pressures",
        f"- Detected pressures: {len(pressures)}",
        *_pressure_lines(pressures),
        "",
        "## Essay Candidates by Score",
        *_candidate_score_lines(candidates),
        "",
        "## Top Recurring Themes",
        *_top_theme_lines(theme_matches, themes),
        "",
        "## Unresolved Tensions",
        *_tension_lines(pressures),
        "",
        "## Next 5 Essay Candidates",
        *_next_candidate_lines(candidates),
        "",
    ]
    return "\n".join(lines)


def _theme_lines(themes: list[dict[str, Any]]) -> list[str]:
    if not themes:
        return ["- None"]
    return [f"- {theme['name']} ({theme['theme_id']})" for theme in sorted(themes, key=lambda row: (row["name"], row["theme_id"]))]


def _pressure_lines(pressures: list[dict[str, Any]]) -> list[str]:
    if not pressures:
        return ["- None"]
    return [
        "- "
        + f"{_contrast_label(pressure['contrast_pair'])} "
        + f"({pressure['emotional_weight']}, fragments: {len(pressure['fragment_ids'])})"
        for pressure in sorted(pressures, key=lambda row: (_contrast_label(row["contrast_pair"]), row["pressure_id"]))
    ]


def _candidate_score_lines(candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return ["- None"]
    return [
        f"- {candidate['score']}: {candidate['title']} ({candidate['status']})"
        for candidate in _sort_candidates(candidates)
    ]


def _top_theme_lines(matches: list[dict[str, Any]], themes: list[dict[str, Any]]) -> list[str]:
    if not matches:
        return ["- None"]
    names_by_id = {theme["theme_id"]: theme["name"] for theme in themes}
    counts = Counter(str(match["theme_id"]) for match in matches)
    return [
        f"- {names_by_id.get(theme_id, theme_id)}: {count}"
        for theme_id, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], names_by_id.get(item[0], item[0]), item[0]),
        )
    ]


def _tension_lines(pressures: list[dict[str, Any]]) -> list[str]:
    if not pressures:
        return ["- None"]
    return [
        f"- {_contrast_label(pressure['contrast_pair'])}"
        for pressure in sorted(pressures, key=lambda row: (_contrast_label(row["contrast_pair"]), row["pressure_id"]))
    ]


def _next_candidate_lines(candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return ["- None"]
    return [
        f"- {candidate['title']} (score {candidate['score']}, {candidate['supporting_fragment_count']} fragments)"
        for candidate in _sort_candidates(candidates)[:5]
    ]


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -int(candidate["score"]),
            str(candidate["title"]),
            str(candidate["candidate_id"]),
        ),
    )


def _contrast_label(contrast_pair: list[str]) -> str:
    return " vs ".join(_title_phrase(term) for term in contrast_pair)


def _title_phrase(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value).split())
