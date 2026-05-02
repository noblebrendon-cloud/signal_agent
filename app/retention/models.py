from __future__ import annotations

from typing import Any

from app.retention.identity import (
    contact_id_from_identifier,
    event_id_from_material,
    identifier_hash,
    normalize_token,
)


ALLOWED_SOURCES = ("substack", "linkedin", "meta", "youtube", "operator")
CLI_CONSENT_STATUSES = (
    "opted_in",
    "soft_opt_in",
    "unknown",
    "import_pending_verification",
)
DISPATCHABLE_CONSENT_STATUSES = {"opted_in", "soft_opt_in"}
AWARE_CONSENT_STATUSES = {"unknown", "import_pending_verification"}
SUPPRESSION_EVENT_TYPES = {"unsubscribe", "hard_bounce", "spam_complaint", "objection", "lawful_objection"}
STATE_RANKS = {
    "suppressed": 0,
    "aware": 10,
    "subscribed": 20,
}


def validate_source(source: str) -> str:
    normalized = normalize_token(source)
    if normalized not in ALLOWED_SOURCES:
        raise ValueError(f"unsupported_source:{source}")
    return normalized


def validate_identifier_kind(identifier_kind: str) -> str:
    normalized = normalize_token(identifier_kind)
    if normalized != "email":
        raise ValueError(f"unsupported_identifier_kind:{identifier_kind}")
    return normalized


def validate_cli_consent_status(consent_status: str) -> str:
    normalized = normalize_token(consent_status)
    if normalized not in CLI_CONSENT_STATUSES:
        raise ValueError(f"unsupported_consent_status:{consent_status}")
    return normalized


def build_contact_seed_event(
    *,
    source: str,
    identifier_kind: str,
    identifier_value: str,
    consent_status: str,
    event_type: str = "contact_seeded",
    scope: str = "contact",
    source_mode: str = "manual",
    event_key: str | None = None,
) -> dict[str, Any]:
    normalized_source = validate_source(source)
    normalized_kind = validate_identifier_kind(identifier_kind)
    normalized_consent = validate_cli_consent_status(consent_status)

    id_hash = identifier_hash(normalized_kind, identifier_value)
    contact_id = contact_id_from_identifier(normalized_kind, identifier_value)
    event_id = event_id_from_material(
        event_type=event_type,
        source=normalized_source,
        identifier_hash_value=id_hash,
        consent_status=normalized_consent,
        event_key=event_key,
    )

    return {
        "record_type": "canonical_event",
        "schema_version": "1.0",
        "event_id": event_id,
        "event_type": normalize_token(event_type),
        "source": normalized_source,
        "source_mode": normalize_token(source_mode) or "manual",
        "scope": normalize_token(scope),
        "contact_id": contact_id,
        "identifier_kind": normalized_kind,
        "identifier_hash": id_hash,
        "actor": {
            "contact_id": contact_id,
            "identifier_kind": normalized_kind,
            "identifier_hash": id_hash,
            "linkage_status": "resolved",
        },
        "consent": {
            "email_marketing_status": normalized_consent,
        },
    }


def build_contact_snapshot(
    *,
    previous_snapshot: dict[str, Any] | None,
    event: dict[str, Any],
    transition: dict[str, Any],
) -> dict[str, Any] | None:
    if transition.get("decision") != "applied":
        return None

    prior = dict(previous_snapshot or {})
    prior_metrics = dict(prior.get("engagement_metrics") or {})
    prior_events = int(prior_metrics.get("event_count", 0))
    contact_version = int(prior.get("contact_version", 0)) + 1
    current_state = str(transition["to_state"])

    consent = dict(prior.get("consent") or {})
    consent.update(dict(event.get("consent") or {}))

    state_history = list(prior.get("state_history") or [])
    state_history.append(
        {
            "state": current_state,
            "event_id": event["event_id"],
            "transition_id": transition["transition_id"],
        }
    )

    source_platforms = sorted(set(prior.get("source_platforms") or []) | {str(event["source"])})

    engagement_metrics = dict(prior_metrics)
    engagement_metrics["event_count"] = prior_events + 1
    engagement_metrics["last_event_type"] = event["event_type"]

    conversion = {
        "objective": None,
        "status": "none",
        "converted_at": None,
        "evidence_event_id": None,
    }
    conversion.update(dict(prior.get("conversion") or {}))

    email_status = str(consent.get("email_marketing_status") or "")
    dispatch_policy = {
        "allow_dispatch": current_state != "suppressed",
        "allow_email": current_state == "subscribed" and email_status in DISPATCHABLE_CONSENT_STATUSES,
        "allow_internal_task": current_state == "aware",
    }

    return {
        "record_type": "contact_snapshot",
        "schema_version": "1.0",
        "contact_id": event["contact_id"],
        "contact_version": contact_version,
        "source_platforms": source_platforms,
        "first_touch_event": prior.get("first_touch_event") or event["event_id"],
        "last_touch_event": event["event_id"],
        "current_state": current_state,
        "state_rank": STATE_RANKS.get(current_state, -1),
        "state_history": state_history,
        "identity_alignment_score": prior.get("identity_alignment_score", 0) or 0,
        "engagement_metrics": engagement_metrics,
        "tags": list(prior.get("tags") or []),
        "segments": list(prior.get("segments") or []),
        "consent": consent,
        "conversion": conversion,
        "dispatch_policy": dispatch_policy,
    }
