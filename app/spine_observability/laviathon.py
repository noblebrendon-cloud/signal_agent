from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.retention.identity import normalize_token, sha256_hex
from app.retention.jsonl_store import stable_json_dumps


SCHEMA_VERSION = "1.0"
MAX_IDENTITY_TEXT_CHARS = 200

ALLOWED_SPINE_TARGETS = (
    "reflective",
    "governance",
    "retention",
    "dashboard",
    "unknown",
)

ALLOWED_OBSERVATION_TYPES = (
    "critique",
    "risk",
    "opportunity",
    "coherence_check",
    "public_post_candidate",
)

ALLOWED_REVIEW_STATUSES = (
    "pending",
    "approved",
    "rejected",
)

REQUIRED_FIELDS = (
    "created_at",
    "source_context",
    "spine_target",
    "observation_type",
    "claim",
    "evidence",
    "recommendation",
    "public_safe",
)

OPTIONAL_FIELDS = (
    "schema_version",
    "observation_id",
    "entity_id",
    "source_artifact_id",
    "requires_human_review",
    "review_status",
    "external_action_allowed",
)

LAVIATHON_IDENTITY = {
    "role": "governed_synthetic_systems_evaluator",
    "capabilities": (
        "systems_design_critique",
        "ai_orchestration_evaluation",
        "execution_integrity_observation",
    ),
    "not_human": True,
    "autonomous": False,
    "authorized_to_contact_people": False,
    "authorized_to_publish_externally": False,
    "human_approved_output_only": True,
}


def normalize_observation(
    record: Mapping[str, Any],
    *,
    require_entity_id: bool = False,
) -> dict:
    if not isinstance(record, Mapping):
        raise ValueError("invalid_observation_record")
    _reject_human_representation(record)
    _reject_unknown_fields(record)
    _require_keys(record, REQUIRED_FIELDS)

    entity_id = _optional_identity_text("entity_id", record.get("entity_id"))
    if require_entity_id and entity_id is None:
        raise ValueError("missing_entity_id")
    source_artifact_id = _optional_identity_text(
        "source_artifact_id",
        record.get("source_artifact_id"),
    )

    normalized = {
        "schema_version": _schema_version(record.get("schema_version", SCHEMA_VERSION)),
        "created_at": _datetime_text("created_at", record["created_at"]),
        "source_context": _required_text("source_context", record["source_context"]),
        "spine_target": _allowed_value(
            "spine_target",
            record["spine_target"],
            ALLOWED_SPINE_TARGETS,
        ),
        "observation_type": _allowed_value(
            "observation_type",
            record["observation_type"],
            ALLOWED_OBSERVATION_TYPES,
        ),
        "claim": _required_text("claim", record["claim"]),
        "evidence": _required_text("evidence", record["evidence"]),
        "recommendation": _required_text("recommendation", record["recommendation"]),
        "public_safe": _required_bool("public_safe", record["public_safe"]),
        "requires_human_review": _optional_bool(
            "requires_human_review",
            record.get("requires_human_review", True),
        ),
        "review_status": _allowed_value(
            "review_status",
            record.get("review_status", "pending"),
            ALLOWED_REVIEW_STATUSES,
        ),
        "external_action_allowed": _external_action_allowed(
            record.get("external_action_allowed", False)
        ),
    }
    if entity_id is not None:
        normalized["entity_id"] = entity_id
    if source_artifact_id is not None:
        normalized["source_artifact_id"] = source_artifact_id
    if normalized["observation_type"] == "public_post_candidate":
        if normalized["requires_human_review"] is not True:
            raise ValueError("public_candidate_requires_human_review")
        if normalized["review_status"] != "pending":
            raise ValueError("public_candidate_review_must_start_pending")

    expected_id = observation_id_from_record(normalized)
    provided_id = record.get("observation_id")
    if provided_id is not None and _required_text("observation_id", provided_id) != expected_id:
        raise ValueError("observation_id_mismatch")
    normalized["observation_id"] = expected_id
    return dict(sorted(normalized.items()))


def observation_id_from_record(record: Mapping[str, Any]) -> str:
    material = {
        "claim": _required_text("claim", record["claim"]),
        "evidence": _required_text("evidence", record["evidence"]),
        "observation_type": _allowed_value(
            "observation_type",
            record["observation_type"],
            ALLOWED_OBSERVATION_TYPES,
        ),
        "public_safe": _required_bool("public_safe", record["public_safe"]),
        "recommendation": _required_text("recommendation", record["recommendation"]),
        "requires_human_review": _optional_bool(
            "requires_human_review",
            record.get("requires_human_review", True),
        ),
        "review_status": _allowed_value(
            "review_status",
            record.get("review_status", "pending"),
            ALLOWED_REVIEW_STATUSES,
        ),
        "source_context": _required_text("source_context", record["source_context"]),
        "spine_target": _allowed_value(
            "spine_target",
            record["spine_target"],
            ALLOWED_SPINE_TARGETS,
        ),
    }
    entity_id = _optional_identity_text("entity_id", record.get("entity_id"))
    if entity_id is not None:
        material["entity_id"] = entity_id
    source_artifact_id = _optional_identity_text(
        "source_artifact_id",
        record.get("source_artifact_id"),
    )
    if source_artifact_id is not None:
        material["source_artifact_id"] = source_artifact_id
    return f"lob_{sha256_hex(stable_json_dumps(material))[:16]}"


def _reject_unknown_fields(record: Mapping[str, Any]) -> None:
    allowed = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    unknown = sorted(str(key) for key in record if key not in allowed)
    if unknown:
        raise ValueError(f"unknown_fields:{','.join(unknown)}")


def _reject_human_representation(record: Mapping[str, Any]) -> None:
    if normalize_token(str(record.get("actor_type", ""))) == "human":
        raise ValueError("laviathon_not_human")
    for key in ("is_human", "represents_human"):
        if record.get(key) is True:
            raise ValueError("laviathon_not_human")


def _require_keys(record: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")


def _schema_version(value: Any) -> str:
    if value != SCHEMA_VERSION:
        raise ValueError(f"invalid_schema_version:{value}")
    return SCHEMA_VERSION


def _required_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"missing_{field}")
    return normalized


def _optional_identity_text(field: str, value: Any) -> str | None:
    if value is None:
        return None
    normalized = _required_text(field, value)
    if len(normalized) > MAX_IDENTITY_TEXT_CHARS:
        raise ValueError(f"{field}_too_long")
    return normalized


def _allowed_value(field: str, value: Any, allowed: tuple[str, ...]) -> str:
    normalized = normalize_token(_required_text(field, value))
    if normalized not in allowed:
        raise ValueError(f"invalid_{field}:{normalized}")
    return normalized


def _required_bool(field: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"invalid_{field}")
    return value


def _optional_bool(field: str, value: Any) -> bool:
    return _required_bool(field, value)


def _external_action_allowed(value: Any) -> bool:
    if value is not False:
        raise ValueError("external_action_not_allowed")
    return False


def _datetime_text(field: str, value: Any) -> str:
    raw = _required_text(field, value)
    candidate = raw
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
