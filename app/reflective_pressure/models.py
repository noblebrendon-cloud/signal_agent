from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.reflective_pressure.taxonomy import (
    OUTPUT_TYPES,
    PRESSURE_TYPES,
    SOURCE_PLATFORMS,
    SOURCE_TYPES,
    SPINES,
    STANCE_TYPES,
    TONE_TYPES,
    validate_taxonomy_value,
)
from app.retention.identity import normalize_token, sha256_hex, utc_now_iso
from app.retention.jsonl_store import stable_json_dumps


SCHEMA_VERSION = "1.0"

INPUT_RECORD_TYPE = "reflective_pressure_input"
CLASSIFICATION_RECORD_TYPE = "reflective_pressure_classification"
DRAFT_RECORD_TYPE = "reflective_pressure_draft"
OBSERVATION_RECORD_TYPE = "reflective_pressure_observation"
EVENT_RECORD_TYPE = "reflective_pressure_event"
CORRECTION_RECORD_TYPE = "reflective_pressure_correction"
GOLDEN_EXAMPLE_RECORD_TYPE = "reflective_pressure_golden_example"

TARGET_RECORD_TYPES = (
    "input",
    "classification",
    "draft",
    "observation",
)

SCORE_FIELDS = (
    "moral_temperature",
    "ambiguity_level",
    "audience_self_insertion_potential",
    "risk_of_tribal_escalation",
    "recognition_potential",
)

OBSERVATION_NUMERIC_FIELDS = (
    "views",
    "reactions",
    "comments",
    "shares",
    "saves",
    "profile_clicks",
    "recognition_events",
    "constructive_reply_ratio",
    "self_insertion_density",
    "delayed_recirculation",
    "contradiction_heat",
)


def input_id_from_material(
    *,
    created_at: str,
    source_platform: str,
    source_context: str,
    source_type: str,
    raw_text: str,
    media_refs: Sequence[str],
    author_label: str,
    group_or_channel: str,
    intended_spine: str,
    tags: Sequence[str],
) -> str:
    payload = {
        "author_label": _optional_text(author_label),
        "created_at": _required_datetime("created_at", created_at),
        "group_or_channel": _optional_text(group_or_channel),
        "intended_spine": validate_taxonomy_value("intended_spine", intended_spine, SPINES),
        "media_refs": _normalize_text_list("media_refs", media_refs),
        "raw_text": _optional_text(raw_text),
        "source_context": _optional_text(source_context),
        "source_platform": validate_taxonomy_value("source_platform", source_platform, SOURCE_PLATFORMS),
        "source_type": validate_taxonomy_value("source_type", source_type, SOURCE_TYPES),
        "tags": _normalize_tags(tags),
    }
    return f"rpi_{sha256_hex(stable_json_dumps(payload))[:16]}"


def classification_id_from_material(
    *,
    input_id: str,
    created_at: str,
    pressure_type: str,
    surface_claim: str,
    hidden_pressure: str,
    recommended_output_type: str,
    rationale: str,
) -> str:
    payload = {
        "created_at": _required_datetime("created_at", created_at),
        "hidden_pressure": _required_text("hidden_pressure", hidden_pressure),
        "input_id": _required_text("input_id", input_id),
        "pressure_type": validate_taxonomy_value("pressure_type", pressure_type, PRESSURE_TYPES),
        "rationale": _required_text("rationale", rationale),
        "recommended_output_type": validate_taxonomy_value(
            "recommended_output_type",
            recommended_output_type,
            OUTPUT_TYPES,
        ),
        "surface_claim": _required_text("surface_claim", surface_claim),
    }
    return f"rpc_{sha256_hex(stable_json_dumps(payload))[:16]}"


def draft_id_from_material(
    *,
    input_id: str,
    classification_id: str,
    created_at: str,
    output_type: str,
    target_platform: str,
    draft_text: str,
) -> str:
    payload = {
        "classification_id": _required_text("classification_id", classification_id),
        "created_at": _required_datetime("created_at", created_at),
        "draft_text": _required_text("draft_text", draft_text),
        "input_id": _required_text("input_id", input_id),
        "output_type": validate_taxonomy_value("output_type", output_type, OUTPUT_TYPES),
        "target_platform": validate_taxonomy_value("target_platform", target_platform, SOURCE_PLATFORMS),
    }
    return f"rpd_{sha256_hex(stable_json_dumps(payload))[:16]}"


def observation_id_from_material(
    *,
    draft_id: str,
    input_id: str,
    created_at: str,
    observation_window: str,
    metrics: Mapping[str, int | float],
) -> str:
    payload = {
        "created_at": _required_datetime("created_at", created_at),
        "draft_id": _required_text("draft_id", draft_id),
        "input_id": _required_text("input_id", input_id),
        "metrics": _normalize_metrics(metrics),
        "observation_window": _required_text("observation_window", observation_window),
    }
    return f"rpo_{sha256_hex(stable_json_dumps(payload))[:16]}"


def event_id_from_material(
    *,
    event_type: str,
    linked_record_type: str,
    linked_record_id: str,
    created_at: str,
) -> str:
    payload = {
        "created_at": _required_datetime("created_at", created_at),
        "event_type": _required_text("event_type", event_type),
        "linked_record_id": _required_text("linked_record_id", linked_record_id),
        "linked_record_type": _required_text("linked_record_type", linked_record_type),
    }
    return f"rpe_{sha256_hex(stable_json_dumps(payload))[:16]}"


def correction_id_from_material(
    *,
    created_at: str,
    target_record_type: str,
    target_record_id: str,
    input_id: str,
    corrected_pressure_type: str,
    corrected_surface_claim: str,
    corrected_hidden_pressure: str,
    corrected_recommended_output_type: str,
    correction_reason: str,
    corrected_by: str,
) -> str:
    payload = {
        "corrected_by": _required_text("corrected_by", corrected_by),
        "corrected_hidden_pressure": _required_text("corrected_hidden_pressure", corrected_hidden_pressure),
        "corrected_pressure_type": validate_taxonomy_value(
            "corrected_pressure_type",
            corrected_pressure_type,
            PRESSURE_TYPES,
        ),
        "corrected_recommended_output_type": validate_taxonomy_value(
            "corrected_recommended_output_type",
            corrected_recommended_output_type,
            OUTPUT_TYPES,
        ),
        "corrected_surface_claim": _required_text("corrected_surface_claim", corrected_surface_claim),
        "correction_reason": _required_text("correction_reason", correction_reason),
        "created_at": _required_datetime("created_at", created_at),
        "input_id": _required_text("input_id", input_id),
        "target_record_id": _required_text("target_record_id", target_record_id),
        "target_record_type": _normalize_target_record_type(target_record_type),
    }
    return f"rpx_{sha256_hex(stable_json_dumps(payload))[:16]}"


def golden_id_from_material(
    *,
    created_at: str,
    input_id: str,
    classification_id: str,
    correction_id: str | None,
    draft_id: str | None,
    pressure_type: str,
    title: str,
    reusable_pattern: str,
) -> str:
    payload = {
        "classification_id": _required_text("classification_id", classification_id),
        "correction_id": _optional_record_id(correction_id),
        "created_at": _required_datetime("created_at", created_at),
        "draft_id": _optional_record_id(draft_id),
        "input_id": _required_text("input_id", input_id),
        "pressure_type": validate_taxonomy_value("pressure_type", pressure_type, PRESSURE_TYPES),
        "reusable_pattern": _required_text("reusable_pattern", reusable_pattern),
        "title": _required_text("title", title),
    }
    return f"rpg_{sha256_hex(stable_json_dumps(payload))[:16]}"


def build_input_record(
    *,
    source_platform: str,
    source_type: str,
    raw_text: str = "",
    media_refs: Sequence[str] | None = None,
    source_context: str = "",
    author_label: str = "",
    group_or_channel: str = "",
    intended_spine: str = "unknown",
    tags: Sequence[str] | None = None,
    notes: str = "",
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    source_platform_value = validate_taxonomy_value("source_platform", source_platform, SOURCE_PLATFORMS)
    source_type_value = validate_taxonomy_value("source_type", source_type, SOURCE_TYPES)
    intended_spine_value = validate_taxonomy_value("intended_spine", intended_spine, SPINES)
    raw_text_value = _optional_text(raw_text)
    media_ref_values = _normalize_text_list("media_refs", media_refs or [])
    if not raw_text_value and not media_ref_values:
        raise ValueError("missing_raw_text_or_media_refs")

    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    tag_values = _normalize_tags(tags or [])

    record = {
        "record_type": INPUT_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "input_id": input_id_from_material(
            created_at=created_at_value,
            source_platform=source_platform_value,
            source_context=source_context,
            source_type=source_type_value,
            raw_text=raw_text_value,
            media_refs=media_ref_values,
            author_label=author_label,
            group_or_channel=group_or_channel,
            intended_spine=intended_spine_value,
            tags=tag_values,
        ),
        "created_at": created_at_value,
        "source_platform": source_platform_value,
        "source_context": _optional_text(source_context),
        "source_type": source_type_value,
        "raw_text": raw_text_value,
        "media_refs": media_ref_values,
        "author_label": _optional_text(author_label),
        "group_or_channel": _optional_text(group_or_channel),
        "intended_spine": intended_spine_value,
        "tags": tag_values,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
        "notes": _optional_text(notes),
    }
    validate_input_record(record)
    return record


def build_classification_record(
    *,
    input_id: str,
    surface_claim: str,
    hidden_pressure: str,
    pressure_type: str,
    moral_temperature: int,
    ambiguity_level: int,
    audience_self_insertion_potential: int,
    risk_of_tribal_escalation: int,
    recognition_potential: int,
    recommended_output_type: str,
    rationale: str,
    confidence: int | float,
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    pressure_type_value = validate_taxonomy_value("pressure_type", pressure_type, PRESSURE_TYPES)
    recommended_value = validate_taxonomy_value("recommended_output_type", recommended_output_type, OUTPUT_TYPES)
    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    record = {
        "record_type": CLASSIFICATION_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "classification_id": classification_id_from_material(
            input_id=input_id,
            created_at=created_at_value,
            pressure_type=pressure_type_value,
            surface_claim=surface_claim,
            hidden_pressure=hidden_pressure,
            recommended_output_type=recommended_value,
            rationale=rationale,
        ),
        "input_id": _required_text("input_id", input_id),
        "created_at": created_at_value,
        "surface_claim": _required_text("surface_claim", surface_claim),
        "hidden_pressure": _required_text("hidden_pressure", hidden_pressure),
        "pressure_type": pressure_type_value,
        "moral_temperature": _score("moral_temperature", moral_temperature),
        "ambiguity_level": _score("ambiguity_level", ambiguity_level),
        "audience_self_insertion_potential": _score(
            "audience_self_insertion_potential",
            audience_self_insertion_potential,
        ),
        "risk_of_tribal_escalation": _score("risk_of_tribal_escalation", risk_of_tribal_escalation),
        "recognition_potential": _score("recognition_potential", recognition_potential),
        "recommended_output_type": recommended_value,
        "rationale": _required_text("rationale", rationale),
        "confidence": _confidence(confidence),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    validate_classification_record(record)
    return record


def build_draft_record(
    *,
    input_id: str,
    classification_id: str,
    output_type: str,
    target_platform: str | None,
    target_spine: str,
    draft_text: str,
    stance: str,
    tone: str,
    preserves_tension: bool,
    human_approved: bool = False,
    published: bool = False,
    published_location: str = "",
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    output_type_value = validate_taxonomy_value("output_type", output_type, OUTPUT_TYPES)
    target_platform_value = validate_taxonomy_value("target_platform", target_platform or "unknown", SOURCE_PLATFORMS)
    target_spine_value = validate_taxonomy_value("target_spine", target_spine, SPINES)
    stance_value = validate_taxonomy_value("stance", stance, STANCE_TYPES)
    tone_value = validate_taxonomy_value("tone", tone, TONE_TYPES)
    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    if not isinstance(preserves_tension, bool):
        raise ValueError("invalid_preserves_tension")
    if not isinstance(human_approved, bool):
        raise ValueError("invalid_human_approved")
    if not isinstance(published, bool):
        raise ValueError("invalid_published")

    record = {
        "record_type": DRAFT_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "draft_id": draft_id_from_material(
            input_id=input_id,
            classification_id=classification_id,
            created_at=created_at_value,
            output_type=output_type_value,
            target_platform=target_platform_value,
            draft_text=draft_text,
        ),
        "input_id": _required_text("input_id", input_id),
        "classification_id": _required_text("classification_id", classification_id),
        "created_at": created_at_value,
        "output_type": output_type_value,
        "target_platform": target_platform_value,
        "target_spine": target_spine_value,
        "draft_text": _required_text("draft_text", draft_text),
        "stance": stance_value,
        "tone": tone_value,
        "preserves_tension": preserves_tension,
        "human_approved": human_approved,
        "published": published,
        "published_location": _optional_text(published_location),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    validate_draft_record(record)
    return record


def build_observation_record(
    *,
    draft_id: str,
    input_id: str,
    observation_window: str = "manual",
    views: int | float = 0,
    reactions: int | float = 0,
    comments: int | float = 0,
    shares: int | float = 0,
    saves: int | float = 0,
    profile_clicks: int | float = 0,
    recognition_events: int | float = 0,
    constructive_reply_ratio: int | float = 0,
    self_insertion_density: int | float = 0,
    delayed_recirculation: int | float = 0,
    contradiction_heat: int | float = 0,
    notes: str = "",
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    metrics = {
        "views": views,
        "reactions": reactions,
        "comments": comments,
        "shares": shares,
        "saves": saves,
        "profile_clicks": profile_clicks,
        "recognition_events": recognition_events,
        "constructive_reply_ratio": constructive_reply_ratio,
        "self_insertion_density": self_insertion_density,
        "delayed_recirculation": delayed_recirculation,
        "contradiction_heat": contradiction_heat,
    }
    normalized_metrics = _normalize_metrics(metrics)
    record = {
        "record_type": OBSERVATION_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "observation_id": observation_id_from_material(
            draft_id=draft_id,
            input_id=input_id,
            created_at=created_at_value,
            observation_window=observation_window,
            metrics=normalized_metrics,
        ),
        "draft_id": _required_text("draft_id", draft_id),
        "input_id": _required_text("input_id", input_id),
        "created_at": created_at_value,
        "observation_window": _required_text("observation_window", observation_window),
        **normalized_metrics,
        "notes": _optional_text(notes),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    validate_observation_record(record)
    return record


def build_event_record(
    *,
    event_type: str,
    linked_record_type: str,
    linked_record_id: str,
    created_at: str | None = None,
    input_id: str | None = None,
    classification_id: str | None = None,
    draft_id: str | None = None,
    observation_id: str | None = None,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    record = {
        "record_type": EVENT_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id_from_material(
            event_type=event_type,
            linked_record_type=linked_record_type,
            linked_record_id=linked_record_id,
            created_at=created_at_value,
        ),
        "event_type": _required_text("event_type", event_type),
        "linked_record_type": _required_text("linked_record_type", linked_record_type),
        "linked_record_id": _required_text("linked_record_id", linked_record_id),
        "created_at": created_at_value,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    if input_id:
        record["input_id"] = _required_text("input_id", input_id)
    if classification_id:
        record["classification_id"] = _required_text("classification_id", classification_id)
    if draft_id:
        record["draft_id"] = _required_text("draft_id", draft_id)
    if observation_id:
        record["observation_id"] = _required_text("observation_id", observation_id)
    validate_event_record(record)
    return record


def build_correction_record(
    *,
    target_record_type: str,
    target_record_id: str,
    input_id: str,
    corrected_pressure_type: str,
    corrected_surface_claim: str,
    corrected_hidden_pressure: str,
    corrected_moral_temperature: int,
    corrected_ambiguity_level: int,
    corrected_audience_self_insertion_potential: int,
    corrected_risk_of_tribal_escalation: int,
    corrected_recognition_potential: int,
    corrected_recommended_output_type: str,
    correction_reason: str,
    corrected_by: str = "human_operator",
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    target_record_type_value = _normalize_target_record_type(target_record_type)
    corrected_pressure_type_value = validate_taxonomy_value(
        "corrected_pressure_type",
        corrected_pressure_type,
        PRESSURE_TYPES,
    )
    corrected_output_type_value = validate_taxonomy_value(
        "corrected_recommended_output_type",
        corrected_recommended_output_type,
        OUTPUT_TYPES,
    )
    corrected_by_value = _required_text("corrected_by", corrected_by or "human_operator")
    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    record = {
        "record_type": CORRECTION_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "correction_id": correction_id_from_material(
            created_at=created_at_value,
            target_record_type=target_record_type_value,
            target_record_id=target_record_id,
            input_id=input_id,
            corrected_pressure_type=corrected_pressure_type_value,
            corrected_surface_claim=corrected_surface_claim,
            corrected_hidden_pressure=corrected_hidden_pressure,
            corrected_recommended_output_type=corrected_output_type_value,
            correction_reason=correction_reason,
            corrected_by=corrected_by_value,
        ),
        "created_at": created_at_value,
        "target_record_type": target_record_type_value,
        "target_record_id": _required_text("target_record_id", target_record_id),
        "input_id": _required_text("input_id", input_id),
        "corrected_pressure_type": corrected_pressure_type_value,
        "corrected_surface_claim": _required_text("corrected_surface_claim", corrected_surface_claim),
        "corrected_hidden_pressure": _required_text("corrected_hidden_pressure", corrected_hidden_pressure),
        "corrected_moral_temperature": _score("corrected_moral_temperature", corrected_moral_temperature),
        "corrected_ambiguity_level": _score("corrected_ambiguity_level", corrected_ambiguity_level),
        "corrected_audience_self_insertion_potential": _score(
            "corrected_audience_self_insertion_potential",
            corrected_audience_self_insertion_potential,
        ),
        "corrected_risk_of_tribal_escalation": _score(
            "corrected_risk_of_tribal_escalation",
            corrected_risk_of_tribal_escalation,
        ),
        "corrected_recognition_potential": _score(
            "corrected_recognition_potential",
            corrected_recognition_potential,
        ),
        "corrected_recommended_output_type": corrected_output_type_value,
        "correction_reason": _required_text("correction_reason", correction_reason),
        "corrected_by": corrected_by_value,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    validate_correction_record(record)
    return record


def build_golden_example_record(
    *,
    input_id: str,
    classification_id: str,
    pressure_type: str,
    title: str,
    why_it_matters: str,
    reusable_pattern: str,
    correction_id: str | None = None,
    draft_id: str | None = None,
    voice_notes: str = "",
    risk_notes: str = "",
    approved_for_prompt_export: bool = False,
    created_at: str | None = None,
    external_action_allowed: bool = False,
    irreversible_action_allowed: bool = False,
) -> dict[str, Any]:
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    pressure_type_value = validate_taxonomy_value("pressure_type", pressure_type, PRESSURE_TYPES)
    if not isinstance(approved_for_prompt_export, bool):
        raise ValueError("invalid_approved_for_prompt_export")
    _require_false("external_action_allowed", external_action_allowed)
    _require_false("irreversible_action_allowed", irreversible_action_allowed)
    correction_id_value = _optional_record_id(correction_id)
    draft_id_value = _optional_record_id(draft_id)
    record = {
        "record_type": GOLDEN_EXAMPLE_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "golden_id": golden_id_from_material(
            created_at=created_at_value,
            input_id=input_id,
            classification_id=classification_id,
            correction_id=correction_id_value,
            draft_id=draft_id_value,
            pressure_type=pressure_type_value,
            title=title,
            reusable_pattern=reusable_pattern,
        ),
        "created_at": created_at_value,
        "input_id": _required_text("input_id", input_id),
        "classification_id": _required_text("classification_id", classification_id),
        "correction_id": correction_id_value,
        "draft_id": draft_id_value,
        "pressure_type": pressure_type_value,
        "title": _required_text("title", title),
        "why_it_matters": _required_text("why_it_matters", why_it_matters),
        "reusable_pattern": _required_text("reusable_pattern", reusable_pattern),
        "voice_notes": _optional_text(voice_notes),
        "risk_notes": _optional_text(risk_notes),
        "approved_for_prompt_export": approved_for_prompt_export,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    validate_golden_example_record(record)
    return record


def validate_input_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, INPUT_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "input_id",
            "created_at",
            "source_platform",
            "source_context",
            "source_type",
            "raw_text",
            "media_refs",
            "author_label",
            "group_or_channel",
            "intended_spine",
            "tags",
            "external_action_allowed",
            "irreversible_action_allowed",
            "notes",
        ),
    )
    _required_text("input_id", record["input_id"])
    _required_datetime("created_at", str(record["created_at"]))
    validate_taxonomy_value("source_platform", str(record["source_platform"]), SOURCE_PLATFORMS)
    validate_taxonomy_value("source_type", str(record["source_type"]), SOURCE_TYPES)
    validate_taxonomy_value("intended_spine", str(record["intended_spine"]), SPINES)
    raw_text = _optional_text(record["raw_text"])
    media_refs = _normalize_text_list("media_refs", record["media_refs"])
    if not raw_text and not media_refs:
        raise ValueError("missing_raw_text_or_media_refs")
    _normalize_tags(record["tags"])
    _validate_safety_flags(record)


def validate_classification_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, CLASSIFICATION_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "classification_id",
            "input_id",
            "created_at",
            "surface_claim",
            "hidden_pressure",
            "pressure_type",
            "moral_temperature",
            "ambiguity_level",
            "audience_self_insertion_potential",
            "risk_of_tribal_escalation",
            "recognition_potential",
            "recommended_output_type",
            "rationale",
            "confidence",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("classification_id", record["classification_id"])
    _required_text("input_id", record["input_id"])
    _required_datetime("created_at", str(record["created_at"]))
    _required_text("surface_claim", record["surface_claim"])
    _required_text("hidden_pressure", record["hidden_pressure"])
    validate_taxonomy_value("pressure_type", str(record["pressure_type"]), PRESSURE_TYPES)
    for field in SCORE_FIELDS:
        _score(field, record[field])
    validate_taxonomy_value("recommended_output_type", str(record["recommended_output_type"]), OUTPUT_TYPES)
    _required_text("rationale", record["rationale"])
    _confidence(record["confidence"])
    _validate_safety_flags(record)


def validate_draft_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, DRAFT_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "draft_id",
            "input_id",
            "classification_id",
            "created_at",
            "output_type",
            "target_platform",
            "target_spine",
            "draft_text",
            "stance",
            "tone",
            "preserves_tension",
            "human_approved",
            "published",
            "published_location",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("draft_id", record["draft_id"])
    _required_text("input_id", record["input_id"])
    _required_text("classification_id", record["classification_id"])
    _required_datetime("created_at", str(record["created_at"]))
    validate_taxonomy_value("output_type", str(record["output_type"]), OUTPUT_TYPES)
    validate_taxonomy_value("target_platform", str(record["target_platform"]), SOURCE_PLATFORMS)
    validate_taxonomy_value("target_spine", str(record["target_spine"]), SPINES)
    validate_taxonomy_value("stance", str(record["stance"]), STANCE_TYPES)
    validate_taxonomy_value("tone", str(record["tone"]), TONE_TYPES)
    _required_text("draft_text", record["draft_text"])
    if not isinstance(record["preserves_tension"], bool):
        raise ValueError("invalid_preserves_tension")
    if not isinstance(record["human_approved"], bool):
        raise ValueError("invalid_human_approved")
    if not isinstance(record["published"], bool):
        raise ValueError("invalid_published")
    _validate_safety_flags(record)


def validate_observation_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, OBSERVATION_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "observation_id",
            "draft_id",
            "input_id",
            "created_at",
            "observation_window",
            "views",
            "reactions",
            "comments",
            "shares",
            "saves",
            "profile_clicks",
            "recognition_events",
            "constructive_reply_ratio",
            "self_insertion_density",
            "delayed_recirculation",
            "contradiction_heat",
            "notes",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("observation_id", record["observation_id"])
    _required_text("draft_id", record["draft_id"])
    _required_text("input_id", record["input_id"])
    _required_datetime("created_at", str(record["created_at"]))
    _required_text("observation_window", record["observation_window"])
    _normalize_metrics({field: record[field] for field in OBSERVATION_NUMERIC_FIELDS})
    _validate_safety_flags(record)


def validate_event_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, EVENT_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "event_id",
            "event_type",
            "linked_record_type",
            "linked_record_id",
            "created_at",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("event_id", record["event_id"])
    _required_text("event_type", record["event_type"])
    _required_text("linked_record_type", record["linked_record_type"])
    _required_text("linked_record_id", record["linked_record_id"])
    _required_datetime("created_at", str(record["created_at"]))
    _validate_safety_flags(record)


def validate_correction_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, CORRECTION_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "correction_id",
            "created_at",
            "target_record_type",
            "target_record_id",
            "input_id",
            "corrected_pressure_type",
            "corrected_surface_claim",
            "corrected_hidden_pressure",
            "corrected_moral_temperature",
            "corrected_ambiguity_level",
            "corrected_audience_self_insertion_potential",
            "corrected_risk_of_tribal_escalation",
            "corrected_recognition_potential",
            "corrected_recommended_output_type",
            "correction_reason",
            "corrected_by",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("correction_id", record["correction_id"])
    _required_datetime("created_at", str(record["created_at"]))
    _normalize_target_record_type(str(record["target_record_type"]))
    _required_text("target_record_id", record["target_record_id"])
    _required_text("input_id", record["input_id"])
    validate_taxonomy_value("corrected_pressure_type", str(record["corrected_pressure_type"]), PRESSURE_TYPES)
    _required_text("corrected_surface_claim", record["corrected_surface_claim"])
    _required_text("corrected_hidden_pressure", record["corrected_hidden_pressure"])
    _score("corrected_moral_temperature", record["corrected_moral_temperature"])
    _score("corrected_ambiguity_level", record["corrected_ambiguity_level"])
    _score(
        "corrected_audience_self_insertion_potential",
        record["corrected_audience_self_insertion_potential"],
    )
    _score("corrected_risk_of_tribal_escalation", record["corrected_risk_of_tribal_escalation"])
    _score("corrected_recognition_potential", record["corrected_recognition_potential"])
    validate_taxonomy_value(
        "corrected_recommended_output_type",
        str(record["corrected_recommended_output_type"]),
        OUTPUT_TYPES,
    )
    _required_text("correction_reason", record["correction_reason"])
    _required_text("corrected_by", record["corrected_by"])
    _validate_safety_flags(record)


def validate_golden_example_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, GOLDEN_EXAMPLE_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "golden_id",
            "created_at",
            "input_id",
            "classification_id",
            "correction_id",
            "draft_id",
            "pressure_type",
            "title",
            "why_it_matters",
            "reusable_pattern",
            "voice_notes",
            "risk_notes",
            "approved_for_prompt_export",
            "external_action_allowed",
            "irreversible_action_allowed",
        ),
    )
    _required_text("golden_id", record["golden_id"])
    _required_datetime("created_at", str(record["created_at"]))
    _required_text("input_id", record["input_id"])
    _required_text("classification_id", record["classification_id"])
    _optional_record_id(record["correction_id"])
    _optional_record_id(record["draft_id"])
    validate_taxonomy_value("pressure_type", str(record["pressure_type"]), PRESSURE_TYPES)
    _required_text("title", record["title"])
    _required_text("why_it_matters", record["why_it_matters"])
    _required_text("reusable_pattern", record["reusable_pattern"])
    _optional_text(record["voice_notes"])
    _optional_text(record["risk_notes"])
    if not isinstance(record["approved_for_prompt_export"], bool):
        raise ValueError("invalid_approved_for_prompt_export")
    _validate_safety_flags(record)


def _require_record_type(record: Mapping[str, Any], expected: str) -> None:
    if record.get("record_type") != expected:
        raise ValueError(f"invalid_record_type:{record.get('record_type')}")


def _require_schema(record: Mapping[str, Any]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid_schema_version:{record.get('schema_version')}")


def _require_keys(record: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")


def _required_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"missing_{field}")
    return normalized


def _optional_record_id(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_record_id")
    normalized = value.strip()
    return normalized or None


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    return value.strip()


def _normalize_target_record_type(value: str) -> str:
    normalized = normalize_token(_required_text("target_record_type", value))
    if normalized not in TARGET_RECORD_TYPES:
        raise ValueError(f"unsupported_target_record_type:{value}")
    return normalized


def _normalize_text_list(field: str, values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"invalid_{field}")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"invalid_{field}")
        text = value.strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_tags(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("invalid_tags")
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("invalid_tag")
        if value.strip():
            normalized.add(normalize_token(_required_text("tag", value)))
    return sorted(normalized)


def _required_datetime(field: str, value: str) -> str:
    normalized = _required_text(field, value)
    candidate = normalized
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        if len(candidate) == 10:
            parsed = datetime.fromisoformat(candidate).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"invalid_datetime:{field}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _score(field: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid_score:{field}")
    if value < 0 or value > 5:
        raise ValueError(f"score_out_of_range:{field}")
    return int(value)


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_confidence")
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise ValueError("confidence_out_of_range")
    return parsed


def _non_negative_number(field: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid_numeric_field:{field}")
    if value < 0:
        raise ValueError(f"negative_numeric_field:{field}")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _normalize_metrics(metrics: Mapping[str, int | float]) -> dict[str, int | float]:
    if not isinstance(metrics, Mapping):
        raise ValueError("invalid_metrics")
    normalized: dict[str, int | float] = {}
    for field in OBSERVATION_NUMERIC_FIELDS:
        if field not in metrics:
            raise ValueError(f"missing_metric:{field}")
        normalized[field] = _non_negative_number(field, metrics[field])
    return normalized


def _require_false(field: str, value: Any) -> None:
    if value is not False:
        raise ValueError(f"{field}_not_allowed")


def _validate_safety_flags(record: Mapping[str, Any]) -> None:
    if record.get("external_action_allowed") is not False:
        raise ValueError("external_action_allowed_not_allowed")
    if record.get("irreversible_action_allowed") is not False:
        raise ValueError("irreversible_action_allowed_not_allowed")
