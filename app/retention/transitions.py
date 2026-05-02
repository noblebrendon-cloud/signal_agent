from __future__ import annotations

from typing import Any

from app.retention.identity import normalize_token, transition_id_from_material
from app.retention.jsonl_store import find_latest_record
from app.retention.models import (
    AWARE_CONSENT_STATUSES,
    DISPATCHABLE_CONSENT_STATUSES,
    SUPPRESSION_EVENT_TYPES,
)


def load_latest_contact_snapshot(contact_id: str, *, repo_root=None) -> dict[str, Any] | None:
    return find_latest_record(
        "contacts.jsonl",
        lambda row: row.get("record_type") == "contact_snapshot" and row.get("contact_id") == contact_id,
        repo_root=repo_root,
    )


def _decision_payload(
    *,
    event_id: str,
    contact_id: str,
    from_state: str | None,
    to_state: str | None,
    decision: str,
    rule_id: str,
    reason_codes: list[str],
) -> dict[str, Any]:
    transition_id = transition_id_from_material(
        event_id=event_id,
        contact_id=contact_id,
        from_state=from_state,
        to_state=to_state,
        rule_id=rule_id,
    )
    return {
        "record_type": "transition_decision",
        "schema_version": "1.0",
        "transition_id": transition_id,
        "event_id": event_id,
        "contact_id": contact_id,
        "from_state": from_state,
        "to_state": to_state,
        "decision": decision,
        "rule_id": rule_id,
        "reason_codes": reason_codes,
    }


def evaluate_transition(
    event: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise TypeError("event must be a dict")

    event_id = str(event.get("event_id") or "")
    contact_id = str(event.get("contact_id") or event.get("actor", {}).get("contact_id") or "")
    from_state = None
    if previous_snapshot:
        from_state = str(previous_snapshot.get("current_state") or "") or None

    if event.get("record_type") != "canonical_event":
        return _decision_payload(
            event_id=event_id,
            contact_id=contact_id,
            from_state=from_state,
            to_state=from_state,
            decision="quarantined",
            rule_id="retention.invalid_record_type",
            reason_codes=["record_type_not_canonical_event"],
        )

    scope = normalize_token(event.get("scope") or "")
    if scope != "contact":
        return _decision_payload(
            event_id=event_id,
            contact_id=contact_id,
            from_state=from_state,
            to_state=from_state,
            decision="rejected",
            rule_id="retention.aggregate_block",
            reason_codes=["aggregate_events_cannot_mutate_contacts"],
        )

    event_type = normalize_token(event.get("event_type") or "")
    suppression_event_type = "objection" if event_type in {"objection", "lawful_objection"} else event_type
    consent_status = normalize_token(event.get("consent", {}).get("email_marketing_status") or "")

    if from_state == "suppressed" and event_type not in SUPPRESSION_EVENT_TYPES:
        return _decision_payload(
            event_id=event_id,
            contact_id=contact_id,
            from_state=from_state,
            to_state="suppressed",
            decision="noop",
            rule_id="retention.suppressed_sticky",
            reason_codes=["suppressed_state_sticky"],
        )

    target_state: str | None = None
    rule_id = "retention.unhandled"
    reason_codes: list[str] = []

    if event_type in SUPPRESSION_EVENT_TYPES or suppression_event_type == "objection":
        target_state = "suppressed"
        rule_id = f"retention.{suppression_event_type}.to_suppressed"
        reason_codes = [f"event_type:{suppression_event_type}"]
    elif event_type == "contact_seeded":
        if consent_status in DISPATCHABLE_CONSENT_STATUSES:
            target_state = "subscribed"
            rule_id = "retention.contact_seeded.to_subscribed"
            reason_codes = ["dispatchable_consent"]
        elif consent_status in AWARE_CONSENT_STATUSES:
            target_state = "aware"
            rule_id = "retention.contact_seeded.to_aware"
            reason_codes = ["consent_pending_verification"]
        else:
            return _decision_payload(
                event_id=event_id,
                contact_id=contact_id,
                from_state=from_state,
                to_state=from_state,
                decision="quarantined",
                rule_id="retention.contact_seeded.unsupported_consent",
                reason_codes=[f"unsupported_consent_status:{consent_status or 'missing'}"],
            )
    else:
        return _decision_payload(
            event_id=event_id,
            contact_id=contact_id,
            from_state=from_state,
            to_state=from_state,
            decision="quarantined",
            rule_id="retention.unhandled_event_type",
            reason_codes=[f"unsupported_event_type:{event_type or 'missing'}"],
        )

    if from_state == target_state:
        return _decision_payload(
            event_id=event_id,
            contact_id=contact_id,
            from_state=from_state,
            to_state=target_state,
            decision="noop",
            rule_id=rule_id,
            reason_codes=reason_codes + ["state_already_current"],
        )

    return _decision_payload(
        event_id=event_id,
        contact_id=contact_id,
        from_state=from_state,
        to_state=target_state,
        decision="applied",
        rule_id=rule_id,
        reason_codes=reason_codes,
    )
