from __future__ import annotations

from typing import Iterable


WTPU_BRAND_ID = "we_the_people_united"

EDITORIAL_SECTIONS = (
    "power_accountability",
    "privacy_surveillance",
    "equal_justice_state_power",
    "public_record",
    "information_critical_thought",
)

CLAIM_TYPES = (
    "direct_quote",
    "public_record_fact",
    "source_supported_statement",
    "observation",
    "interpretation",
    "inference",
    "hypothesis",
    "unresolved_question",
    "allegation_requires_caution",
    "editorial_position",
    "recommendation",
)

SOURCE_TYPES = (
    "public_record",
    "court_record",
    "contract",
    "budget",
    "meeting_minutes",
    "transcript",
    "statute",
    "policy_document",
    "dataset",
    "primary_statement",
    "official_notice",
    "reputable_reporting",
    "records_request",
    "firsthand_observation",
    "secondary_analysis",
)

EVIDENCE_CONFIDENCE = (
    "direct_primary",
    "strong_corrobored",
    "moderate",
    "context_only",
    "disputed",
    "unverified",
    "unsupported_blocked",
)

INTERPRETATION_STATUS = (
    "evidence_only",
    "interpreted",
    "inferential",
    "contested",
    "needs_review",
    "blocked",
)

CORRECTION_STATUS = (
    "none",
    "update_added",
    "correction_pending",
    "corrected",
    "clarified",
    "retracted",
    "superseded",
)

ARCHIVE_STATUS = (
    "draft",
    "canonical",
    "campaign_active",
    "discussion_review",
    "archive_ready",
    "archived",
    "dossier_component",
    "superseded",
    "retired",
)

ESSAY_LIFECYCLE = (
    "draft",
    "review_requested",
    "reviewed",
    "canonical",
    "correction_pending",
    "corrected",
    "retracted",
    "superseded",
)

ADAPTATION_STATUSES = (
    "draft",
    "review_requested",
    "reviewed",
    "changes_requested",
    "retired",
)

FORBIDDEN_PUBLICATION_FIELDS = frozenset(
    {
        "release_eligible",
        "release_state",
        "release_id",
        "release_candidate",
        "scheduled_at",
        "scheduled_for",
        "scheduler_queue",
        "queue",
        "queue_id",
        "platform_id",
        "platform_post_id",
        "external_post_id",
        "external_url",
        "oauth",
        "oauth_state",
        "publisher_config",
        "publish",
        "published",
        "published_at",
        "publication_state",
        "export",
        "exported",
        "exported_at",
    }
)


class WTPUTaxonomyError(ValueError):
    pass


def validate_taxonomy_value(value: object, allowed: Iterable[str], field_name: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in set(allowed):
        raise WTPUTaxonomyError(f"wtpu_{field_name}_not_allowed:{normalized}")
    return normalized


def validate_section_id(value: object) -> str:
    return validate_taxonomy_value(value, EDITORIAL_SECTIONS, "section_id")


def validate_claim_type(value: object, *, allow_blank: bool = False) -> str:
    normalized = str(value or "").strip()
    if allow_blank and not normalized:
        return ""
    return validate_taxonomy_value(normalized, CLAIM_TYPES, "claim_type")


def validate_source_type(value: object) -> str:
    return validate_taxonomy_value(value, SOURCE_TYPES, "source_type")


def validate_evidence_confidence(value: object) -> str:
    return validate_taxonomy_value(value, EVIDENCE_CONFIDENCE, "evidence_confidence")


def validate_interpretation_status(value: object) -> str:
    return validate_taxonomy_value(value, INTERPRETATION_STATUS, "interpretation_status")


def validate_correction_status(value: object) -> str:
    return validate_taxonomy_value(value, CORRECTION_STATUS, "correction_status")


def validate_archive_status(value: object) -> str:
    return validate_taxonomy_value(value, ARCHIVE_STATUS, "archive_status")


def validate_essay_lifecycle(value: object) -> str:
    return validate_taxonomy_value(value, ESSAY_LIFECYCLE, "essay_lifecycle")


def validate_adaptation_status(value: object) -> str:
    return validate_taxonomy_value(value, ADAPTATION_STATUSES, "adaptation_status")
