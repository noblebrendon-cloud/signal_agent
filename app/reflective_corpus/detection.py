from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.reflective_corpus.models import (
    build_essay_candidate_record,
    build_pressure_record,
    normalize_for_matching,
    validate_fragment_record,
    validate_pressure_record,
    validate_theme_record,
)
from app.reflective_corpus.store import list_fragments, list_themes


CONFIDENCE_LEVELS = ("low", "medium", "high")
CONTRAST_PAIRS = (
    ("mission", "monetization"),
    ("continuity", "virality"),
    ("public morality", "private reality"),
    ("condemnation", "self-awareness"),
    ("authority", "encounter"),
    ("institution", "living witness"),
    ("truth", "performance"),
    ("extraction", "service"),
    ("fragmentation", "coherence"),
)


def detect_theme_matches(
    *,
    fragments: Sequence[Mapping[str, Any]] | None = None,
    themes: Sequence[Mapping[str, Any]] | None = None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    fragment_rows = list(fragments) if fragments is not None else list_fragments(repo_root=repo_root)
    theme_rows = list(themes) if themes is not None else list_themes(repo_root=repo_root)

    matches: list[dict[str, Any]] = []
    for fragment in fragment_rows:
        validate_fragment_record(fragment)
        fragment_text = normalize_for_matching(fragment["text"])
        for theme in theme_rows:
            validate_theme_record(theme)
            matched = _matched_terms(fragment_text, theme)
            if not matched:
                continue
            matches.append(
                {
                    "fragment_id": fragment["fragment_id"],
                    "theme_id": theme["theme_id"],
                    "matched_terms": matched,
                    "confidence": _confidence_for_terms(matched, theme),
                    "external_action_allowed": False,
                }
            )

    return sorted(
        matches,
        key=lambda match: (
            str(match["fragment_id"]),
            str(match["theme_id"]),
            tuple(match["matched_terms"]),
        ),
    )


def detect_pressures(
    *,
    fragments: Sequence[Mapping[str, Any]] | None = None,
    themes: Sequence[Mapping[str, Any]] | None = None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    fragment_rows = list(fragments) if fragments is not None else list_fragments(repo_root=repo_root)
    theme_rows = list(themes) if themes is not None else list_themes(repo_root=repo_root)
    theme_ids_by_fragment = _theme_ids_by_fragment(fragment_rows, theme_rows)

    pressures: list[dict[str, Any]] = []
    for left, right in CONTRAST_PAIRS:
        support: list[Mapping[str, Any]] = []
        matched_terms: set[str] = set()
        for fragment in fragment_rows:
            validate_fragment_record(fragment)
            text = normalize_for_matching(fragment["text"])
            fragment_terms = [term for term in (left, right) if _contains_term(text, term)]
            if not fragment_terms:
                continue
            support.append(fragment)
            matched_terms.update(fragment_terms)

        if {left, right} != matched_terms:
            continue

        fragment_ids = [str(fragment["fragment_id"]) for fragment in support]
        related_theme_ids = sorted(
            {
                theme_id
                for fragment in support
                for theme_id in theme_ids_by_fragment.get(str(fragment["fragment_id"]), [])
            }
        )
        pressures.append(
            build_pressure_record(
                fragment_ids=fragment_ids,
                contrast_pair=[left, right],
                matched_terms=sorted(matched_terms),
                related_theme_ids=related_theme_ids,
                emotional_weight=_emotional_weight_for_support(len(fragment_ids)),
                detected_at=_latest_fragment_time(support),
            )
        )

    return sorted(
        pressures,
        key=lambda pressure: (
            tuple(pressure["contrast_pair"]),
            str(pressure["pressure_id"]),
        ),
    )


def suggest_essay_candidates(
    *,
    pressures: Sequence[Mapping[str, Any]] | None = None,
    fragments: Sequence[Mapping[str, Any]] | None = None,
    themes: Sequence[Mapping[str, Any]] | None = None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    fragment_rows = list(fragments) if fragments is not None else list_fragments(repo_root=repo_root)
    pressure_rows = (
        list(pressures)
        if pressures is not None
        else detect_pressures(fragments=fragment_rows, themes=themes, repo_root=repo_root)
    )
    fragments_by_id = {str(fragment["fragment_id"]): fragment for fragment in fragment_rows}

    candidates: list[dict[str, Any]] = []
    for pressure in pressure_rows:
        validate_pressure_record(pressure)
        supporting_fragments = [
            fragments_by_id[fragment_id]
            for fragment_id in pressure["fragment_ids"]
            if fragment_id in fragments_by_id
        ]
        if not supporting_fragments:
            continue
        source_types = sorted({str(fragment["source_type"]) for fragment in supporting_fragments})
        score = score_essay_candidate(
            supporting_fragment_count=len(supporting_fragments),
            source_types=source_types,
            emotional_weight=str(pressure["emotional_weight"]),
            theme_ids=pressure["related_theme_ids"],
            contrast_pair=pressure["contrast_pair"],
        )
        candidates.append(
            build_essay_candidate_record(
                title=title_for_contrast_pair(pressure["contrast_pair"]),
                pressure_ids=[str(pressure["pressure_id"])],
                fragment_ids=[str(fragment["fragment_id"]) for fragment in supporting_fragments],
                theme_ids=pressure["related_theme_ids"],
                contrast_pair=pressure["contrast_pair"],
                supporting_fragment_count=len(supporting_fragments),
                source_types=source_types,
                score=score,
                status="seed",
                created_at=str(pressure["detected_at"]),
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            -int(candidate["score"]),
            str(candidate["title"]),
            str(candidate["candidate_id"]),
        ),
    )


def score_essay_candidate(
    *,
    supporting_fragment_count: int,
    source_types: Sequence[str],
    emotional_weight: str,
    theme_ids: Sequence[str],
    contrast_pair: Sequence[str],
) -> int:
    score = int(supporting_fragment_count) * 2
    if len(set(source_types)) > 1:
        score += 3
    if str(emotional_weight).strip().lower() == "high":
        score += 2
    if len(set(theme_ids)) > 1:
        score += 2
    if len([term for term in contrast_pair if str(term).strip()]) == 2:
        score += 1
    return min(score, 10)


def title_for_contrast_pair(contrast_pair: Sequence[str]) -> str:
    if len(contrast_pair) != 2:
        raise ValueError("contrast_pair_must_have_two_terms")
    return f"{_title_phrase(str(contrast_pair[0]))} vs {_title_phrase(str(contrast_pair[1]))}"


def _matched_terms(fragment_text: str, theme: Mapping[str, Any]) -> list[str]:
    terms = _theme_terms(theme)
    matched = {term for term in terms if _contains_term(fragment_text, term)}
    return sorted(matched)


def _theme_terms(theme: Mapping[str, Any]) -> list[str]:
    terms = [
        normalize_for_matching(theme["name"]),
        *[normalize_for_matching(alias) for alias in theme["aliases"]],
        *[normalize_for_matching(term) for term in theme["signal_terms"]],
    ]
    return sorted({term for term in terms if term})


def _contains_term(fragment_text: str, term: str) -> bool:
    if not term:
        return False
    pattern = r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])"
    return re.search(pattern, fragment_text) is not None


def _confidence_for_terms(matched_terms: Sequence[str], theme: Mapping[str, Any]) -> str:
    name = normalize_for_matching(theme["name"])
    aliases = {normalize_for_matching(alias) for alias in theme["aliases"]}
    matched = set(matched_terms)

    if name in matched or len(matched) >= 3:
        return "high"
    if matched.intersection(aliases) or len(matched) == 2:
        return "medium"
    return "low"


def _theme_ids_by_fragment(
    fragments: Sequence[Mapping[str, Any]],
    themes: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    matches = detect_theme_matches(fragments=fragments, themes=themes)
    grouped: dict[str, set[str]] = {}
    for match in matches:
        grouped.setdefault(str(match["fragment_id"]), set()).add(str(match["theme_id"]))
    return {fragment_id: sorted(theme_ids) for fragment_id, theme_ids in grouped.items()}


def _emotional_weight_for_support(count: int) -> str:
    if count >= 3:
        return "high"
    if count == 2:
        return "medium"
    return "low"


def _latest_fragment_time(fragments: Sequence[Mapping[str, Any]]) -> str:
    values = [str(fragment["captured_at"]) for fragment in fragments]
    if not values:
        raise ValueError("missing_pressure_support")
    return max(values)


def _title_phrase(value: str) -> str:
    return " ".join(part.capitalize() for part in normalize_for_matching(value).split())
