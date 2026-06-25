from __future__ import annotations

import pytest

from app.retention.dispatch import plan_dispatch
from app.retention.models import ALLOWED_SOURCES, build_contact_seed_event, build_contact_snapshot, validate_source
from app.retention.transitions import evaluate_transition


def _snapshot_for_event(event: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    transition = evaluate_transition(event, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=event, transition=transition)
    assert snapshot is not None
    return transition, snapshot


def test_public_website_is_valid_acquisition_source_value() -> None:
    assert "public_website" in ALLOWED_SOURCES
    assert validate_source(" public_website ") == "public_website"


def test_public_website_pending_signup_statuses_remain_outside_retention_state() -> None:
    for consent_status in ("unknown", "import_pending_verification"):
        with pytest.raises(ValueError, match="public_website_requires_confirmation"):
            build_contact_seed_event(
                source="public_website",
                identifier_kind="email",
                identifier_value="public_website_contact",
                consent_status=consent_status,
            )


def test_public_website_cannot_establish_dispatchable_consent_by_itself() -> None:
    for consent_status in ("opted_in", "soft_opt_in"):
        with pytest.raises(ValueError, match="public_website_requires_confirmation"):
            build_contact_seed_event(
                source="public_website",
                identifier_kind="email",
                identifier_value="public_website_contact",
                consent_status=consent_status,
            )


def test_public_website_alone_cannot_make_contact_dispatch_eligible() -> None:
    with pytest.raises(ValueError, match="public_website_requires_confirmation"):
        build_contact_seed_event(
            source="public_website",
            identifier_kind="email",
            identifier_value="public_website_contact",
            consent_status="opted_in",
        )


def test_existing_sources_keep_existing_dispatchable_consent_behavior() -> None:
    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="substack_contact",
        consent_status="opted_in",
    )

    transition, snapshot = _snapshot_for_event(event)

    assert transition["decision"] == "applied"
    assert transition["to_state"] == "subscribed"
    assert snapshot["current_state"] == "subscribed"
    assert snapshot["dispatch_policy"]["allow_email"] is True

    dispatch_plan = plan_dispatch(snapshot, contact_id=str(snapshot["contact_id"]))
    assert dispatch_plan["decision"] == "planned"
    assert dispatch_plan["channel"] == "email"
    assert dispatch_plan["dispatch_type"] == "orientation_email"
