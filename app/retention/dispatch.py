from __future__ import annotations

from typing import Any

from app.retention.identity import dispatch_id_from_material
from app.retention.models import DISPATCHABLE_CONSENT_STATUSES


def plan_dispatch(contact_snapshot: dict[str, Any] | None, *, contact_id: str | None = None) -> dict[str, Any]:
    snapshot = dict(contact_snapshot or {})
    resolved_contact_id = str(snapshot.get("contact_id") or contact_id or "")
    current_state = str(snapshot.get("current_state") or "")
    consent_status = str(snapshot.get("consent", {}).get("email_marketing_status") or "")
    contact_version = int(snapshot.get("contact_version", 0) or 0)

    base = {
        "record_type": "content_dispatch_plan",
        "schema_version": "1.0",
        "contact_id": resolved_contact_id or None,
        "contact_version": contact_version or None,
        "current_state": current_state or None,
        "consent": dict(snapshot.get("consent") or {}),
    }

    if not snapshot:
        return {
            **base,
            "decision": "blocked",
            "reason_codes": ["no_contact_snapshot"],
        }

    if current_state == "suppressed":
        return {
            **base,
            "decision": "blocked",
            "reason_codes": ["suppressed_contacts_block_dispatch"],
        }

    if current_state == "subscribed" and consent_status in DISPATCHABLE_CONSENT_STATUSES:
        return {
            **base,
            "dispatch_id": dispatch_id_from_material(
                contact_id=resolved_contact_id,
                contact_version=contact_version,
                dispatch_type="orientation_email",
                channel="email",
            ),
            "decision": "planned",
            "dispatch_type": "orientation_email",
            "channel": "email",
            "template_key": "orientation_email_v1",
            "reason_codes": ["subscribed_contact_ready_for_orientation"],
        }

    if current_state == "aware":
        return {
            **base,
            "dispatch_id": dispatch_id_from_material(
                contact_id=resolved_contact_id,
                contact_version=contact_version,
                dispatch_type="internal_task",
                channel="internal",
            ),
            "decision": "planned",
            "dispatch_type": "internal_task",
            "channel": "internal",
            "template_key": "contact_review_task_v1",
            "reason_codes": ["awareness_requires_internal_followup"],
        }

    return {
        **base,
        "decision": "blocked",
        "reason_codes": ["no_matching_dispatch_rule"],
    }
