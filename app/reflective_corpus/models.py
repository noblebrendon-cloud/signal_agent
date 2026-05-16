from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.retention.identity import normalize_token, sha256_hex, utc_now_iso
from app.retention.jsonl_store import stable_json_dumps


SCHEMA_VERSION = "1.0"

FRAGMENT_RECORD_TYPE = "reflective_corpus_fragment"
THEME_RECORD_TYPE = "reflective_corpus_theme"
PRESSURE_RECORD_TYPE = "reflective_corpus_pressure"
ESSAY_CANDIDATE_RECORD_TYPE = "reflective_corpus_essay_candidate"

SOURCE_TYPES = (
    "chat_reflection",
    "comment",
    "journal",
    "note",
    "other",
    "transcript",
)

THEME_STATUSES = ("active", "dormant", "merged")
EMOTIONAL_WEIGHTS = ("low", "medium", "high")
ESSAY_CANDIDATE_STATUSES = ("seed", "archived")


def fragment_id_from_material(
    *,
    source_type: str,
    source_ref: str,
    text: str,
    tags: Sequence[Any] | None = None,
) -> str:
    payload = {
        "source_ref": _normalize_identity_text(_required_text("source_ref", source_ref)),
        "source_type": _normalize_source_type(source_type),
        "tags": _normalize_phrase_list("tags", tags or []),
        "text": _normalize_identity_text(_required_text("text", text)),
    }
    return f"rcf_{sha256_hex(stable_json_dumps(payload))[:16]}"


def theme_id_from_name(name: str) -> str:
    return f"rct_{sha256_hex(_normalize_identity_text(_required_text('name', name)))[:16]}"


def pressure_id_from_material(
    *,
    fragment_ids: Sequence[Any],
    contrast_pair: Sequence[Any],
) -> str:
    payload = {
        "contrast_pair": _normalize_contrast_pair(contrast_pair),
        "fragment_ids": _normalize_id_list("fragment_ids", fragment_ids, require_non_empty=True),
    }
    return f"rcp_{sha256_hex(stable_json_dumps(payload))[:16]}"


def essay_candidate_id_from_material(
    *,
    title: str,
    pressure_ids: Sequence[Any],
    fragment_ids: Sequence[Any],
    theme_ids: Sequence[Any],
    contrast_pair: Sequence[Any],
) -> str:
    payload = {
        "contrast_pair": _normalize_contrast_pair(contrast_pair),
        "fragment_ids": _normalize_id_list("fragment_ids", fragment_ids, require_non_empty=True),
        "pressure_ids": _normalize_id_list("pressure_ids", pressure_ids, require_non_empty=True),
        "theme_ids": _normalize_id_list("theme_ids", theme_ids, require_non_empty=False),
        "title": _normalize_identity_text(_required_text("title", title)),
    }
    return f"rce_{sha256_hex(stable_json_dumps(payload))[:16]}"


def build_fragment_record(
    *,
    source_type: str,
    source_ref: str,
    text: str,
    tags: Sequence[Any] | None = None,
    captured_at: str | None = None,
    external_action_allowed: bool = False,
) -> dict[str, Any]:
    source_type_value = _normalize_source_type(source_type)
    source_ref_value = _required_text("source_ref", source_ref)
    text_value = _required_text("text", text)
    tag_values = _normalize_phrase_list("tags", tags or [])
    captured_at_value = _required_datetime("captured_at", captured_at or utc_now_iso())
    _require_false("external_action_allowed", external_action_allowed)

    record = {
        "record_type": FRAGMENT_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "fragment_id": fragment_id_from_material(
            source_type=source_type_value,
            source_ref=source_ref_value,
            text=text_value,
            tags=tag_values,
        ),
        "source_type": source_type_value,
        "source_ref": source_ref_value,
        "captured_at": captured_at_value,
        "text": text_value,
        "tags": tag_values,
        "external_action_allowed": False,
    }
    validate_fragment_record(record)
    return record


def build_theme_record(
    *,
    name: str,
    aliases: Sequence[Any] | None = None,
    description: str = "",
    signal_terms: Sequence[Any] | None = None,
    created_at: str | None = None,
    status: str = "active",
    external_action_allowed: bool = False,
) -> dict[str, Any]:
    name_value = _required_text("name", name)
    alias_values = _normalize_phrase_list("aliases", aliases or [])
    signal_term_values = _normalize_phrase_list("signal_terms", signal_terms or [])
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    status_value = _normalize_theme_status(status)
    _require_false("external_action_allowed", external_action_allowed)

    record = {
        "record_type": THEME_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "theme_id": theme_id_from_name(name_value),
        "name": name_value,
        "aliases": alias_values,
        "description": _optional_text(description),
        "signal_terms": signal_term_values,
        "created_at": created_at_value,
        "status": status_value,
        "external_action_allowed": False,
    }
    validate_theme_record(record)
    return record


def build_pressure_record(
    *,
    fragment_ids: Sequence[Any],
    contrast_pair: Sequence[Any],
    matched_terms: Sequence[Any] | None = None,
    related_theme_ids: Sequence[Any] | None = None,
    emotional_weight: str = "low",
    detected_at: str | None = None,
    external_action_allowed: bool = False,
) -> dict[str, Any]:
    fragment_id_values = _normalize_id_list("fragment_ids", fragment_ids, require_non_empty=True)
    contrast_pair_value = _normalize_contrast_pair(contrast_pair)
    matched_term_values = _normalize_phrase_list("matched_terms", matched_terms or contrast_pair_value)
    related_theme_id_values = _normalize_id_list("related_theme_ids", related_theme_ids or [], require_non_empty=False)
    detected_at_value = _required_datetime("detected_at", detected_at or utc_now_iso())
    emotional_weight_value = _normalize_emotional_weight(emotional_weight)
    _require_false("external_action_allowed", external_action_allowed)

    record = {
        "record_type": PRESSURE_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "pressure_id": pressure_id_from_material(
            fragment_ids=fragment_id_values,
            contrast_pair=contrast_pair_value,
        ),
        "fragment_ids": fragment_id_values,
        "contrast_pair": contrast_pair_value,
        "matched_terms": matched_term_values,
        "related_theme_ids": related_theme_id_values,
        "emotional_weight": emotional_weight_value,
        "detected_at": detected_at_value,
        "external_action_allowed": False,
    }
    validate_pressure_record(record)
    return record


def build_essay_candidate_record(
    *,
    title: str,
    pressure_ids: Sequence[Any],
    fragment_ids: Sequence[Any],
    theme_ids: Sequence[Any] | None = None,
    contrast_pair: Sequence[Any],
    supporting_fragment_count: int,
    source_types: Sequence[Any],
    score: int,
    status: str = "seed",
    created_at: str | None = None,
    external_action_allowed: bool = False,
) -> dict[str, Any]:
    title_value = _required_text("title", title)
    pressure_id_values = _normalize_id_list("pressure_ids", pressure_ids, require_non_empty=True)
    fragment_id_values = _normalize_id_list("fragment_ids", fragment_ids, require_non_empty=True)
    theme_id_values = _normalize_id_list("theme_ids", theme_ids or [], require_non_empty=False)
    contrast_pair_value = _normalize_contrast_pair(contrast_pair)
    source_type_values = _normalize_source_type_list(source_types)
    status_value = _normalize_candidate_status(status)
    created_at_value = _required_datetime("created_at", created_at or utc_now_iso())
    score_value = _score_value(score)
    supporting_count_value = _positive_int("supporting_fragment_count", supporting_fragment_count)
    _require_false("external_action_allowed", external_action_allowed)

    record = {
        "record_type": ESSAY_CANDIDATE_RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": essay_candidate_id_from_material(
            title=title_value,
            pressure_ids=pressure_id_values,
            fragment_ids=fragment_id_values,
            theme_ids=theme_id_values,
            contrast_pair=contrast_pair_value,
        ),
        "title": title_value,
        "pressure_ids": pressure_id_values,
        "fragment_ids": fragment_id_values,
        "theme_ids": theme_id_values,
        "contrast_pair": contrast_pair_value,
        "supporting_fragment_count": supporting_count_value,
        "source_types": source_type_values,
        "score": score_value,
        "status": status_value,
        "created_at": created_at_value,
        "external_action_allowed": False,
    }
    validate_essay_candidate_record(record)
    return record


def validate_fragment_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, FRAGMENT_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "fragment_id",
            "source_type",
            "source_ref",
            "captured_at",
            "text",
            "tags",
            "external_action_allowed",
        ),
    )
    source_type = _normalize_source_type(str(record["source_type"]))
    source_ref = _required_text("source_ref", record["source_ref"])
    text = _required_text("text", record["text"])
    tags = _normalize_phrase_list("tags", record["tags"])
    captured_at = _required_datetime("captured_at", str(record["captured_at"]))
    _validate_safety(record)

    if record["source_type"] != source_type:
        raise ValueError("source_type_not_normalized")
    if record["tags"] != tags:
        raise ValueError("tags_not_normalized")
    if record["captured_at"] != captured_at:
        raise ValueError("captured_at_not_normalized")
    expected_id = fragment_id_from_material(
        source_type=source_type,
        source_ref=source_ref,
        text=text,
        tags=tags,
    )
    if record["fragment_id"] != expected_id:
        raise ValueError("fragment_id_mismatch")


def validate_theme_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, THEME_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "theme_id",
            "name",
            "aliases",
            "description",
            "signal_terms",
            "created_at",
            "status",
            "external_action_allowed",
        ),
    )
    name = _required_text("name", record["name"])
    aliases = _normalize_phrase_list("aliases", record["aliases"])
    signal_terms = _normalize_phrase_list("signal_terms", record["signal_terms"])
    created_at = _required_datetime("created_at", str(record["created_at"]))
    status = _normalize_theme_status(str(record["status"]))
    _optional_text(record["description"])
    _validate_safety(record)

    if record["aliases"] != aliases:
        raise ValueError("aliases_not_normalized")
    if record["signal_terms"] != signal_terms:
        raise ValueError("signal_terms_not_normalized")
    if record["created_at"] != created_at:
        raise ValueError("created_at_not_normalized")
    if record["status"] != status:
        raise ValueError("status_not_normalized")
    if record["theme_id"] != theme_id_from_name(name):
        raise ValueError("theme_id_mismatch")


def validate_pressure_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, PRESSURE_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "pressure_id",
            "fragment_ids",
            "contrast_pair",
            "matched_terms",
            "related_theme_ids",
            "emotional_weight",
            "detected_at",
            "external_action_allowed",
        ),
    )
    fragment_ids = _normalize_id_list("fragment_ids", record["fragment_ids"], require_non_empty=True)
    contrast_pair = _normalize_contrast_pair(record["contrast_pair"])
    matched_terms = _normalize_phrase_list("matched_terms", record["matched_terms"])
    related_theme_ids = _normalize_id_list("related_theme_ids", record["related_theme_ids"], require_non_empty=False)
    emotional_weight = _normalize_emotional_weight(str(record["emotional_weight"]))
    detected_at = _required_datetime("detected_at", str(record["detected_at"]))
    _validate_safety(record)

    if record["fragment_ids"] != fragment_ids:
        raise ValueError("fragment_ids_not_normalized")
    if record["contrast_pair"] != contrast_pair:
        raise ValueError("contrast_pair_not_normalized")
    if record["matched_terms"] != matched_terms:
        raise ValueError("matched_terms_not_normalized")
    if record["related_theme_ids"] != related_theme_ids:
        raise ValueError("related_theme_ids_not_normalized")
    if record["emotional_weight"] != emotional_weight:
        raise ValueError("emotional_weight_not_normalized")
    if record["detected_at"] != detected_at:
        raise ValueError("detected_at_not_normalized")
    if record["pressure_id"] != pressure_id_from_material(fragment_ids=fragment_ids, contrast_pair=contrast_pair):
        raise ValueError("pressure_id_mismatch")


def validate_essay_candidate_record(record: Mapping[str, Any]) -> None:
    _require_record_type(record, ESSAY_CANDIDATE_RECORD_TYPE)
    _require_schema(record)
    _require_keys(
        record,
        (
            "candidate_id",
            "title",
            "pressure_ids",
            "fragment_ids",
            "theme_ids",
            "contrast_pair",
            "supporting_fragment_count",
            "source_types",
            "score",
            "status",
            "created_at",
            "external_action_allowed",
        ),
    )
    title = _required_text("title", record["title"])
    pressure_ids = _normalize_id_list("pressure_ids", record["pressure_ids"], require_non_empty=True)
    fragment_ids = _normalize_id_list("fragment_ids", record["fragment_ids"], require_non_empty=True)
    theme_ids = _normalize_id_list("theme_ids", record["theme_ids"], require_non_empty=False)
    contrast_pair = _normalize_contrast_pair(record["contrast_pair"])
    supporting_fragment_count = _positive_int("supporting_fragment_count", record["supporting_fragment_count"])
    source_types = _normalize_source_type_list(record["source_types"])
    score = _score_value(record["score"])
    status = _normalize_candidate_status(str(record["status"]))
    created_at = _required_datetime("created_at", str(record["created_at"]))
    _validate_safety(record)

    if record["pressure_ids"] != pressure_ids:
        raise ValueError("pressure_ids_not_normalized")
    if record["fragment_ids"] != fragment_ids:
        raise ValueError("fragment_ids_not_normalized")
    if record["theme_ids"] != theme_ids:
        raise ValueError("theme_ids_not_normalized")
    if record["contrast_pair"] != contrast_pair:
        raise ValueError("contrast_pair_not_normalized")
    if record["supporting_fragment_count"] != supporting_fragment_count:
        raise ValueError("supporting_fragment_count_not_normalized")
    if supporting_fragment_count != len(fragment_ids):
        raise ValueError("supporting_fragment_count_mismatch")
    if record["source_types"] != source_types:
        raise ValueError("source_types_not_normalized")
    if record["score"] != score:
        raise ValueError("score_not_normalized")
    if record["status"] != status:
        raise ValueError("status_not_normalized")
    if record["created_at"] != created_at:
        raise ValueError("created_at_not_normalized")
    expected_id = essay_candidate_id_from_material(
        title=title,
        pressure_ids=pressure_ids,
        fragment_ids=fragment_ids,
        theme_ids=theme_ids,
        contrast_pair=contrast_pair,
    )
    if record["candidate_id"] != expected_id:
        raise ValueError("candidate_id_mismatch")


def normalize_for_matching(value: Any) -> str:
    return _normalize_identity_text(str(value or ""))


def split_terms(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", normalize_for_matching(value)) if part}


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


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    return value.strip()


def _normalize_identity_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_source_type(value: str) -> str:
    normalized = normalize_token(_required_text("source_type", value))
    if normalized not in SOURCE_TYPES:
        raise ValueError(f"unsupported_source_type:{value}")
    return normalized


def _normalize_theme_status(value: str) -> str:
    normalized = normalize_token(_required_text("status", value))
    if normalized not in THEME_STATUSES:
        raise ValueError(f"unsupported_theme_status:{value}")
    return normalized


def _normalize_emotional_weight(value: str) -> str:
    normalized = normalize_token(_required_text("emotional_weight", value))
    if normalized not in EMOTIONAL_WEIGHTS:
        raise ValueError(f"unsupported_emotional_weight:{value}")
    return normalized


def _normalize_candidate_status(value: str) -> str:
    normalized = normalize_token(_required_text("status", value))
    if normalized not in ESSAY_CANDIDATE_STATUSES:
        raise ValueError(f"unsupported_candidate_status:{value}")
    return normalized


def _normalize_phrase_list(field: str, values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"invalid_{field}")
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"invalid_{field}")
        text = _normalize_identity_text(value)
        if text:
            normalized.add(text)
    return sorted(normalized)


def _normalize_id_list(field: str, values: Sequence[Any], *, require_non_empty: bool) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"invalid_{field}")
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"invalid_{field}")
        text = value.strip()
        if text:
            normalized.add(text)
    if require_non_empty and not normalized:
        raise ValueError(f"missing_{field}")
    return sorted(normalized)


def _normalize_contrast_pair(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("invalid_contrast_pair")
    pair: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("invalid_contrast_pair")
        text = _normalize_identity_text(value)
        if text:
            pair.append(text)
    if len(pair) != 2:
        raise ValueError("contrast_pair_must_have_two_terms")
    if pair[0] == pair[1]:
        raise ValueError("contrast_pair_must_have_two_terms")
    return pair


def _normalize_source_type_list(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("invalid_source_types")
    normalized = {_normalize_source_type(str(value)) for value in values}
    if not normalized:
        raise ValueError("missing_source_types")
    return sorted(normalized)


def _positive_int(field: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid_integer_field:{field}")
    if value <= 0:
        raise ValueError(f"non_positive_integer_field:{field}")
    return value


def _score_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid_score")
    if value < 0 or value > 10:
        raise ValueError("score_must_be_0_to_10")
    return value


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


def _require_false(field: str, value: Any) -> None:
    if value is not False:
        raise ValueError(f"{field}_not_allowed")


def _validate_safety(record: Mapping[str, Any]) -> None:
    if record.get("external_action_allowed") is not False:
        raise ValueError("external_action_allowed_not_allowed")
