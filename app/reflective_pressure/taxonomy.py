from __future__ import annotations

from collections.abc import Iterable

from app.retention.identity import normalize_token


SOURCE_PLATFORMS = (
    "facebook",
    "facebook_group",
    "threads",
    "instagram",
    "tiktok",
    "linkedin",
    "x",
    "substack",
    "youtube",
    "reddit",
    "email",
    "personal_note",
    "screenshot",
    "unknown",
)

SOURCE_TYPES = (
    "post",
    "comment",
    "reply",
    "screenshot",
    "meme",
    "scripture_reference",
    "personal_reflection",
    "article_excerpt",
    "group_discussion",
    "performance_metric",
    "other",
)

SPINES = (
    "reflective",
    "theological",
    "humor",
    "governance",
    "systems_ai",
    "tenderness",
    "music_art",
    "community",
    "unknown",
)

PRESSURE_TYPES = (
    "recognition_deprivation",
    "role_fatigue",
    "aspiration_reality_gap",
    "moral_contradiction_exposure",
    "belonging_exclusion_tension",
    "public_private_split",
    "sacred_profane_conflict",
    "humor_as_shield",
    "tenderness_under_threat",
    "aftermath_memory",
    "ego_disguised_as_righteousness",
    "shallow_certainty",
    "spiritual_reductionism",
    "authority_confusion",
    "grievance_loop",
    "peace_vs_escalation",
    "unknown",
)

OUTPUT_TYPES = (
    "short_post",
    "long_post",
    "reply",
    "comment_response",
    "threads_post",
    "facebook_group_post",
    "letter_of_light_seed",
    "song_reflection_seed",
    "theological_reflection",
    "system_note",
    "pressure_log_entry",
)

TONE_TYPES = (
    "measured",
    "gentle",
    "tender",
    "plainspoken",
    "sober",
    "wry",
    "curious",
    "firm",
    "unknown",
)

STANCE_TYPES = (
    "naming",
    "questioning",
    "witnessing",
    "de_escalating",
    "logging",
    "reflective",
    "unknown",
)


def validate_taxonomy_value(field_name: str, value: str, allowed_values: Iterable[str]) -> str:
    normalized = normalize_token(value)
    allowed = tuple(allowed_values)
    if normalized not in allowed:
        raise ValueError(f"unsupported_{field_name}:{value}")
    return normalized
