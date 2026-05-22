from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.reflective_pressure.models import (
    build_draft_record,
    validate_classification_record,
    validate_input_record,
)
from app.reflective_pressure.taxonomy import SOURCE_PLATFORMS, validate_taxonomy_value


SUPPORTED_TEMPLATE_OUTPUTS = {
    "short_post",
    "reply",
    "pressure_log_entry",
    "letter_of_light_seed",
    "theological_reflection",
    "system_note",
}


def generate_draft(
    input_record: Mapping[str, Any],
    classification_record: Mapping[str, Any],
    output_type: str,
    target_platform: str | None = None,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_input_record(input_record)
    validate_classification_record(classification_record)
    if classification_record["input_id"] != input_record["input_id"]:
        raise ValueError("classification_input_mismatch")
    if output_type not in SUPPORTED_TEMPLATE_OUTPUTS:
        raise ValueError(f"unsupported_template_output_type:{output_type}")
    target_platform_value = validate_taxonomy_value(
        "target_platform",
        target_platform or str(input_record.get("source_platform") or "unknown"),
        SOURCE_PLATFORMS,
    )
    target_spine = _target_spine(input_record, classification_record)
    draft_text = _render_template(input_record, classification_record, output_type)
    stance, tone = _stance_and_tone(output_type, str(classification_record["pressure_type"]))

    return build_draft_record(
        input_id=str(input_record["input_id"]),
        classification_id=str(classification_record["classification_id"]),
        output_type=output_type,
        target_platform=target_platform_value,
        target_spine=target_spine,
        draft_text=draft_text,
        stance=stance,
        tone=tone,
        preserves_tension=True,
        human_approved=False,
        published=False,
        published_location="",
        created_at=created_at,
    )


def _render_template(
    input_record: Mapping[str, Any],
    classification_record: Mapping[str, Any],
    output_type: str,
) -> str:
    surface_claim = str(classification_record["surface_claim"])
    hidden_pressure = str(classification_record["hidden_pressure"])
    pressure_type = str(classification_record["pressure_type"])
    source_excerpt = _excerpt(str(input_record.get("raw_text") or ""))

    if output_type == "reply":
        return (
            f"There is a pressure here worth naming: {hidden_pressure} "
            f"The surface argument is {surface_claim}, but the deeper tension seems to be {pressure_type}. "
            "I do not think this needs to be solved with a slogan before it is honestly seen."
        )
    if output_type == "short_post":
        return (
            f"Some conversations are not only about the claim on the surface. {surface_claim} "
            f"Under it, I hear this pressure: {hidden_pressure} "
            "That is the part people often feel before they can explain it."
        )
    if output_type == "pressure_log_entry":
        return (
            f"Pressure log: {pressure_type}. Surface: {surface_claim} "
            f"Hidden pressure: {hidden_pressure} Source excerpt: {source_excerpt or 'no text excerpt recorded'}."
        )
    if output_type == "letter_of_light_seed":
        return (
            f"Seed: stay near the place where {hidden_pressure} "
            "Do not force the ache into a lesson. Let the recognition arrive before any resolution."
        )
    if output_type == "theological_reflection":
        return (
            f"A theological reflection could begin by naming this pressure without claiming final authority: "
            f"{hidden_pressure} The surface claim is {surface_claim}. "
            "The safer move is to preserve the human tension before turning it into doctrine."
        )
    if output_type == "system_note":
        return (
            f"System note: classify this as {pressure_type}. Preserve tension: yes. "
            f"Observed surface: {surface_claim} Hidden pressure: {hidden_pressure} "
            "No external action is authorized."
        )
    raise ValueError(f"unsupported_template_output_type:{output_type}")


def _target_spine(input_record: Mapping[str, Any], classification_record: Mapping[str, Any]) -> str:
    intended = str(input_record.get("intended_spine") or "unknown")
    if intended != "unknown":
        return intended
    if classification_record.get("recommended_output_type") == "theological_reflection":
        return "theological"
    if classification_record.get("pressure_type") == "humor_as_shield":
        return "humor"
    return "reflective"


def _stance_and_tone(output_type: str, pressure_type: str) -> tuple[str, str]:
    if output_type == "pressure_log_entry":
        return "logging", "sober"
    if output_type == "theological_reflection":
        return "reflective", "measured"
    if pressure_type == "peace_vs_escalation":
        return "de_escalating", "gentle"
    if pressure_type == "humor_as_shield":
        return "naming", "wry"
    return "naming", "measured"


def _excerpt(text: str, limit: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
