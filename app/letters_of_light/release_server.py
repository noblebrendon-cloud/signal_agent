"""
app/letters_of_light/release_server.py - Local campaign manager for release gates.

This server exposes local review controls and explicit per-platform publish
actions. It stays bound to localhost by default.
"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import mimetypes
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default as email_default_policy
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.letters_of_light.brand_registry import DEFAULT_BRAND_ID, get_brand, safe_brand_list, safe_brand_metadata
from app.letters_of_light.creation_manager import (
    get_creation_job,
    list_creation_jobs,
    start_creation_job,
)
from app.letters_of_light.release import (
    approve_release,
    check_release_eligibility,
    create_release_candidate,
    export_campaign,
    scan_letters,
    _get_root,
    _letter_dir,
    _read_json,
    _resolve_artifact_path,
)
from app.letters_of_light.governed_handoff import (
    GOVERNED_HANDOFF_METADATA_KEY,
    GovernedProjectStudioHandoffConflict,
    GovernedProjectStudioHandoffNotFound,
    GovernedProjectStudioHandoffRequest,
    GovernedProjectStudioHandoffValidationError,
    open_governed_drafting_brief_in_project_studio,
)
from app.letters_of_light.source_grounded_drafting import (
    OUTLINE_FROM_GOVERNED_BRIEF_MODE,
    SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY,
    SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED,
    SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE,
    SOURCE_GROUNDED_ACCEPTANCE_INDEX_KEY,
    SOURCE_GROUNDED_DRAFTING_METADATA_KEY,
    SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_ALREADY_LINKED,
    SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_CREATED,
    SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_REPAIRED_LINK,
    SourceGroundedOutlineAcceptanceConflict,
    SourceGroundedOutlineAcceptanceIntegrityError,
    SourceGroundedOutlineAcceptanceNotFound,
    SourceGroundedOutlineAcceptanceRequest,
    SourceGroundedOutlineAcceptanceValidationError,
    SourceGroundedOutlinePreviewRequest,
    accept_source_grounded_outline_preview,
    build_source_grounded_outline_preview,
    source_grounded_outline_acceptance_id,
    _resolve_authoritative_semantic_context,
)
from app.letters_of_light.source_grounded_prose_apply import (
    SOURCE_GROUNDED_PROSE_APPLY_STATUS_ALREADY_LINKED,
    SOURCE_GROUNDED_PROSE_APPLY_STATUS_CREATED,
    SOURCE_GROUNDED_PROSE_APPLY_STATUS_REPAIRED_LINK,
    CandidateEnvelopeSigner,
    CandidateEnvelopeVerifier,
    SourceGroundedCandidateEnvelope,
    SourceGroundedCandidateEnvelopeError,
    SourceGroundedProseApplyConflict,
    SourceGroundedProseApplyIntegrityError,
    SourceGroundedProseApplyNotFound,
    SourceGroundedProseApplyValidationError,
    SourceGroundedProseCandidateApplyRequest,
    apply_source_grounded_prose_candidate,
    seal_source_grounded_candidate,
    source_grounded_candidate_envelope_id,
)
from app.letters_of_light.source_grounded_prose_candidates import (
    SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_BLOCKED,
    SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_GENERATED,
    SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_PROVIDER_ERROR,
    SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_VALIDATION_ERROR,
    SourceGroundedProseCandidateRequest,
    build_source_grounded_prose_candidate,
)
from app.letters_of_light.release_site import publish_release_site, resolve_site_root
from app.letters_of_light.publishers.youtube import (
    YOUTUBE_CLIENT_SECRETS_ENV,
    publish_youtube,
)
from app.letters_of_light.project_studio import (
    asset_file,
    create_composition,
    create_composition_from_voice_capture,
    create_letter_from_voice_capture,
    create_project,
    create_project_letter,
    create_project_revision,
    clone_project_to_brand,
    extract_project_asset,
    get_voice_transcript,
    import_asset,
    list_voice_captures,
    list_projects,
    project_dir,
    project_payload,
    promote_render_to_release,
    register_voice_capture,
    render_file,
    start_render,
    transcribe_voice_capture,
    update_voice_transcript,
    update_project_review_fields,
)
from app.letters_of_light.production_derivative_promotion import (
    GovernedDraftPromotionConflict,
    GovernedDraftPromotionIntegrityError,
    GovernedDraftPromotionRequest,
    GovernedDraftPromotionValidationError,
    governed_draft_production_derivative_status,
    promote_governed_draft_to_production_derivative,
    validate_governed_draft_production_derivative_candidate,
)
from app.letters_of_light.transcription import transcription_readiness
from app.letters_of_light.wtpu_publication_dashboard import (
    handle_wtpu_publication_api,
    is_wtpu_publication_path,
    render_wtpu_publication_dashboard_page,
    wtpu_method_not_allowed_payload,
)
from signal_agent.governed_publishing import (
    GovernedPublishingLedger,
    derive_governed_drafting_brief,
    project_studio_draft_handoff_identity,
    replay_governed_publishing_events,
)
from signal_agent.structured_generation import (
    StructuredGenerationError,
    resolve_manual_generation_context,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
GOVERNED_PUBLISHING_STATE_ROOT = Path("data") / "state" / "governed_publishing"
SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY_ENV = "SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY"
SOURCE_GROUNDED_CANDIDATE_SIGNER_ID_ENV = "SOURCE_GROUNDED_CANDIDATE_SIGNER_ID"
SOURCE_GROUNDED_CANDIDATE_ENVELOPE_TTL_SECONDS_ENV = "SOURCE_GROUNDED_CANDIDATE_ENVELOPE_TTL_SECONDS"
SOURCE_GROUNDED_CANDIDATE_DEFAULT_SIGNER_ID = "source-grounded-candidate-local"
SOURCE_GROUNDED_CANDIDATE_DEFAULT_TTL_SECONDS = 900
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY_ENV = (
    "GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY"
)
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_TTL_SECONDS_ENV = (
    "GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_TTL_SECONDS"
)
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_DEFAULT_SIGNER_ID = (
    "governed-production-derivative-promotion-local"
)
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_DEFAULT_TTL_SECONDS = 900
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_VERSION = (
    "governed_production_derivative_promotion_envelope_v1"
)
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_PAYLOAD_VERSION = (
    "governed_production_derivative_promotion_payload_v1"
)
GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_ALGORITHM = "hmac-sha256"
GOVERNED_PRODUCTION_DERIVATIVE_AUTHORITY_NOTICE = (
    "This creates a separate production derivative for normal pipeline processing. "
    "It does not approve, release, export, schedule, publish, or grant platform authority."
)
GOVERNED_DRAFT_ROUTE_FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "approval",
        "approval_state",
        "approval_evidence",
        "artifact",
        "artifact_readiness",
        "package_readiness",
        "readiness",
        "readiness_state",
        "release_eligibility",
        "release_state",
        "publication",
        "published",
        "publish_state",
        "scheduled",
        "schedule",
        "schedule_state",
        "queue",
        "queue_state",
        "export",
        "export_state",
        "platform",
        "platform_state",
        "platform_adapter",
        "destination_brand_ref",
        "destination_surface_ref",
        "source_snapshot_ref",
        "canonical_node_id",
        "promotion_ref",
        "handoff_id",
        "handoff_metadata",
    }
)
GOVERNED_DRAFT_DISCOVERY_FORBIDDEN_CLIENT_FIELDS = (
    GOVERNED_DRAFT_ROUTE_FORBIDDEN_CLIENT_FIELDS
    - frozenset({"destination_brand_ref", "destination_surface_ref"})
)
GOVERNED_DRAFT_DISCOVERY_LINKED_STATES = frozenset({"any", "linked", "unlinked", "unavailable"})
SOURCE_GROUNDED_OUTLINE_FORBIDDEN_CLIENT_FIELDS = GOVERNED_DRAFT_ROUTE_FORBIDDEN_CLIENT_FIELDS | frozenset(
    {
        "governed_drafting_brief_id",
        "proposal_id",
        "source_support_refs",
        "origin_brand_ref",
        "destination_brand",
        "destination_brand_ref",
        "destination_surface",
        "destination_surface_ref",
        "promotion_ref",
        "claim_classifications",
        "claims",
        "readiness",
        "governed_authority",
        "governed_ledger",
    }
)
SOURCE_GROUNDED_PROSE_CANDIDATE_FORBIDDEN_CLIENT_FIELDS = SOURCE_GROUNDED_OUTLINE_FORBIDDEN_CLIENT_FIELDS | frozenset(
    {
        "candidate_text",
        "candidate_result",
        "candidate_output",
        "provider_output",
        "provider_credentials",
        "provider_config",
        "provider_api_key",
        "envelope_signature",
        "signing_key",
        "signing_material",
        "candidate_envelope",
        "semantic_context",
        "governed_semantic_context",
        "source_support_refs",
        "claim_classifications",
        "used_source_refs",
        "used_passage_refs",
        "segment_annotations",
    }
)
SOURCE_GROUNDED_PROSE_APPLY_FORBIDDEN_CLIENT_FIELDS = (
    SOURCE_GROUNDED_PROSE_CANDIDATE_FORBIDDEN_CLIENT_FIELDS
    - frozenset({"candidate_envelope"})
)
PRODUCTION_DERIVATIVE_PROMOTION_CANDIDATE_ALLOWED_FIELDS = frozenset(
    {
        "expected_source_body_hash",
        "promotion_intent_ref",
        "destination_brand_id",
        "operator_ref",
        "target_theme",
        "operator_note",
    }
)
PRODUCTION_DERIVATIVE_PROMOTION_APPLY_ALLOWED_FIELDS = frozenset(
    {
        "candidate_envelope",
        "expected_source_body_hash",
        "promotion_intent_ref",
        "operator_ref",
        "operator_note",
    }
)
PRODUCTION_DERIVATIVE_PROMOTION_FORBIDDEN_CLIENT_FIELDS = GOVERNED_DRAFT_ROUTE_FORBIDDEN_CLIENT_FIELDS | frozenset(
    {
        "authorized",
        "approval",
        "approved",
        "release",
        "release_eligible",
        "release_eligibility",
        "release_state",
        "export",
        "export_state",
        "schedule",
        "schedule_state",
        "publish",
        "publish_state",
        "publication",
        "publication_state",
        "published",
        "platform",
        "platform_adapter",
        "platform_state",
        "oauth",
        "queue",
        "queue_state",
        "target_letter_id",
        "promotion_id",
        "creation_job_id",
        "job_id",
        "initial_metadata",
        "promotion_receipt",
    }
)
GOVERNED_DRAFT_DISCOVERY_BLOCKER_MAP = {
    "proposal_not_promoted_to_draft_candidate": "invalid_promotion_state",
    "canonical_node_id_required": "missing_canonical_node",
    "canonical_node_missing": "missing_canonical_node",
    "origin_brand_ref_required": "missing_origin_brand",
    "destination_brand_ref_required": "missing_destination_brand",
    "destination_surface_ref_required": "missing_destination_surface",
    "source_support_refs_required": "missing_source_support",
    "source_snapshot_ref_required": "missing_source_snapshot",
    "promotion_ref_required": "missing_promotion_ref",
    "draft_intent_ref_required": "missing_draft_intent_context",
    "proposal_intent_ref_required": "missing_proposal_intent",
    "ready_for_draft_review_required": "draft_brief_blocked",
}


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, indent=2).encode("utf-8")


def _governed_publishing_ledger() -> GovernedPublishingLedger:
    return GovernedPublishingLedger(root=_get_root() / GOVERNED_PUBLISHING_STATE_ROOT)


def _source_grounding_references_for_proposal(proposal: Any) -> tuple[Dict[str, str], ...]:
    if proposal is None:
        return ()
    return tuple(
        {
            "reference_id": f"grounding.{proposal.proposal_id}.{index}",
            "source_ref": source_ref,
            "claim_classification": "observation",
            "reference_type": "source_support",
            "evidence_ref": source_ref,
        }
        for index, source_ref in enumerate(proposal.source_support, start=1)
    )


def _derive_governed_project_studio_readiness(
    *,
    proposal_id: str,
    draft_intent_ref: str,
    selected_passages: Any,
    working_title: str,
    writer_note: str,
):
    ledger = _governed_publishing_ledger()
    projection = replay_governed_publishing_events(ledger.read_events())
    proposal = projection.horizon_proposals.get(proposal_id)
    return derive_governed_drafting_brief(
        projection,
        proposal_id,
        draft_intent_ref=draft_intent_ref,
        source_grounding_references=_source_grounding_references_for_proposal(proposal),
        working_title=working_title,
        writer_notes=writer_note,
        selected_excerpt_expansion_refs=_selected_passage_refs(selected_passages),
    )


def _selected_passage_refs(selected_passages: Any) -> tuple[str, ...]:
    if not isinstance(selected_passages, list):
        return ()
    refs: list[str] = []
    for item in selected_passages:
        if not isinstance(item, dict):
            continue
        passage_id = str(item.get("passage_id") or "").strip()
        asset_id = str(item.get("asset_id") or item.get("source_asset_id") or "").strip()
        if passage_id and asset_id:
            ref = f"asset:{asset_id}:passage:{passage_id}"
        elif passage_id:
            ref = f"passage:{passage_id}"
        elif asset_id:
            ref = f"asset:{asset_id}"
        else:
            continue
        if ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _reject_governed_draft_client_authority_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(key for key in body if key in GOVERNED_DRAFT_ROUTE_FORBIDDEN_CLIENT_FIELDS)
    if forbidden:
        raise ValueError(f"governed_draft_client_authority_fields_forbidden:{','.join(forbidden)}")


def _reject_source_grounded_outline_client_authority_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(key for key in body if key in SOURCE_GROUNDED_OUTLINE_FORBIDDEN_CLIENT_FIELDS)
    if forbidden:
        raise ValueError(f"source_grounded_outline_client_authority_fields_forbidden:{','.join(forbidden)}")


def _reject_source_grounded_prose_candidate_client_authority_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(key for key in body if key in SOURCE_GROUNDED_PROSE_CANDIDATE_FORBIDDEN_CLIENT_FIELDS)
    if forbidden:
        raise ValueError(f"source_grounded_prose_candidate_client_authority_fields_forbidden:{','.join(forbidden)}")


def _reject_source_grounded_prose_apply_client_authority_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(key for key in body if key in SOURCE_GROUNDED_PROSE_APPLY_FORBIDDEN_CLIENT_FIELDS)
    if forbidden:
        raise ValueError(f"source_grounded_prose_apply_client_authority_fields_forbidden:{','.join(forbidden)}")


def _reject_governed_discovery_client_authority_fields(query: Dict[str, List[str]]) -> None:
    forbidden = sorted(key for key in query if key in GOVERNED_DRAFT_DISCOVERY_FORBIDDEN_CLIENT_FIELDS)
    if forbidden:
        raise ValueError(f"governed_draft_discovery_client_authority_fields_forbidden:{','.join(forbidden)}")


def _reject_production_derivative_candidate_client_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(
        key
        for key in body
        if key in PRODUCTION_DERIVATIVE_PROMOTION_FORBIDDEN_CLIENT_FIELDS
        or key not in PRODUCTION_DERIVATIVE_PROMOTION_CANDIDATE_ALLOWED_FIELDS
    )
    if forbidden:
        raise ValueError(
            "production_derivative_promotion_candidate_client_fields_forbidden:"
            + ",".join(forbidden)
        )


def _reject_production_derivative_apply_client_fields(body: Dict[str, Any]) -> None:
    forbidden = sorted(
        key
        for key in body
        if key in PRODUCTION_DERIVATIVE_PROMOTION_FORBIDDEN_CLIENT_FIELDS
        or key not in PRODUCTION_DERIVATIVE_PROMOTION_APPLY_ALLOWED_FIELDS
    )
    if forbidden:
        raise ValueError(
            "production_derivative_promotion_apply_client_fields_forbidden:"
            + ",".join(forbidden)
        )


class SourceGroundedProseProviderAuthorizationError(RuntimeError):
    pass


class GovernedProductionDerivativePromotionEnvelopeError(ValueError):
    pass


class GovernedProductionDerivativePromotionEnvelopeAuthorizationError(RuntimeError):
    pass


def _blockers_payload(readiness: Any) -> List[Dict[str, str]]:
    return [
        blocker.to_dict()
        for blocker in getattr(readiness, "blockers", ())
        if hasattr(blocker, "to_dict")
    ]


def _governed_draft_result_payload(result: Any, *, status: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "result_status": result.status,
        "project_id": result.project_id,
        "letter_id": result.letter_id,
        "job_id": result.job_id,
        "output_id": result.output_id,
        "draft_intent_ref": result.draft_intent_ref,
    }


def _source_grounded_outline_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        return ()
    refs: list[str] = []
    for item in values:
        ref = str(item or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _source_grounded_outline_selected_passages(body: Dict[str, Any]) -> tuple[Dict[str, Any], ...]:
    selected = body.get("selected_passages")
    if selected is None:
        return ()
    if not isinstance(selected, list):
        raise ValueError("selected_passages must be a list")
    return tuple(dict(item) for item in selected if isinstance(item, dict))


def _source_grounded_outline_asset_ids(body: Dict[str, Any], selected_passages: tuple[Dict[str, Any], ...]) -> tuple[str, ...]:
    explicit = _source_grounded_outline_refs(body.get("selected_source_asset_ids"))
    if explicit:
        return explicit
    asset_ids: list[str] = []
    for passage in selected_passages:
        asset_id = str(passage.get("asset_id") or passage.get("source_asset_id") or "").strip()
        if asset_id and asset_id not in asset_ids:
            asset_ids.append(asset_id)
    return tuple(asset_ids)


def _source_grounded_outline_preview_request(
    *,
    project_id: str,
    body: Dict[str, Any],
) -> SourceGroundedOutlinePreviewRequest:
    parent_letter_id = str(body.get("parent_letter_id") or body.get("letter_id") or "").strip()
    if not parent_letter_id:
        raise ValueError("parent_letter_id is required")
    preview_intent_ref = str(body.get("preview_intent_ref") or "").strip()
    if not preview_intent_ref:
        raise ValueError("preview_intent_ref is required")
    selected_passages = _source_grounded_outline_selected_passages(body)
    selected_asset_ids = _source_grounded_outline_asset_ids(body, selected_passages)
    return SourceGroundedOutlinePreviewRequest(
        project_id=project_id,
        letter_id=parent_letter_id,
        drafting_mode=OUTLINE_FROM_GOVERNED_BRIEF_MODE,
        selected_source_asset_ids=selected_asset_ids,
        selected_passages=selected_passages,
        actor_ref=str(body.get("actor_ref") or "operator.local").strip() or "operator.local",
        preview_intent_ref=preview_intent_ref,
        writer_note=str(body.get("writer_note") or "").strip(),
        format_intent=str(body.get("format_intent") or "").strip(),
        selected_excerpt_refs=_source_grounded_outline_refs(body.get("selected_excerpt_refs")),
    )


def _source_grounded_outline_acceptance_request(
    *,
    preview_request: SourceGroundedOutlinePreviewRequest,
    preview: Any,
    body: Dict[str, Any],
) -> SourceGroundedOutlineAcceptanceRequest:
    preview_id = str(body.get("preview_id") or "").strip()
    if not preview_id:
        raise ValueError("preview_id is required")
    if preview.source_grounding is None:
        raise ValueError("source_grounding_required")
    return SourceGroundedOutlineAcceptanceRequest(
        project_id=preview_request.project_id,
        parent_letter_id=preview_request.letter_id,
        preview_id=preview_id,
        preview_intent_ref=preview_request.preview_intent_ref,
        selected_source_asset_ids=preview_request.selected_source_asset_ids,
        selected_source_passage_refs=tuple(preview.source_grounding.selected_passage_refs),
        selected_passages=preview_request.selected_passages,
        actor_ref=preview_request.actor_ref,
        writer_note=preview_request.writer_note,
        format_intent=preview_request.format_intent,
        selected_excerpt_refs=preview_request.selected_excerpt_refs,
    )


def _source_grounded_letter_identity(letter_id: str) -> Dict[str, Any]:
    letter = _read_json(_letter_dir(letter_id) / "letter.json")
    if not letter:
        return {
            "letter_id": letter_id,
            "title": "",
            "lifecycle_state": "",
            "available": False,
        }
    metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
    return {
        "letter_id": str(letter.get("letter_id") or letter_id),
        "title": str(letter.get("title") or letter.get("theme") or ""),
        "lifecycle_state": str(letter.get("lifecycle_state") or ""),
        "status": str(metadata.get("status") or letter.get("status") or ""),
        "available": _source_grounded_letter_available(letter),
    }


def _source_grounded_letter_available(letter: Dict[str, Any]) -> bool:
    metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
    lifecycle_state = str(letter.get("lifecycle_state") or metadata.get("lifecycle_state") or "").strip().lower()
    metadata_state = str(metadata.get("status") or "").strip().lower()
    return lifecycle_state not in {"archived", "deleted"} and metadata_state not in {"archived", "deleted"}


def _source_grounded_outline_semantic_context(parent_letter_id: str) -> tuple[Dict[str, Any], str, List[Dict[str, str]]]:
    letter = _read_json(_letter_dir(parent_letter_id) / "letter.json")
    metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
    handoff = metadata.get(GOVERNED_HANDOFF_METADATA_KEY)
    if not isinstance(handoff, dict):
        return (
            {},
            SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED,
            [
                {
                    "code": "governed_handoff_metadata_required",
                    "field": "parent_letter_id",
                    "message": "Parent Letter does not contain governed handoff metadata.",
                }
            ],
        )
    try:
        semantic_context = _resolve_authoritative_semantic_context(handoff)
        return (
            dict(semantic_context),
            str(semantic_context.get("semantic_resolution_status") or SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE),
            [],
        )
    except SourceGroundedOutlineAcceptanceValidationError as exc:
        message = str(exc)
        code = message
        if message.startswith(f"{SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED}:"):
            code = message.split(":", 1)[1] or "governed_semantic_context_blocked"
        return (
            {},
            SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED,
            [
                {
                    "code": code,
                    "field": "governed_semantic_context",
                    "message": message,
                }
            ],
        )


def _source_grounded_outline_blockers(
    preview: Any,
    semantic_blockers: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    blockers: list[Dict[str, str]] = []
    for blocker in getattr(preview, "blockers", ()):
        if hasattr(blocker, "to_dict"):
            blockers.append(blocker.to_dict())
    blockers.extend(semantic_blockers)
    deduped: list[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for blocker in blockers:
        code = str(blocker.get("code") or "").strip()
        field = str(blocker.get("field") or "").strip()
        key = (code, field)
        if code and key not in seen:
            deduped.append(blocker)
            seen.add(key)
    return deduped


def _source_grounded_outline_item_payload(item: Any) -> Dict[str, Any]:
    payload = item.to_dict() if hasattr(item, "to_dict") else dict(item)
    return {
        "item_id": str(payload.get("item_id") or ""),
        "item_type": str(payload.get("item_type") or ""),
        "label": str(payload.get("label") or ""),
        "role": str(payload.get("role") or ""),
        "claim_classification": str(payload.get("claim_classification") or ""),
        "source_support_ref_count": len(payload.get("source_support_refs") or []),
        "selected_passage_refs": list(payload.get("selected_passage_refs") or []),
        "selected_excerpt_refs": list(payload.get("selected_excerpt_refs") or []),
        "derived_from": list(payload.get("derived_from") or []),
        "support_status": str(payload.get("support_status") or ""),
        "fact_verified": bool(payload.get("fact_verified")),
    }


def _source_grounded_existing_child_context(
    *,
    project_id: str,
    parent_letter_id: str,
    preview_id: str,
    handoff_id: str,
    preview_intent_ref: str,
) -> Dict[str, Any]:
    if not (project_id and parent_letter_id and preview_id and handoff_id and preview_intent_ref):
        return {"exists": False, "available": False, "status": "none"}
    acceptance_id = source_grounded_outline_acceptance_id(
        parent_letter_id=parent_letter_id,
        preview_id=preview_id,
        governed_handoff_id=handoff_id,
        preview_intent_ref=preview_intent_ref,
    )
    project = _read_project_without_mutation(project_id)
    index = project.get(SOURCE_GROUNDED_ACCEPTANCE_INDEX_KEY)
    if not isinstance(index, dict):
        return {"exists": False, "available": False, "status": "none", "acceptance_id": acceptance_id}
    entry = index.get(acceptance_id)
    if not isinstance(entry, dict):
        return {"exists": False, "available": False, "status": "none", "acceptance_id": acceptance_id}
    child_letter_id = str(entry.get("child_letter_id") or entry.get("letter_id") or "").strip()
    if not child_letter_id:
        return {
            "exists": True,
            "available": False,
            "status": "accepted_child_unavailable",
            "acceptance_id": acceptance_id,
        }
    identity = _source_grounded_letter_identity(child_letter_id)
    if not identity.get("available"):
        return {
            "exists": True,
            "available": False,
            "status": "accepted_child_unavailable",
            "acceptance_id": acceptance_id,
            "child_letter_id": child_letter_id,
        }
    return {
        "exists": True,
        "available": True,
        "status": "linked_existing",
        "acceptance_id": acceptance_id,
        "child_letter_id": child_letter_id,
        "title": identity.get("title", ""),
        "lifecycle_state": identity.get("lifecycle_state", ""),
        "open_url": f"/?letter_id={child_letter_id}",
    }


def _source_grounded_outline_preview_payload(
    *,
    request: SourceGroundedOutlinePreviewRequest,
    preview: Any,
    semantic_context: Dict[str, Any],
    semantic_status: str,
    semantic_blockers: List[Dict[str, str]],
) -> Dict[str, Any]:
    source_grounding = preview.source_grounding.to_dict() if preview.source_grounding is not None else {}
    lineage = dict(preview.lineage_summary)
    grounding_summary = dict(preview.grounding_summary)
    source_support_summary = dict(preview.source_support_summary)
    claim_summary = dict(preview.claim_classification_summary)
    blockers = _source_grounded_outline_blockers(preview, semantic_blockers)
    ready = bool(preview.ready and semantic_status == SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE and not semantic_blockers)
    parent_letter_id = str(lineage.get("letter_id") or request.letter_id)
    handoff_id = str(lineage.get("handoff_id") or source_grounding.get("handoff_id") or "")
    existing_child = _source_grounded_existing_child_context(
        project_id=request.project_id,
        parent_letter_id=parent_letter_id,
        preview_id=str(preview.preview_id or ""),
        handoff_id=handoff_id,
        preview_intent_ref=request.preview_intent_ref,
    )
    governed_context = {
        "proposal_id": str(semantic_context.get("proposal_id") or source_grounding.get("proposal_id") or lineage.get("proposal_id") or ""),
        "canonical_node_id": str(semantic_context.get("canonical_node_id") or source_grounding.get("canonical_node_id") or lineage.get("canonical_node_id") or ""),
        "governed_handoff_id": handoff_id,
        "thesis_or_claim": str(semantic_context.get("thesis_or_claim") or source_grounding.get("thesis_or_claim") or ""),
        "reason_now": str(semantic_context.get("reason_now") or source_grounding.get("reason_now") or ""),
        "destination_brand_ref": str(semantic_context.get("destination_brand_ref") or source_grounding.get("destination_brand_ref") or ""),
        "destination_surface_ref": str(semantic_context.get("destination_surface_ref") or source_grounding.get("destination_surface_ref") or ""),
        "source_snapshot_ref": str(semantic_context.get("source_snapshot_ref") or source_grounding.get("source_snapshot_ref") or ""),
        "content_job": str(semantic_context.get("content_job") or source_grounding.get("content_job") or ""),
        "horizon_class": str(semantic_context.get("horizon_class") or source_grounding.get("horizon_class") or ""),
    }
    outline_sections = [_source_grounded_outline_item_payload(item) for item in preview.outline_items]
    claim_classifications = list(
        claim_summary.get("classifications")
        or source_grounding.get("governed_claim_classifications")
        or ()
    )
    provenance_limitations = list(
        source_support_summary.get("provenance_limitations")
        or source_grounding.get("provenance_limitations")
        or ()
    )
    payload = {
        "ok": True,
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "preview_id": str(preview.preview_id or ""),
        "drafting_mode": OUTLINE_FROM_GOVERNED_BRIEF_MODE,
        "preview_intent_ref": request.preview_intent_ref,
        "semantic_resolution_status": semantic_status,
        "blockers": blockers,
        "parent_letter": _source_grounded_letter_identity(parent_letter_id),
        "governed_context": governed_context,
        "proposal_id": governed_context["proposal_id"],
        "canonical_node_id": governed_context["canonical_node_id"],
        "thesis_or_claim": governed_context["thesis_or_claim"],
        "reason_now": governed_context["reason_now"],
        "destination_brand_ref": governed_context["destination_brand_ref"],
        "destination_surface_ref": governed_context["destination_surface_ref"],
        "source_snapshot_ref": governed_context["source_snapshot_ref"],
        "grounding_summary": grounding_summary,
        "selected_source_asset_count": int(grounding_summary.get("selected_source_asset_count") or 0),
        "selected_passage_count": int(grounding_summary.get("selected_passage_count") or 0),
        "selected_source_passage_refs": list(source_grounding.get("selected_passage_refs") or ()),
        "source_support_summary": {
            "source_snapshot_ref": str(source_support_summary.get("source_snapshot_ref") or governed_context["source_snapshot_ref"]),
            "source_support_ref_count": int(source_support_summary.get("source_support_ref_count") or 0),
        },
        "claim_classifications": claim_classifications,
        "claim_classification_summary": claim_summary,
        "provenance_limitations": provenance_limitations,
        "outline_sections": outline_sections,
        "outline_items": outline_sections,
        "existing_child": existing_child,
        "authority": dict(preview.authority),
    }
    return payload


def _source_grounded_outline_acceptance_payload(result: Any, *, status: str) -> Dict[str, Any]:
    child = _source_grounded_letter_identity(result.child_letter_id)
    parent = _source_grounded_letter_identity(result.parent_letter_id)
    return {
        "ok": True,
        "status": status,
        "result_status": result.status,
        "acceptance_id": result.acceptance_id,
        "preview_id": result.preview_id,
        "parent_letter_id": result.parent_letter_id,
        "parent_letter": parent,
        "child_letter_id": result.child_letter_id,
        "child_letter": {
            "letter_id": child.get("letter_id", ""),
            "title": child.get("title", ""),
            "lifecycle_state": child.get("lifecycle_state", ""),
            "available": child.get("available", False),
            "open_url": f"/?letter_id={result.child_letter_id}",
        },
        "open_url": f"/?letter_id={result.child_letter_id}",
        "authority": {
            "approval": False,
            "package_readiness": False,
            "release_eligibility": False,
            "schedule": False,
            "export": False,
            "publication": False,
            "queue": False,
            "platform_action": False,
            "oauth": False,
            "governed_publishing_ledger_write": False,
        },
    }


def _source_grounded_prose_passage_ref(passage: Mapping[str, Any]) -> str:
    passage_id = str(passage.get("passage_id") or "").strip()
    if passage_id:
        return passage_id
    asset_id = str(passage.get("asset_id") or passage.get("source_asset_id") or "").strip()
    index = str(passage.get("passage_index") or "").strip()
    if asset_id:
        return f"{asset_id}:passage:{index or 'selected'}"
    return ""


def _source_grounded_prose_accepted_plan_from_letter(letter: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
    drafting = metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY)
    if not isinstance(drafting, Mapping):
        return {}
    accepted_plan = drafting.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    return dict(accepted_plan) if isinstance(accepted_plan, Mapping) else {}


def _source_grounded_prose_accepted_passages_by_ref(accepted_plan: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    passages: Dict[str, Mapping[str, Any]] = {}
    for passage in accepted_plan.get("selected_passages") or ():
        if not isinstance(passage, Mapping):
            continue
        ref = _source_grounded_prose_passage_ref(passage)
        if ref:
            passages[ref] = passage
    return passages


def _source_grounded_prose_selected_passage_refs(
    body: Dict[str, Any],
    selected_passages: tuple[Dict[str, Any], ...],
) -> tuple[str, ...]:
    explicit = _source_grounded_outline_refs(body.get("selected_source_passage_refs"))
    if explicit:
        return explicit
    refs: list[str] = []
    for passage in selected_passages:
        ref = _source_grounded_prose_passage_ref(passage)
        if ref and ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _source_grounded_prose_selected_asset_refs(
    body: Dict[str, Any],
    selected_passages: tuple[Dict[str, Any], ...],
    accepted_plan: Mapping[str, Any],
    selected_passage_refs: tuple[str, ...],
) -> tuple[str, ...]:
    explicit = _source_grounded_outline_refs(body.get("selected_source_asset_ids"))
    if explicit:
        return explicit
    asset_ids: list[str] = []
    for passage in selected_passages:
        asset_id = str(passage.get("asset_id") or passage.get("source_asset_id") or "").strip()
        if asset_id and asset_id not in asset_ids:
            asset_ids.append(asset_id)
    if asset_ids:
        return tuple(asset_ids)
    accepted_by_ref = _source_grounded_prose_accepted_passages_by_ref(accepted_plan)
    for ref in selected_passage_refs:
        passage = accepted_by_ref.get(ref)
        if not passage:
            continue
        asset_id = str(passage.get("asset_id") or passage.get("source_asset_id") or "").strip()
        if asset_id and asset_id not in asset_ids:
            asset_ids.append(asset_id)
    if asset_ids:
        return tuple(asset_ids)
    return _source_grounded_outline_refs(accepted_plan.get("selected_source_asset_ids"))


def _source_grounded_prose_candidate_request(
    *,
    project_id: str,
    body: Dict[str, Any],
) -> SourceGroundedProseCandidateRequest:
    accepted_scaffold_letter_id = str(
        body.get("accepted_scaffold_letter_id") or body.get("child_letter_id") or ""
    ).strip()
    if not accepted_scaffold_letter_id:
        raise ValueError("accepted_scaffold_letter_id is required")
    accepted_outline_section_id = str(
        body.get("accepted_outline_section_id") or body.get("selected_outline_section_id") or ""
    ).strip()
    if not accepted_outline_section_id:
        raise ValueError("accepted_outline_section_id is required")
    candidate_intent_ref = str(body.get("candidate_intent_ref") or "").strip()
    if not candidate_intent_ref:
        raise ValueError("candidate_intent_ref is required")
    requested_length_or_format = str(body.get("requested_length_or_format") or "").strip()
    if not requested_length_or_format:
        raise ValueError("requested_length_or_format is required")

    _read_project_without_mutation(project_id)
    letter = _read_json(_letter_dir(accepted_scaffold_letter_id) / "letter.json")
    if not letter:
        raise FileNotFoundError(f"Accepted scaffold Letter not found: {accepted_scaffold_letter_id}")
    accepted_plan = _source_grounded_prose_accepted_plan_from_letter(letter)
    accepted_preview_id = str(accepted_plan.get("accepted_preview_id") or "").strip()
    if not accepted_preview_id:
        raise ValueError("accepted_outline_metadata_required")

    selected_passages = _source_grounded_outline_selected_passages(body)
    selected_passage_refs = _source_grounded_prose_selected_passage_refs(body, selected_passages)
    selected_asset_refs = _source_grounded_prose_selected_asset_refs(
        body,
        selected_passages,
        accepted_plan,
        selected_passage_refs,
    )
    return SourceGroundedProseCandidateRequest(
        project_id=project_id,
        child_letter_id=accepted_scaffold_letter_id,
        accepted_preview_id=accepted_preview_id,
        accepted_outline_section_id=accepted_outline_section_id,
        selected_source_asset_refs=selected_asset_refs,
        selected_source_passage_refs=selected_passage_refs,
        candidate_intent_ref=candidate_intent_ref,
        requested_length_or_format=requested_length_or_format,
        writer_instruction=str(body.get("writer_instruction") or "").strip(),
        operator_ref=str(body.get("actor_ref") or body.get("operator_ref") or "operator.local").strip() or "operator.local",
    )


def _resolve_source_grounded_prose_provider() -> tuple[Any, Any, Any]:
    try:
        context = resolve_manual_generation_context()
    except StructuredGenerationError as exc:
        raise SourceGroundedProseProviderAuthorizationError("structured_generation_provider_not_authorized") from exc
    return context.generator, context.authorization, context.budget_policy


def _source_grounded_candidate_signer() -> CandidateEnvelopeSigner:
    key_material = os.environ.get(SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY_ENV, "").strip()
    if not key_material:
        raise SourceGroundedProseProviderAuthorizationError("candidate_envelope_signing_key_not_configured")
    signer_id = (
        os.environ.get(SOURCE_GROUNDED_CANDIDATE_SIGNER_ID_ENV, "").strip()
        or SOURCE_GROUNDED_CANDIDATE_DEFAULT_SIGNER_ID
    )
    return CandidateEnvelopeSigner(key_material=key_material, signer_id=signer_id)


def _source_grounded_candidate_verifier() -> CandidateEnvelopeVerifier:
    key_material = os.environ.get(SOURCE_GROUNDED_CANDIDATE_SIGNING_KEY_ENV, "").strip()
    if not key_material:
        raise SourceGroundedProseProviderAuthorizationError("candidate_envelope_signing_key_not_configured")
    signer_id = (
        os.environ.get(SOURCE_GROUNDED_CANDIDATE_SIGNER_ID_ENV, "").strip()
        or SOURCE_GROUNDED_CANDIDATE_DEFAULT_SIGNER_ID
    )
    return CandidateEnvelopeVerifier(key_material=key_material, signer_id=signer_id)


def _source_grounded_candidate_expiration(*, issued_at: datetime | None = None) -> str:
    raw_ttl = os.environ.get(SOURCE_GROUNDED_CANDIDATE_ENVELOPE_TTL_SECONDS_ENV, "").strip()
    if raw_ttl:
        try:
            ttl_seconds = int(raw_ttl)
        except ValueError as exc:
            raise SourceGroundedProseProviderAuthorizationError("candidate_envelope_ttl_invalid") from exc
    else:
        ttl_seconds = SOURCE_GROUNDED_CANDIDATE_DEFAULT_TTL_SECONDS
    if ttl_seconds < 1:
        raise SourceGroundedProseProviderAuthorizationError("candidate_envelope_ttl_invalid")
    moment = issued_at or datetime.now(timezone.utc)
    return (moment + timedelta(seconds=ttl_seconds)).isoformat()


def _source_grounded_prose_candidate_payload(
    result: Any,
    *,
    envelope: SourceGroundedCandidateEnvelope | None = None,
    expires_at: str = "",
) -> Dict[str, Any]:
    result_payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    payload: Dict[str, Any] = {
        "ok": result_payload.get("status") == SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_GENERATED,
        "status": str(result_payload.get("status") or ""),
        "candidate_request_identity": str(result_payload.get("candidate_request_identity") or ""),
        "candidate_result_id": str(result_payload.get("candidate_result_id") or ""),
        "candidate_text": str(result_payload.get("candidate_text") or ""),
        "outline_section_target": dict(result_payload.get("outline_section_target") or {}),
        "immutable_lineage_summary": dict(result_payload.get("immutable_lineage_summary") or {}),
        "selected_grounding_summary": dict(result_payload.get("selected_grounding_summary") or {}),
        "segment_annotations": list(result_payload.get("segment_annotations") or ()),
        "used_source_refs": list(result_payload.get("used_source_refs") or ()),
        "used_passage_refs": list(result_payload.get("used_passage_refs") or ()),
        "warnings": list(result_payload.get("warnings") or ()),
        "blockers": list(result_payload.get("blockers") or ()),
        "provenance_limitations": list(result_payload.get("provenance_limitations") or ()),
        "bounded_context": dict(result_payload.get("bounded_context") or {}),
        "provider_metadata": dict(result_payload.get("provider_metadata") or {}),
        "authority": dict(result_payload.get("authority") or {}),
        "direct_quotations_supported": False,
    }
    if envelope is not None:
        payload["candidate_envelope"] = envelope.to_dict()
        payload["candidate_envelope_id"] = source_grounded_candidate_envelope_id(envelope)
        payload["expires_at"] = expires_at or str(envelope.payload.get("expires_at") or "")
    return payload


def _source_grounded_prose_apply_request(
    *,
    project_id: str,
    body: Dict[str, Any],
) -> SourceGroundedProseCandidateApplyRequest:
    accepted_scaffold_letter_id = str(body.get("accepted_scaffold_letter_id") or "").strip()
    if not accepted_scaffold_letter_id:
        raise ValueError("accepted_scaffold_letter_id is required")
    envelope_value = body.get("candidate_envelope")
    if not isinstance(envelope_value, Mapping):
        raise ValueError("candidate_envelope is required")
    envelope = SourceGroundedCandidateEnvelope.model_validate(envelope_value)
    expected_hash = str(
        body.get("expected_scaffold_body_hash")
        or envelope.payload.get("accepted_scaffold_body_hash")
        or ""
    ).strip()
    if not expected_hash:
        raise ValueError("expected_scaffold_body_hash is required")
    return SourceGroundedProseCandidateApplyRequest(
        project_id=project_id,
        accepted_scaffold_letter_id=accepted_scaffold_letter_id,
        candidate_envelope=envelope,
        expected_scaffold_body_hash=expected_hash,
        apply_intent_ref=str(body.get("apply_intent_ref") or "").strip(),
        operator_ref=str(body.get("actor_ref") or body.get("operator_ref") or "operator.local").strip() or "operator.local",
        operator_note=str(body.get("operator_note") or "").strip(),
    )


def _source_grounded_prose_apply_payload(result: Any, *, status: str) -> Dict[str, Any]:
    child = _source_grounded_letter_identity(result.child_letter_id)
    parent = _source_grounded_letter_identity(result.parent_scaffold_letter_id)
    return {
        "ok": True,
        "status": status,
        "result_status": result.status,
        "project_id": result.project_id,
        "apply_id": result.apply_id,
        "parent_scaffold_letter_id": result.parent_scaffold_letter_id,
        "parent_scaffold_letter": parent,
        "child_letter_id": result.child_letter_id,
        "child_letter": {
            "letter_id": child.get("letter_id", ""),
            "title": child.get("title", ""),
            "lifecycle_state": child.get("lifecycle_state", ""),
            "available": child.get("available", False),
            "open_url": f"/?letter_id={result.child_letter_id}",
        },
        "open_url": f"/?letter_id={result.child_letter_id}",
        "candidate_request_identity": result.candidate_request_identity,
        "candidate_result_id": result.candidate_result_id,
        "candidate_text_hash": result.candidate_text_hash,
        "authority": {
            "approval": False,
            "package_readiness": False,
            "release_eligibility": False,
            "schedule": False,
            "export": False,
            "publication": False,
            "queue": False,
            "platform_action": False,
            "oauth": False,
            "governed_publishing_ledger_write": False,
        },
    }


def _promotion_required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _production_derivative_promotion_request(
    *,
    project_id: str,
    source_letter_id: str,
    body: Dict[str, Any],
    target_theme: Any = None,
) -> GovernedDraftPromotionRequest:
    return GovernedDraftPromotionRequest(
        source_letter_id=_promotion_required_text(source_letter_id, "source_letter_id"),
        expected_source_body_hash=_promotion_required_text(
            body.get("expected_source_body_hash"),
            "expected_source_body_hash",
        ),
        promotion_intent_ref=_promotion_required_text(
            body.get("promotion_intent_ref"),
            "promotion_intent_ref",
        ),
        destination_project_id=_promotion_required_text(project_id, "project_id"),
        destination_brand_id=_promotion_required_text(
            body.get("destination_brand_id"),
            "destination_brand_id",
        ),
        operator_ref=_promotion_required_text(body.get("operator_ref"), "operator_ref"),
        target_theme=str(target_theme if target_theme is not None else body.get("target_theme") or "").strip() or None,
        operator_note=str(body.get("operator_note") or "").strip() or None,
    )


def _promotion_envelope_key_material() -> bytes:
    key_material = os.environ.get(GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_SIGNING_KEY_ENV, "").strip()
    if not key_material:
        raise GovernedProductionDerivativePromotionEnvelopeAuthorizationError(
            "production_derivative_promotion_envelope_signing_key_not_configured"
        )
    return key_material.encode("utf-8")


def _promotion_envelope_expiration(*, issued_at: datetime | None = None) -> str:
    raw_ttl = os.environ.get(
        GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_TTL_SECONDS_ENV,
        "",
    ).strip()
    if raw_ttl:
        try:
            ttl_seconds = int(raw_ttl)
        except ValueError as exc:
            raise GovernedProductionDerivativePromotionEnvelopeAuthorizationError(
                "production_derivative_promotion_envelope_ttl_invalid"
            ) from exc
    else:
        ttl_seconds = GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_DEFAULT_TTL_SECONDS
    if ttl_seconds < 1:
        raise GovernedProductionDerivativePromotionEnvelopeAuthorizationError(
            "production_derivative_promotion_envelope_ttl_invalid"
        )
    moment = issued_at or datetime.now(timezone.utc)
    return (moment + timedelta(seconds=ttl_seconds)).isoformat()


def _promotion_canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _promotion_envelope_signature(key_material: bytes, material: Mapping[str, Any]) -> str:
    digest = hmac.new(
        key_material,
        _promotion_canonical_json(material).encode("utf-8"),
        sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _seal_production_derivative_promotion_envelope(payload: Mapping[str, Any]) -> Dict[str, Any]:
    material = {
        "envelope_version": GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_VERSION,
        "payload": dict(payload),
        "signer_id": GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_DEFAULT_SIGNER_ID,
        "signature_algorithm": GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_ALGORITHM,
    }
    return {
        **material,
        "signature": _promotion_envelope_signature(_promotion_envelope_key_material(), material),
    }


def _production_derivative_promotion_envelope_id(envelope: Mapping[str, Any]) -> str:
    return "governed_production_derivative_promotion_envelope." + sha256(
        _promotion_canonical_json(envelope).encode("utf-8")
    ).hexdigest()[:16]


def _parse_promotion_envelope_time(value: Any, label: str) -> datetime:
    text = _promotion_required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GovernedProductionDerivativePromotionEnvelopeError(f"{label}_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _verify_production_derivative_promotion_envelope(
    envelope: Any,
    *,
    now: datetime | None = None,
) -> Dict[str, Any]:
    if not isinstance(envelope, Mapping):
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_required"
        )
    sealed = dict(envelope)
    payload = sealed.get("payload")
    if not isinstance(payload, Mapping):
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_payload_required"
        )
    material = {
        "envelope_version": str(sealed.get("envelope_version") or ""),
        "payload": dict(payload),
        "signer_id": str(sealed.get("signer_id") or ""),
        "signature_algorithm": str(sealed.get("signature_algorithm") or ""),
    }
    if material["envelope_version"] != GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_VERSION:
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_version_unsupported"
        )
    if material["signature_algorithm"] != GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_ENVELOPE_ALGORITHM:
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_signature_algorithm_mismatch"
        )
    if material["signer_id"] != GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_DEFAULT_SIGNER_ID:
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_signer_mismatch"
        )
    expected = _promotion_envelope_signature(_promotion_envelope_key_material(), material)
    if not hmac.compare_digest(expected, str(sealed.get("signature") or "")):
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_signature_invalid"
        )

    verified = dict(payload)
    if str(verified.get("payload_version") or "") != GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_PAYLOAD_VERSION:
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_payload_version_unsupported"
        )
    for field in (
        "project_id",
        "destination_project_id",
        "source_letter_id",
        "source_body_hash",
        "destination_brand_id",
        "operator_ref",
        "promotion_intent_ref",
        "promotion_id",
        "target_letter_id",
        "issued_at",
        "expires_at",
    ):
        _promotion_required_text(verified.get(field), field)
    expires_at = _parse_promotion_envelope_time(verified.get("expires_at"), "expires_at")
    check_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if check_time > expires_at:
        raise GovernedProductionDerivativePromotionEnvelopeError(
            "production_derivative_promotion_candidate_envelope_expired"
        )
    return verified


def _production_derivative_candidate_envelope_payload(
    *,
    candidate: Any,
    request: GovernedDraftPromotionRequest,
    issued_at: str,
    expires_at: str,
) -> Dict[str, Any]:
    return {
        "payload_version": GOVERNED_PRODUCTION_DERIVATIVE_PROMOTION_PAYLOAD_VERSION,
        "project_id": request.destination_project_id,
        "destination_project_id": request.destination_project_id,
        "source_letter_id": candidate.source_letter_id,
        "source_body_hash": candidate.source_body_hash,
        "destination_brand_id": candidate.destination_brand_id,
        "operator_ref": candidate.operator_ref,
        "promotion_intent_ref": candidate.promotion_intent_ref,
        "promotion_id": candidate.promotion_id,
        "target_letter_id": candidate.target_letter_id,
        "target_theme": request.target_theme or "",
        "lineage_summary": dict(candidate.lineage_summary),
        "authority_notice": GOVERNED_PRODUCTION_DERIVATIVE_AUTHORITY_NOTICE,
        "authority": {
            "approval": False,
            "package_readiness": False,
            "release_eligibility": False,
            "schedule": False,
            "export": False,
            "publication": False,
            "queue": False,
            "platform_action": False,
            "oauth": False,
        },
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def _production_derivative_candidate_payload(
    candidate: Any,
    *,
    envelope: Mapping[str, Any] | None = None,
    expires_at: str = "",
) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "validation_state": candidate.validation_state,
        "promotion_id": candidate.promotion_id,
        "target_letter_id": candidate.target_letter_id,
        "source_letter_id": candidate.source_letter_id,
        "source_body_hash": candidate.source_body_hash,
        "destination_project_id": candidate.destination_project_id,
        "destination_brand_id": candidate.destination_brand_id,
        "lineage_summary": dict(candidate.lineage_summary),
        "warnings": list(candidate.warnings),
        "blockers": list(candidate.blockers),
        "authority_notice": GOVERNED_PRODUCTION_DERIVATIVE_AUTHORITY_NOTICE,
    }
    if envelope is not None:
        payload["candidate_envelope"] = dict(envelope)
        payload["candidate_envelope_id"] = _production_derivative_promotion_envelope_id(envelope)
        payload["expires_at"] = expires_at or str(dict(envelope).get("payload", {}).get("expires_at") or "")
    return payload


def _production_derivative_blocked_candidate_payload(error: Exception) -> Dict[str, Any]:
    code = str(error) or error.__class__.__name__
    return {
        "ok": False,
        "validation_state": "blocked",
        "promotion_id": "",
        "target_letter_id": "",
        "source_body_hash": "",
        "lineage_summary": {},
        "warnings": [],
        "blockers": [{"code": code, "message": code}],
        "authority_notice": GOVERNED_PRODUCTION_DERIVATIVE_AUTHORITY_NOTICE,
    }


def _production_derivative_apply_payload(result: Any, *, status: str) -> Dict[str, Any]:
    target = _read_json(_letter_dir(result.target_letter_id) / "letter.json")
    target_state = str(target.get("lifecycle_state") or "")
    if not target_state and result.job_id:
        job = get_creation_job(result.job_id)
        target_state = str((job or {}).get("status") or "creation_job_started")
    return {
        "ok": True,
        "status": status,
        "result_status": result.status,
        "promotion_id": result.promotion_id,
        "source_letter_id": result.source_letter_id,
        "target_letter_id": result.target_letter_id,
        "creation_job_id": result.job_id,
        "job_id": result.job_id,
        "validation_state": "already_promoted" if result.status == "already_promoted" else "applied",
        "source_body_hash": str(result.promotion_receipt.get("source_body_hash") or ""),
        "target_lifecycle_state": target_state,
        "authority_notice": GOVERNED_PRODUCTION_DERIVATIVE_AUTHORITY_NOTICE,
    }


def _read_project_without_mutation(project_id: str) -> Dict[str, Any]:
    project = _read_json(project_dir(project_id) / "project.json")
    if project.get("project_id") != project_id:
        raise FileNotFoundError(f"Project not found: {project_id}")
    return project


def _governed_query_value(query: Dict[str, List[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0] if values else "").strip()


def _governed_draft_context_payload(
    *,
    project_id: str,
    proposal_id: str,
    draft_intent_ref: str,
) -> Dict[str, Any]:
    project = _read_project_without_mutation(project_id)
    ledger = _governed_publishing_ledger()
    projection = replay_governed_publishing_events(ledger.read_events())
    proposal = projection.horizon_proposals.get(proposal_id)
    readiness = derive_governed_drafting_brief(
        projection,
        proposal_id,
        draft_intent_ref=draft_intent_ref,
        source_grounding_references=_source_grounding_references_for_proposal(proposal),
    )
    handoff_id = project_studio_draft_handoff_identity(
        proposal_id=proposal_id,
        draft_intent_ref=draft_intent_ref,
    )
    linked_letter = _governed_linked_letter_context(project, handoff_id)
    context = _proposal_context_fields(proposal)
    context.update(
        {
            "ok": True,
            "status": "ready" if readiness.ready else "blocked",
            "proposal_id": proposal_id,
            "draft_intent_ref": draft_intent_ref,
            "governed_brief_ready": bool(readiness.ready),
            "readiness_state": "ready" if readiness.ready else "blocked",
            "blockers": _blockers_payload(readiness),
            "project_studio_handoff_id": handoff_id,
            "linked_project_studio_letter_exists": bool(linked_letter.get("exists")),
            "linked_letter": linked_letter,
        }
    )
    return context


def _governed_draft_proposals_payload(
    *,
    project_id: str,
    query: Dict[str, List[str]],
) -> Dict[str, Any]:
    _reject_governed_discovery_client_authority_fields(query)
    project = _read_project_without_mutation(project_id)
    filters = _governed_discovery_filters(project, query)
    ledger = _governed_publishing_ledger()
    projection = replay_governed_publishing_events(ledger.read_events())
    actionable: list[Dict[str, Any]] = []
    needs_attention: list[Dict[str, Any]] = []

    for proposal in sorted(projection.horizon_proposals.values(), key=lambda item: item.proposal_id):
        if proposal.status != "promoted_to_draft_candidate":
            continue
        summary = _governed_discovery_summary(
            project=project,
            projection=projection,
            proposal=proposal,
            draft_intent_ref=filters["draft_intent_ref"],
        )
        if not _governed_discovery_matches_filters(summary, filters):
            continue
        if summary["actionable"]:
            actionable.append(summary)
        else:
            needs_attention.append(summary)

    return {
        "ok": True,
        "status": "ready",
        "project_id": project_id,
        "advisory_only": True,
        "check_proposal_required": True,
        "open_governed_draft_required": True,
        "filters": filters,
        "counts": {
            "actionable": len(actionable),
            "needs_attention": len(needs_attention),
        },
        "actionable": actionable,
        "needs_attention": needs_attention,
    }


def _governed_discovery_filters(project: Dict[str, Any], query: Dict[str, List[str]]) -> Dict[str, str]:
    linked_state = _governed_query_value(query, "linked_state") or "any"
    if linked_state not in GOVERNED_DRAFT_DISCOVERY_LINKED_STATES:
        raise ValueError(f"linked_state_not_allowed:{linked_state}")
    return {
        "destination_brand_ref": _governed_query_value(query, "destination_brand_ref"),
        "destination_surface_ref": _governed_query_value(query, "destination_surface_ref"),
        "content_job": _governed_query_value(query, "content_job"),
        "horizon_class": _governed_query_value(query, "horizon_class"),
        "linked_state": linked_state,
        "proposal_id": _governed_query_value(query, "proposal_id"),
        "q": _governed_query_value(query, "q"),
        "draft_intent_ref": _governed_query_value(query, "draft_intent_ref"),
        "project_brand_ref": str(project.get("brand_id") or "").strip(),
    }


def _governed_discovery_summary(
    *,
    project: Dict[str, Any],
    projection: Any,
    proposal: Any,
    draft_intent_ref: str,
) -> Dict[str, Any]:
    readiness = derive_governed_drafting_brief(
        projection,
        proposal.proposal_id,
        draft_intent_ref=draft_intent_ref or proposal.promotion_ref,
        source_grounding_references=_source_grounding_references_for_proposal(proposal),
    )
    linked_letter = _governed_discovery_linked_letter_context(
        project,
        proposal_id=proposal.proposal_id,
        draft_intent_ref=draft_intent_ref,
    )
    blockers = _governed_discovery_blockers(
        project=project,
        projection=projection,
        proposal=proposal,
        readiness=readiness,
        linked_letter=linked_letter,
    )
    actionable = bool(readiness.ready and not blockers)
    summary: Dict[str, Any] = {
        "proposal_id": proposal.proposal_id,
        "canonical_node_id": proposal.source_node_id,
        "content_job": proposal.content_job.value,
        "horizon_class": proposal.horizon_class,
        "origin_brand_ref": proposal.origin_brand_id,
        "destination_brand_ref": proposal.brand_id,
        "destination_surface_ref": proposal.platform,
        "thesis_or_claim": proposal.thesis_or_claim,
        "reason_now": proposal.reason_now,
        "source_support_reference_count": len(proposal.source_support),
        "source_snapshot_ref": proposal.source_snapshot_ref,
        "review_outcome": proposal.review_outcome,
        "promotion_state": proposal.status,
        "actionable": actionable,
        "blockers": blockers,
        "status_label": _governed_discovery_status_label(actionable, linked_letter, blockers),
    }
    if draft_intent_ref:
        summary["linked_letter"] = linked_letter
        summary["linked_project_studio_letter_exists"] = bool(linked_letter.get("exists"))
    return summary


def _governed_discovery_blockers(
    *,
    project: Dict[str, Any],
    projection: Any,
    proposal: Any,
    readiness: Any,
    linked_letter: Dict[str, Any],
) -> List[Dict[str, str]]:
    blockers: list[Dict[str, str]] = []
    project_brand = str(project.get("brand_id") or "").strip()
    if proposal.source_node_id not in projection.canonical_nodes:
        blockers.append(_governed_discovery_blocker("missing_canonical_node", "canonical_node_id"))
    if not project_brand:
        blockers.append(_governed_discovery_blocker("project_brand_missing", "project.brand_id"))
    elif proposal.brand_id and proposal.brand_id != project_brand:
        blockers.append(
            _governed_discovery_blocker(
                "incompatible_project_brand",
                "destination_brand_ref",
                f"Project brand {project_brand} does not match governed destination brand {proposal.brand_id}.",
            )
        )
    if not readiness.ready:
        blockers.append(_governed_discovery_blocker("draft_brief_blocked", "drafting_brief"))
    for blocker in getattr(readiness, "blockers", ()):
        code = GOVERNED_DRAFT_DISCOVERY_BLOCKER_MAP.get(
            str(getattr(blocker, "code", "") or ""),
            str(getattr(blocker, "code", "") or "draft_brief_blocked"),
        )
        field = str(getattr(blocker, "field", "") or "")
        if not any(item["code"] == code and item.get("field", "") == field for item in blockers):
            blockers.append(_governed_discovery_blocker(code, field))
    if linked_letter.get("exists") and not linked_letter.get("available"):
        blockers.append(_governed_discovery_blocker("linked_draft_unavailable", "linked_letter"))
    return blockers


def _governed_discovery_blocker(code: str, field: str = "", message: str = "") -> Dict[str, str]:
    payload = {"code": code, "field": field}
    if message:
        payload["message"] = message
    return payload


def _governed_discovery_status_label(
    actionable: bool,
    linked_letter: Dict[str, Any],
    blockers: List[Dict[str, str]],
) -> str:
    if linked_letter.get("exists") and linked_letter.get("available"):
        return "Linked"
    if linked_letter.get("exists") and not linked_letter.get("available"):
        return "Linked draft unavailable"
    if actionable:
        return "Ready"
    if any(item.get("code") == "incompatible_project_brand" for item in blockers):
        return "Brand mismatch"
    return "Needs attention"


def _governed_discovery_linked_letter_context(
    project: Dict[str, Any],
    *,
    proposal_id: str,
    draft_intent_ref: str,
) -> Dict[str, Any]:
    if draft_intent_ref:
        handoff_id = project_studio_draft_handoff_identity(
            proposal_id=proposal_id,
            draft_intent_ref=draft_intent_ref,
        )
        linked = _governed_linked_letter_context(project, handoff_id)
        if linked.get("exists"):
            linked["draft_intent_ref"] = draft_intent_ref
        return linked

    entries = _governed_handoff_entries_for_proposal(project, proposal_id)
    if not entries:
        return {"exists": False, "available": False, "status": "none"}
    if len(entries) > 1:
        return {
            "exists": True,
            "available": False,
            "status": "draft_intent_required",
            "linked_count": len(entries),
        }
    entry = entries[0]
    entry_handoff_id = str(entry.get("handoff_id") or "").strip()
    entry_draft_intent = str(entry.get("draft_intent_ref") or "").strip()
    if not entry_handoff_id and entry_draft_intent:
        entry_handoff_id = project_studio_draft_handoff_identity(
            proposal_id=proposal_id,
            draft_intent_ref=entry_draft_intent,
        )
    if not entry_handoff_id:
        return {
            "exists": True,
            "available": False,
            "status": "linked_draft_unavailable",
        }
    linked = _governed_linked_letter_context(project, entry_handoff_id)
    if linked.get("exists") and entry_draft_intent:
        linked["draft_intent_ref"] = entry_draft_intent
    return linked


def _governed_handoff_entries_for_proposal(project: Dict[str, Any], proposal_id: str) -> List[Dict[str, Any]]:
    index = project.get("governed_handoffs")
    if not isinstance(index, dict):
        return []
    return [
        dict(entry)
        for entry in index.values()
        if isinstance(entry, dict) and str(entry.get("proposal_id") or "") == proposal_id
    ]


def _governed_discovery_matches_filters(summary: Dict[str, Any], filters: Dict[str, str]) -> bool:
    for field in ("destination_brand_ref", "destination_surface_ref", "content_job", "horizon_class"):
        value = filters.get(field, "")
        if value and str(summary.get(field) or "") != value:
            return False
    proposal_filter = filters.get("proposal_id", "").lower()
    if proposal_filter and proposal_filter not in str(summary.get("proposal_id") or "").lower():
        return False
    text_query = filters.get("q", "").lower()
    if text_query and text_query not in str(summary.get("thesis_or_claim") or "").lower():
        return False
    linked_state = filters.get("linked_state", "any")
    linked = summary.get("linked_letter") if isinstance(summary.get("linked_letter"), dict) else {}
    if linked_state == "linked" and not (linked.get("exists") and linked.get("available")):
        return False
    if linked_state == "unlinked" and linked.get("exists"):
        return False
    if linked_state == "unavailable" and not (linked.get("exists") and not linked.get("available")):
        return False
    return True


def _proposal_context_fields(proposal: Any) -> Dict[str, Any]:
    if proposal is None:
        return {
            "canonical_node_id": "",
            "content_job": "",
            "origin_brand_ref": "",
            "destination_brand_ref": "",
            "destination_surface_ref": "",
            "horizon_class": "",
            "thesis_or_claim": "",
            "reason_now": "",
            "source_support_reference_count": 0,
            "source_snapshot_ref": "",
            "promotion_state": "missing",
            "review_outcome": "",
        }
    return {
        "canonical_node_id": proposal.source_node_id,
        "content_job": proposal.content_job.value,
        "origin_brand_ref": proposal.origin_brand_id,
        "destination_brand_ref": proposal.brand_id,
        "destination_surface_ref": proposal.platform,
        "horizon_class": proposal.horizon_class,
        "thesis_or_claim": proposal.thesis_or_claim,
        "reason_now": proposal.reason_now,
        "source_support_reference_count": len(proposal.source_support),
        "source_snapshot_ref": proposal.source_snapshot_ref,
        "promotion_state": proposal.status,
        "review_outcome": proposal.review_outcome,
    }


def _governed_linked_letter_context(project: Dict[str, Any], handoff_id: str) -> Dict[str, Any]:
    entry = {}
    index = project.get("governed_handoffs")
    if isinstance(index, dict):
        candidate = index.get(handoff_id)
        if isinstance(candidate, dict):
            entry = candidate
    letter_id = str(entry.get("letter_id") or "").strip()
    if not letter_id:
        letter_id = _find_letter_id_by_governed_handoff(handoff_id)
    if not letter_id:
        return {"exists": False, "available": False, "status": "none"}
    letter = _read_json(_letter_dir(letter_id) / "letter.json")
    if not letter:
        return {
            "exists": True,
            "available": False,
            "status": "linked_draft_unavailable",
            "letter_id": letter_id,
        }
    metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
    lifecycle_state = str(letter.get("lifecycle_state") or metadata.get("lifecycle_state") or "").strip()
    metadata_state = str(metadata.get("status") or "").strip().lower()
    if lifecycle_state.lower() in {"archived", "deleted"} or metadata_state in {"archived", "deleted"}:
        return {
            "exists": True,
            "available": False,
            "status": "linked_draft_unavailable",
            "letter_id": letter_id,
            "title": str(letter.get("title") or ""),
            "lifecycle_state": lifecycle_state,
        }
    return {
        "exists": True,
        "available": True,
        "status": "available",
        "letter_id": letter_id,
        "title": str(letter.get("title") or ""),
        "lifecycle_state": lifecycle_state,
    }


def _find_letter_id_by_governed_handoff(handoff_id: str) -> str:
    letters_root = _get_root() / "data" / "state" / "letters_of_light"
    if not letters_root.exists():
        return ""
    for child in letters_root.iterdir():
        if not child.is_dir():
            continue
        letter = _read_json(child / "letter.json")
        metadata = letter.get("metadata") if isinstance(letter.get("metadata"), dict) else {}
        handoff = metadata.get("governed_handoff") if isinstance(metadata, dict) else {}
        if isinstance(handoff, dict) and str(handoff.get("handoff_id") or "") == handoff_id:
            return str(letter.get("letter_id") or child.name)
    return ""


def _read_release(letter_id: str) -> Dict[str, Any]:
    return _read_json(_letter_dir(letter_id) / "release.json")


def _export_dir_for(letter_id: str) -> Path:
    return _letter_dir(letter_id) / "release_export"


def _public_release_log_for(letter_id: str) -> Dict[str, Any]:
    return _read_json(_letter_dir(letter_id) / "public_release_log.json")


def _folder_uri(path: Path) -> str:
    try:
        return path.resolve().as_uri()
    except ValueError:
        return ""


def _file_uri(path_value: Any) -> str:
    if not path_value:
        return ""
    try:
        path = _resolve_artifact_path(str(path_value))
        if path.exists() and path.is_file():
            return path.resolve().as_uri()
    except Exception:
        return ""
    return ""


def _env_file_configured(name: str) -> bool:
    value = os.environ.get(name, "").strip()
    if not value:
        return False
    try:
        return Path(value).expanduser().is_file()
    except Exception:
        return False


def _config_payload() -> Dict[str, Any]:
    try:
        resolve_site_root()
        website_available = True
    except Exception:
        website_available = False
    local_transcription = transcription_readiness()

    return {
        "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
        "youtube_oauth_configured": _env_file_configured(YOUTUBE_CLIENT_SECRETS_ENV),
        "website_publisher_available": website_available,
        "local_transcription_available": bool(local_transcription.get("available")),
        "local_transcription": local_transcription,
        "brands": safe_brand_list(),
    }


def _safe_brand_for_letter(letter: Dict[str, Any], release: Dict[str, Any]) -> Dict[str, Any]:
    metadata = letter.get("metadata", {}) if isinstance(letter.get("metadata"), dict) else {}
    brand_id = str(metadata.get("brand_id") or release.get("brand_id") or DEFAULT_BRAND_ID)
    try:
        return safe_brand_metadata(get_brand(brand_id))
    except Exception:
        return safe_brand_metadata(get_brand(DEFAULT_BRAND_ID))


def _letters_payload() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    scanned = scan_letters()
    jobs = list_creation_jobs()
    parent_counts: Dict[str, int] = {}

    for row in scanned:
        letter_id = row.get("letter_id", "")
        letter = _read_json(_letter_dir(letter_id) / "letter.json")
        metadata = letter.get("metadata", {}) if isinstance(letter.get("metadata"), dict) else {}
        parent = str(metadata.get("parent_letter_id") or letter.get("parent_letter_id") or "").strip()
        if parent:
            parent_counts[parent] = parent_counts.get(parent, 0) + 1

    job_by_letter: Dict[str, Dict[str, Any]] = {}
    for job in jobs:
        letter_id = str(job.get("letter_id") or "")
        if letter_id:
            job_by_letter[letter_id] = job

    for row in scanned:
        letter_id = row.get("letter_id", "")
        letter_dir = _letter_dir(letter_id)
        letter = _read_json(letter_dir / "letter.json")
        release = _read_release(letter_id)
        export_dir = _export_dir_for(letter_id)
        export_exists = export_dir.exists() and export_dir.is_dir()

        enriched = dict(row)
        metadata = letter.get("metadata", {}) if isinstance(letter.get("metadata"), dict) else {}
        brand = _safe_brand_for_letter(letter, release)
        targets = release.get("targets", {})
        site = targets.get("site", {}) if isinstance(targets.get("site"), dict) else {}
        youtube = targets.get("youtube", {}) if isinstance(targets.get("youtube"), dict) else {}
        log = _public_release_log_for(letter_id)
        social_urls = log.get("social_urls", {}) if isinstance(log.get("social_urls"), dict) else {}
        job = job_by_letter.get(letter_id, {})
        enriched["approved"] = bool(release.get("approved", False))
        enriched["brand_id"] = brand.get("brand_id")
        enriched["brand_display_name"] = brand.get("display_name")
        enriched["brand_status"] = brand.get("status")
        enriched["brand"] = brand
        enriched["release_disabled_reasons"] = (
            release.get("eligibility", {}).get("reasons", [])
            if isinstance(release.get("eligibility"), dict)
            else row.get("reasons", [])
        )
        enriched["site_enabled"] = bool(site.get("enabled", False))
        enriched["youtube_enabled"] = bool(youtube.get("enabled", False))
        enriched["canonical_url"] = release.get("canonical_url") or site.get("url") or social_urls.get("site")
        enriched["site_status"] = site.get("status")
        enriched["youtube_status"] = youtube.get("status")
        enriched["youtube_url"] = youtube.get("url") or social_urls.get("youtube")
        enriched["youtube_platform_id"] = youtube.get("platform_id") or youtube.get("video_id")
        enriched["youtube_error"] = youtube.get("error")
        enriched["release_log_path"] = str(_letter_dir(letter_id) / "public_release_log.json") if log else ""
        enriched["manual_social_urls"] = social_urls
        enriched["release_export_dir"] = str(export_dir) if export_exists else ""
        enriched["release_export_url"] = _folder_uri(export_dir) if export_exists else ""
        enriched["text"] = letter.get("text", "")
        enriched["parent_letter_id"] = metadata.get("parent_letter_id") or letter.get("parent_letter_id") or ""
        enriched["revision_count"] = parent_counts.get(letter_id, 0)
        enriched["project_id"] = metadata.get("project_id", "")
        enriched["source_asset_ids"] = metadata.get("source_asset_ids", [])
        passages = metadata.get("selected_source_passages", [])
        enriched["selected_source_count"] = len(passages) if isinstance(passages, list) else 0
        enriched["creation_job_id"] = job.get("job_id")
        enriched["creation_status"] = job.get("status")
        enriched["video_path"] = letter.get("video_path") or enriched.get("video_path") or ""
        enriched["visual_path"] = letter.get("visual_path", "")
        enriched["audio_path"] = letter.get("audio_path", "")
        enriched["video_url"] = _file_uri(enriched["video_path"])
        enriched["visual_url"] = _file_uri(enriched["visual_path"])
        enriched["audio_url"] = _file_uri(enriched["audio_path"])
        enriched["release_events"] = release.get("events", [])[-10:] if isinstance(release.get("events"), list) else []
        enriched["public_release_log"] = log
        rows.append(enriched)

    seen_letters = {str(row.get("letter_id") or "") for row in rows}
    for job in jobs:
        letter_id = str(job.get("letter_id") or "")
        if letter_id and letter_id in seen_letters:
            continue
        status = str(job.get("status") or "")
        if status not in {"queued", "running", "failed"}:
            continue
        rows.append(
            {
                "letter_id": letter_id or str(job.get("job_id") or ""),
                "title": "Creating Letter" if status in {"queued", "running"} else "Creation Failed",
                "theme": job.get("theme", ""),
                "lifecycle_state": job.get("current_stage") or status,
                "evaluation_total": job.get("final_score"),
                "audio_alignment": job.get("audio_score"),
                "eligible": False,
                "reasons": job.get("release_reasons", []),
                "release_state": "creating" if status in {"queued", "running"} else "failed",
                "approved": False,
                "brand_id": job.get("brand_id") or DEFAULT_BRAND_ID,
                "brand_display_name": safe_brand_metadata(job.get("brand_id") or DEFAULT_BRAND_ID).get("display_name"),
                "brand_status": safe_brand_metadata(job.get("brand_id") or DEFAULT_BRAND_ID).get("status"),
                "brand": safe_brand_metadata(job.get("brand_id") or DEFAULT_BRAND_ID),
                "release_disabled_reasons": job.get("release_reasons", []),
                "site_enabled": False,
                "youtube_enabled": False,
                "canonical_url": None,
                "site_status": None,
                "youtube_status": None,
                "youtube_url": None,
                "release_log_path": "",
                "manual_social_urls": {},
                "release_export_dir": "",
                "release_export_url": "",
                "text": "",
                "parent_letter_id": job.get("parent_letter_id") or "",
                "revision_count": 0,
                "project_id": job.get("project_id") or "",
                "source_asset_ids": job.get("source_asset_ids") or [],
                "selected_source_count": len(job.get("source_passages") or []),
                "creation_job_id": job.get("job_id"),
                "creation_status": status,
                "video_path": "",
                "visual_path": "",
                "audio_path": "",
                "video_url": "",
                "visual_url": "",
                "audio_url": "",
                "release_events": [],
                "public_release_log": {},
                "is_creation_job": True,
            }
        )
    return rows


def _job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(job)
    letter_id = str(job.get("letter_id") or "")
    letter = _read_json(_letter_dir(letter_id) / "letter.json") if letter_id else {}
    release = _read_release(letter_id) if letter_id else {}
    check = check_release_eligibility(letter_id) if letter_id else None

    video_path = letter.get("video_path", "")
    visual_path = letter.get("visual_path", "")
    audio_path = letter.get("audio_path", "")
    if not video_path or not visual_path:
        for event in reversed(job.get("events", [])):
            summary = event.get("summary", {}) if isinstance(event, dict) else {}
            if not isinstance(summary, dict):
                continue
            video_path = video_path or summary.get("video_path", "")
            visual_path = visual_path or summary.get("visual_path", "")
            audio_path = audio_path or summary.get("audio_path", "")

    enriched["title"] = letter.get("title", "")
    enriched["text"] = letter.get("text", "")
    enriched["release_state"] = release.get("release_state") or "unseen"
    enriched["approved"] = bool(release.get("approved", False))
    enriched["brand_id"] = job.get("brand_id") or DEFAULT_BRAND_ID
    enriched["brand_display_name"] = safe_brand_metadata(enriched["brand_id"]).get("display_name")
    enriched["brand_status"] = safe_brand_metadata(enriched["brand_id"]).get("status")
    enriched["eligible"] = check.eligible if check else bool(job.get("release_eligible"))
    enriched["eligibility_reasons"] = check.reasons if check else job.get("release_reasons", [])
    enriched["video_url"] = _file_uri(video_path)
    enriched["visual_url"] = _file_uri(visual_path)
    enriched["audio_url"] = _file_uri(audio_path)
    return enriched


def _jobs_payload() -> List[Dict[str, Any]]:
    return [_job_payload(job) for job in list_creation_jobs()]


def _extract_letter_id(body: Dict[str, Any]) -> str:
    letter_id = str(body.get("letter_id", "")).strip()
    if not letter_id:
        raise ValueError("letter_id is required")
    return letter_id


def _render_release_dashboard_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Letters of Light Campaign Manager</title>
  <style>
    :root {
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #1f2528;
      --muted: #667075;
      --line: #d9ddd8;
      --green: #18623c;
      --green-bg: #e7f4ec;
      --red: #9a2d2d;
      --red-bg: #f7e8e5;
      --blue: #264f7a;
      --blue-bg: #e5eef7;
      --amber: #795600;
      --amber-bg: #fff3cf;
      --button: #2f3a40;
      --button-hover: #141a1e;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.45;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0;
    }

    main {
      padding: 18px 22px 28px;
      width: 100%;
      overflow-x: auto;
    }

    .summary {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      white-space: nowrap;
    }

    button, .link-button {
      appearance: none;
      border: 1px solid transparent;
      background: var(--button);
      color: #fff;
      border-radius: 6px;
      padding: 7px 10px;
      min-height: 32px;
      font: inherit;
      font-weight: 600;
      letter-spacing: 0;
      text-decoration: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }

    button:hover, .link-button:hover { background: var(--button-hover); }
    button:disabled, .link-button[aria-disabled="true"] {
      background: #c6cbc8;
      color: #5d6668;
      cursor: not-allowed;
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .status {
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
    }

    table {
      width: 100%;
      min-width: 1380px;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: middle;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef0ed;
      color: #3d4649;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    tr:last-child td { border-bottom: 0; }
    td.id { font-family: Consolas, "SFMono-Regular", monospace; font-size: 13px; }
    td.title { min-width: 180px; font-weight: 620; }
    td.score, td.audio { font-variant-numeric: tabular-nums; }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .yes { color: var(--green); background: var(--green-bg); }
    .no { color: var(--red); background: var(--red-bg); }
    .state-exported, .state-approved, .state-published { color: var(--green); background: var(--green-bg); }
    .state-candidate { color: var(--blue); background: var(--blue-bg); }
    .state-manual_required, .state-failed { color: var(--red); background: var(--red-bg); }
    .state-unseen, .state-draft, .state-scheduled, .state-pending { color: var(--amber); background: var(--amber-bg); }

    .actions {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 520px;
      flex-wrap: wrap;
    }

    select {
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 8px;
    }

    .path {
      color: var(--muted);
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 12px;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    @media (max-width: 760px) {
      header, .toolbar {
        align-items: flex-start;
        flex-direction: column;
      }
      main { padding: 14px; }
      table { min-width: 1240px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Letters of Light Campaign Manager</h1>
    <div class="summary" id="summary">Loading...</div>
  </header>
  <main>
    <div class="toolbar">
      <div class="status" id="status"></div>
      <button id="refresh" type="button">Refresh</button>
    </div>
    <table aria-label="Letters">
      <thead>
        <tr>
          <th>Letter ID</th>
          <th>Title</th>
          <th>Theme</th>
          <th>Score</th>
          <th>Audio</th>
          <th>Eligibility</th>
          <th>Release State</th>
          <th>Canonical</th>
          <th>Site</th>
          <th>YouTube</th>
          <th>Manual Log</th>
          <th>Export Folder</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="letters"></tbody>
    </table>
  </main>
  <script>
    const tbody = document.getElementById("letters");
    const statusEl = document.getElementById("status");
    const summaryEl = document.getElementById("summary");
    const refreshBtn = document.getElementById("refresh");

    function stateClass(value) {
      return "state-" + String(value || "unseen").replace(/[^a-z0-9_]+/gi, "_").toLowerCase();
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function badge(text, cls) {
      return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
    }

    function setBusy(isBusy) {
      form.querySelectorAll("button, input, select, textarea").forEach((control) => {
        if (control.id !== "refresh") control.disabled = isBusy;
      });
      refreshBtn.disabled = isBusy;
    }

    async function api(path, body) {
      const response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: body ? {"Content-Type": "application/json"} : {},
        body: body ? JSON.stringify(body) : undefined
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function apiForm(path, formData) {
      const response = await fetch(path, {method: "POST", body: formData});
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function runAction(path, letterId, extra = {}) {
      setBusy(true);
      statusEl.textContent = `${letterId}: working`;
      try {
        await api(path, {letter_id: letterId, ...extra});
        await loadLetters();
        statusEl.textContent = `${letterId}: updated`;
      } catch (error) {
        statusEl.textContent = `${letterId}: ${error.message}`;
      } finally {
        setBusy(false);
      }
    }

    function openExport(row) {
      if (!row.release_export_url) return;
      window.open(row.release_export_url, "_blank", "noopener");
    }

    async function copyManualPackage(row) {
      const lines = [
        `Letter: ${row.title || row.letter_id}`,
        `Canonical: ${row.canonical_url || ""}`,
        "Collection: https://brendonrcoleman.com/letters/",
        `Export: ${row.release_export_dir || ""}`
      ];
      await navigator.clipboard.writeText(lines.join("\\n"));
    }

    function render(rows) {
      const eligibleCount = rows.filter((row) => row.eligible).length;
      const exportedCount = rows.filter((row) => row.release_state === "exported").length;
      const publishedCount = rows.filter((row) => row.release_state === "published").length;
      summaryEl.textContent = `${rows.length} letters | ${eligibleCount} eligible | ${exportedCount} exported | ${publishedCount} published`;

      tbody.innerHTML = rows.map((row) => {
        const eligible = row.eligible ? badge("eligible", "yes") : badge("blocked", "no");
        const state = row.release_state || "unseen";
        const stateBadge = badge(state, stateClass(state));
        const exportDisabled = row.release_export_url ? "" : "disabled";
        const candidateDisabled = row.eligible ? "" : "disabled";
        const approveDisabled = row.eligible ? "" : "disabled";
        const exportActionDisabled = row.approved ? "" : "disabled";
        const siteActionDisabled = (row.release_state === "exported" || row.release_state === "published") ? "" : "disabled";
        const youtubeActionDisabled = (row.approved && row.release_export_dir && row.youtube_status !== "published") ? "" : "disabled";
        const exportPath = row.release_export_dir || "";
        const score = row.evaluation_total ?? "";
        const audio = row.audio_alignment ?? "";
        const letterId = escapeHtml(row.letter_id);
        const title = escapeHtml(row.title || "");
        const theme = escapeHtml(row.theme || "");
        const exportTitle = escapeHtml(exportPath);
        const canonical = row.canonical_url
          ? `<a href="${escapeHtml(row.canonical_url)}" target="_blank" rel="noopener">Open</a>`
          : "";
        const site = badge(row.site_status || "pending", stateClass(row.site_status || "pending"));
        const youtubeStatus = row.youtube_url
          ? `<a href="${escapeHtml(row.youtube_url)}" target="_blank" rel="noopener">${badge(row.youtube_status || "published", stateClass(row.youtube_status || "published"))}</a>`
          : badge(row.youtube_status || "pending", stateClass(row.youtube_status || "pending"));
        const logCount = Object.values(row.manual_social_urls || {}).filter(Boolean).length;
        const manualLog = row.release_log_path ? `${logCount} URLs` : "";

        return `<tr>
          <td class="id">${letterId}</td>
          <td class="title">${title}</td>
          <td>${theme}</td>
          <td class="score">${escapeHtml(score)}</td>
          <td class="audio">${escapeHtml(audio)}</td>
          <td>${eligible}</td>
          <td>${stateBadge}</td>
          <td>${canonical}</td>
          <td>${site}</td>
          <td>${youtubeStatus}</td>
          <td>${escapeHtml(manualLog)}</td>
          <td><div class="path" title="${exportTitle}">${exportTitle}</div></td>
          <td>
            <div class="actions">
              <button type="button" ${candidateDisabled} data-action="/api/candidate" data-id="${letterId}">Candidate</button>
              <button type="button" ${approveDisabled} data-action="/api/approve" data-id="${letterId}">Approve</button>
              <button type="button" ${exportActionDisabled} data-action="/api/export" data-id="${letterId}">Export</button>
              <button type="button" ${siteActionDisabled} data-action="/api/publish-site" data-id="${letterId}">Publish to Site</button>
              <select ${youtubeActionDisabled} data-youtube-privacy="${letterId}" aria-label="YouTube privacy">
                <option value="unlisted" selected>Unlisted</option>
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
              <button type="button" ${youtubeActionDisabled} data-action="/api/publish/youtube" data-id="${letterId}">Publish YouTube</button>
              <button type="button" ${exportDisabled} data-copy="${letterId}">Copy Manual Package</button>
              <button type="button" ${exportDisabled} data-open="${letterId}">Open</button>
            </div>
          </td>
        </tr>`;
      }).join("");

      tbody.querySelectorAll("button[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const extra = {};
          if (button.dataset.action === "/api/publish/youtube") {
            const select = tbody.querySelector(`select[data-youtube-privacy="${button.dataset.id}"]`);
            extra.privacy_status = select ? select.value : "unlisted";
          }
          runAction(button.dataset.action, button.dataset.id, extra);
        });
      });
      tbody.querySelectorAll("button[data-open]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.open);
        button.addEventListener("click", () => openExport(row));
      });
      tbody.querySelectorAll("button[data-copy]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.copy);
        button.addEventListener("click", () => {
          copyManualPackage(row)
            .then(() => { statusEl.textContent = `${row.letter_id}: manual package copied`; })
            .catch((error) => { statusEl.textContent = `${row.letter_id}: ${error.message}`; });
        });
      });
    }

    async function loadLetters() {
      const rows = await api("/api/letters");
      render(rows);
    }

    refreshBtn.addEventListener("click", () => {
      statusEl.textContent = "Refreshing";
      loadLetters()
        .then(() => { statusEl.textContent = "Refreshed"; })
        .catch((error) => { statusEl.textContent = error.message; });
    });

    loadLetters()
      .then(() => { statusEl.textContent = "Ready"; })
      .catch((error) => { statusEl.textContent = error.message; });
  </script>
</body>
</html>
"""


def _render_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Multi-Brand Studio</title>
  <style>
    :root {
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #202628;
      --muted: #687377;
      --line: #d9ded8;
      --soft: #eef1ec;
      --green: #17613b;
      --green-bg: #e6f4eb;
      --red: #9b302c;
      --red-bg: #f8e8e4;
      --blue: #22577a;
      --blue-bg: #e4eef7;
      --amber: #755700;
      --amber-bg: #fff2ca;
      --button: #2f3a40;
      --button-hover: #141a1e;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.45;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 20px; font-weight: 700; letter-spacing: 0; }
    h2 { font-size: 16px; font-weight: 700; letter-spacing: 0; }
    h3 { font-size: 14px; font-weight: 700; letter-spacing: 0; }

    main {
      display: grid;
      gap: 16px;
      padding: 18px 22px 28px;
      width: 100%;
      overflow-x: auto;
    }

    .summary, .status {
      color: var(--muted);
      font-size: 13px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }

    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .create-grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1.1fr) minmax(240px, 0.7fr);
      gap: 14px;
      align-items: start;
    }

    .studio-grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.75fr) minmax(360px, 1.25fr);
      gap: 14px;
      align-items: start;
    }

    .workspace-grid, .composition-grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.8fr) minmax(360px, 1.2fr);
      gap: 14px;
      align-items: start;
    }

    .voice-grid {
      display: grid;
      grid-template-columns: minmax(280px, 0.75fr) minmax(360px, 1.25fr);
      gap: 14px;
      align-items: start;
    }

    .compact-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(90px, 1fr));
      gap: 8px;
    }

    form {
      display: grid;
      gap: 10px;
    }

    label {
      display: grid;
      gap: 5px;
      color: #374044;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    input, select, textarea {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 7px 9px;
    }

    textarea {
      min-height: 82px;
      resize: vertical;
    }

    .theme-row {
      display: grid;
      grid-template-columns: minmax(140px, 180px) minmax(160px, 1fr);
      gap: 8px;
    }

    .form-actions, .toolbar, .filters, .actions, .media-links {
      display: flex;
      align-items: center;
      gap: 7px;
      flex-wrap: wrap;
    }

    button, .link-button {
      appearance: none;
      border: 1px solid transparent;
      background: var(--button);
      color: #fff;
      border-radius: 6px;
      padding: 7px 10px;
      min-height: 32px;
      font: inherit;
      font-weight: 650;
      letter-spacing: 0;
      text-decoration: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }

    button:hover, .link-button:hover { background: var(--button-hover); }
    button.secondary { background: #eef1ec; color: #293135; border-color: var(--line); }
    button.secondary:hover { background: #dfe5dd; }
    button:disabled, .link-button[aria-disabled="true"] {
      background: #c6cbc8;
      color: #5d6668;
      cursor: not-allowed;
    }

    .readiness {
      display: grid;
      gap: 8px;
    }

    .readiness-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
    }

    .readiness-row:last-child { border-bottom: 0; }

    .source-drop {
      border: 1px dashed #aeb8b1;
      border-radius: 8px;
      background: #fafbf8;
      padding: 12px;
      display: grid;
      gap: 9px;
    }

    .governed-draft-panel {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      margin-top: 12px;
      padding: 12px;
      display: grid;
      gap: 9px;
    }

    .governed-draft-panel h3 {
      margin: 0;
    }

    .governed-disclosure {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .governed-brief-context {
      display: grid;
      gap: 6px;
      color: #344044;
      font-size: 13px;
    }

    .governed-proposal-discovery {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfa;
      padding: 10px;
      display: grid;
      gap: 8px;
    }

    .governed-proposal-discovery h4 {
      margin: 0;
      font-size: 13px;
    }

    .source-grounded-outline-panel {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfa;
      padding: 10px;
      display: grid;
      gap: 8px;
    }

    .source-grounded-outline-panel h4 {
      margin: 0;
      font-size: 13px;
    }

    .governed-proposal-search {
      display: grid;
      grid-template-columns: minmax(120px, 1fr) auto;
      gap: 8px;
      align-items: center;
    }

    .governed-proposal-results {
      display: grid;
      gap: 8px;
    }

    .governed-proposal-section {
      display: grid;
      gap: 6px;
    }

    .governed-proposal-section-title {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .governed-proposal-row {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 8px;
      display: grid;
      gap: 6px;
    }

    .governed-proposal-title {
      font-weight: 700;
    }

    .governed-proposal-actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }

    .governed-blocker-list {
      display: grid;
      gap: 4px;
    }

    .governed-blocker-message {
      display: block;
    }

    .governed-blocker-code {
      color: var(--muted);
      font-size: 11px;
      margin-left: 4px;
    }

    .reader-panel {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      min-height: 220px;
      max-height: 360px;
      overflow: auto;
      padding: 14px;
      line-height: 1.65;
      font-size: 22px;
      white-space: pre-wrap;
    }

    .voice-sources, .transcript-list {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }

    .transcript-row {
      display: grid;
      grid-template-columns: 24px minmax(78px, 96px) 1fr;
      gap: 8px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 8px;
    }

    .transcript-row input[type="checkbox"] {
      width: 18px;
      min-height: 18px;
      margin-top: 5px;
    }

    .transcript-row textarea {
      min-height: 50px;
    }

    .audio-preview {
      width: 100%;
    }

    .project-list, .source-list, .passage-list, .composition-list, .render-list {
      display: grid;
      gap: 8px;
    }

    .project-row, .asset-row, .passage-item, .composition-row, .render-row {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 9px;
      display: grid;
      gap: 5px;
    }

    .project-row.active, .asset-row.active {
      border-color: var(--blue);
      box-shadow: inset 3px 0 0 var(--blue);
    }

    .source-meta {
      color: var(--muted);
      font-size: 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .passage-item {
      grid-template-columns: 22px 1fr;
      align-items: start;
      max-height: 130px;
      overflow: auto;
    }

    .passage-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 10px;
      display: grid;
      gap: 7px;
    }

    .passage-card label {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 500;
      text-transform: none;
    }

    .passage-card input[type="checkbox"] {
      width: 18px;
      min-height: 18px;
      margin-top: 2px;
      flex: 0 0 auto;
    }

    .passage-heading {
      color: var(--ink);
      font-weight: 750;
    }

    .passage-preview {
      color: #344044;
    }

    .passage-card details {
      color: var(--muted);
      font-size: 13px;
    }

    .passage-card summary {
      cursor: pointer;
      color: var(--blue);
      font-weight: 650;
    }

    .passage-debug {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .passage-debug pre {
      max-height: 220px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fafbf8;
      white-space: pre-wrap;
    }

    .preview-frame {
      width: 100%;
      max-height: 280px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #111;
    }

    .render-preview {
      width: min(100%, 560px);
      max-height: 320px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #111;
    }

    .revision-notice {
      display: none;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 10px;
      border: 1px solid #c7d6e3;
      border-radius: 6px;
      background: var(--blue-bg);
      color: var(--blue);
      font-size: 13px;
      font-weight: 650;
    }

    .revision-notice.active { display: flex; }

    table {
      width: 100%;
      min-width: 1280px;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px;
      text-align: left;
      vertical-align: top;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--soft);
      color: #3d4649;
      font-size: 12px;
      font-weight: 750;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    tr:last-child td { border-bottom: 0; }
    td.id { font-family: Consolas, "SFMono-Regular", monospace; font-size: 12px; }
    td.title { min-width: 190px; font-weight: 650; }
    td.score, td.audio { font-variant-numeric: tabular-nums; }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 23px;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }

    .yes { color: var(--green); background: var(--green-bg); }
    .no { color: var(--red); background: var(--red-bg); }
    .state-succeeded, .state-completed, .state-ready, .state-registered, .state-exported, .state-approved, .state-published, .state-active { color: var(--green); background: var(--green-bg); }
    .state-running, .state-recording, .state-candidate, .state-composed, .state-evaluated, .state-interaction_added { color: var(--blue); background: var(--blue-bg); }
    .state-failed, .state-manual_required, .state-evaluation_failed, .state-quarantined { color: var(--red); background: var(--red-bg); }
    .state-queued, .state-paused, .state-processing, .state-permission_required, .state-unavailable, .state-unseen, .state-draft, .state-scheduled, .state-pending, .state-creating, .state-internal_only { color: var(--amber); background: var(--amber-bg); }

    .path {
      color: var(--muted);
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 12px;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .timeline {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      max-width: 520px;
    }

    .timeline .badge {
      border-radius: 6px;
      font-size: 11px;
      min-height: 22px;
    }

    .media-links a {
      color: var(--blue);
      font-weight: 650;
      text-decoration: none;
    }

    .media-links a:hover { text-decoration: underline; }

    .empty {
      color: var(--muted);
      padding: 6px 0;
    }

    .filter.active {
      background: var(--blue);
      color: #fff;
      border-color: var(--blue);
    }

    @media (max-width: 980px) {
      header, .panel-head {
        align-items: flex-start;
        flex-direction: column;
      }
      main { padding: 14px; }
      .create-grid { grid-template-columns: 1fr; }
      .studio-grid, .workspace-grid, .composition-grid, .voice-grid { grid-template-columns: 1fr; }
      .theme-row { grid-template-columns: 1fr; }
      .compact-grid { grid-template-columns: 1fr; }
      table { min-width: 1180px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Multi-Brand Studio</h1>
    <div class="summary" id="summary">Loading</div>
  </header>

  <main>
    <section class="panel" aria-labelledby="projects-title">
      <div class="panel-head">
        <h2 id="projects-title">Project Library</h2>
        <div class="toolbar">
          <select id="project-brand-filter" aria-label="Brand filter"></select>
          <select id="new-project-brand" aria-label="New project brand"></select>
          <input id="new-project-title" type="text" placeholder="project title">
          <button id="new-project" type="button">New Project</button>
        </div>
      </div>
      <div class="studio-grid">
        <div class="project-list" id="project-list"></div>
        <div>
          <h3>Project Workspace</h3>
          <div class="status" id="project-summary">No project selected</div>
          <div class="readiness" id="brand-requirements"></div>
          <div class="toolbar" style="margin-top:10px;">
            <select id="clone-brand" aria-label="Clone target brand"></select>
            <button class="secondary" id="clone-to-brand" type="button">Clone to Brand</button>
          </div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="voice-intake-title">
      <div class="panel-head">
        <h2 id="voice-intake-title">Voice Intake</h2>
        <div class="status" id="voice-status">permission_required</div>
      </div>
      <div class="voice-grid">
        <div>
          <div class="toolbar">
            <button id="voice-new" type="button">New Voice Capture</button>
            <button class="secondary filter active" id="voice-free-talk" type="button">Free Talk</button>
            <button class="secondary filter" id="voice-read-script" type="button">Read Script</button>
          </div>
          <label>Save Target
            <select id="voice-save-target">
              <option value="new_project">New project</option>
              <option value="active_project">Selected project</option>
            </select>
          </label>
          <label>Brand
            <select id="voice-brand"></select>
          </label>
          <label>Project Title
            <input id="voice-project-title" type="text" placeholder="optional title">
          </label>
          <label>Script Source
            <textarea id="voice-script-text" placeholder="paste or load text for Read Script"></textarea>
          </label>
          <div class="toolbar">
            <span class="badge state-pending" id="voice-state">permission_required</span>
            <span class="status" id="voice-elapsed">00:00</span>
          </div>
          <div class="form-actions">
            <button id="voice-start" type="button">Start Recording</button>
            <button class="secondary" id="voice-pause" type="button" disabled>Pause</button>
            <button class="secondary" id="voice-resume" type="button" disabled>Resume</button>
            <button class="secondary" id="voice-stop" type="button" disabled>Stop</button>
            <button class="secondary" id="voice-discard" type="button" disabled>Discard</button>
            <button id="voice-save" type="button" disabled>Save Recording</button>
          </div>
          <audio class="audio-preview" id="voice-playback" controls></audio>
        </div>
        <div>
          <div class="toolbar">
            <label>Reader Size
              <input id="voice-reader-size" type="range" min="18" max="42" step="1" value="22">
            </label>
            <label><input id="voice-auto-scroll" type="checkbox"> Auto-scroll</label>
          </div>
          <div class="reader-panel" id="voice-reader">Select Read Script or paste text to use the reader.</div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="workspace-title">
      <div class="panel-head">
        <h2 id="workspace-title">Source Workspace</h2>
        <div class="status" id="workspace-status"></div>
      </div>
      <div class="workspace-grid">
        <div class="source-drop" id="source-drop">
          <label>Source Upload
            <input id="asset-file" type="file" accept=".pdf,.txt,.md,.markdown,.mp4,.mov,.webm,.wav,.mp3,.m4a,.png,.jpg,.jpeg,.webp">
          </label>
          <label>Local Source Path
            <input id="asset-path" type="text" placeholder="optional local path">
          </label>
          <div class="form-actions">
            <button id="import-asset" type="button">Import Source</button>
            <button class="secondary" id="extract-asset" type="button">Extract Text</button>
          </div>
          <div class="source-list" id="source-list"></div>
        </div>

        <div>
          <h3>PDF Passage Selector</h3>
          <input id="passage-search" type="search" placeholder="search extracted PDF text">
          <div class="toolbar">
            <button class="secondary" id="select-visible-passages" type="button">Select visible</button>
            <button class="secondary" id="clear-passages" type="button">Clear selection</button>
            <button class="secondary" id="read-selected-passages" type="button">Read Selected</button>
            <div class="status" id="selected-passage-count">0 selected</div>
          </div>
          <div class="passage-list" id="passage-list"></div>
          <details class="passage-debug" id="raw-extraction-details">
            <summary>Raw extraction details</summary>
            <pre id="raw-extraction-debug"></pre>
          </details>
          <label>Visible Draft
            <textarea id="project-letter-draft" placeholder="selected passages build an editable draft"></textarea>
          </label>
          <div class="theme-row">
            <input id="project-letter-theme" type="text" placeholder="theme">
            <button id="project-create-letter" type="button">Create Letter from Sources</button>
          </div>
          <div class="governed-draft-panel" id="governed-draft-panel">
            <h3>Open Governed Draft</h3>
            <div class="governed-disclosure">This opens an editable Project Studio draft. It does not approve, schedule, export, publish, or release anything. Source references provide provenance context and are not independent fact verification.</div>
            <div class="governed-proposal-discovery" id="governed-proposal-discovery">
              <div class="toolbar">
                <h4>Find Governed Proposal</h4>
                <button class="secondary" id="governed-find-proposals" type="button" disabled>Find Governed Proposal</button>
              </div>
              <div class="governed-proposal-search">
                <input id="governed-proposal-search" type="search" placeholder="search thesis or proposal ID">
                <button class="secondary" id="governed-clear-proposal-search" type="button">Clear</button>
              </div>
              <div class="status" id="governed-proposal-discovery-status">Select a project to find promoted proposals.</div>
              <div class="governed-proposal-results" id="governed-proposal-results"></div>
            </div>
            <label>Governed Proposal ID
              <input id="governed-proposal-id" type="text" placeholder="proposal ID">
            </label>
            <label>Draft Intent Ref
              <input id="governed-draft-intent" type="text" placeholder="draft-intent:primary">
            </label>
            <label>Working Title
              <input id="governed-working-title" type="text" placeholder="optional title">
            </label>
            <label>Writer Note
              <textarea id="governed-writer-note" placeholder="optional internal note"></textarea>
            </label>
            <div class="governed-brief-context" id="governed-brief-context"></div>
            <div class="form-actions">
              <button class="secondary" id="governed-check-proposal" type="button" disabled>Check Proposal</button>
              <button id="governed-open-draft" type="button" disabled>Open Governed Draft</button>
              <button class="secondary" id="governed-open-existing-draft" type="button" disabled>Open Existing Draft</button>
            </div>
            <div class="status" id="governed-draft-status">Select a project, proposal, draft intent, and source passages.</div>
            <div class="source-grounded-outline-panel" id="source-grounded-outline-panel">
              <h4>Source-Grounded Outline</h4>
              <div class="governed-disclosure">This creates an editable scaffold-only child draft. It does not approve, schedule, export, publish, or release anything. Source references provide provenance context and are not independent fact verification.</div>
              <label>Outline Preview Intent Ref
                <input id="outline-preview-intent" type="text" placeholder="outline-preview:intent">
              </label>
              <label>Format Intent
                <input id="outline-format-intent" type="text" placeholder="optional format guidance">
              </label>
              <label>Outline Writer Note
                <textarea id="outline-writer-note" placeholder="optional note for the scaffold"></textarea>
              </label>
              <div class="governed-brief-context" id="outline-preview-context"></div>
              <div class="form-actions">
                <button class="secondary" id="outline-preview-action" type="button" disabled>Preview Grounded Outline</button>
                <button id="outline-accept-action" type="button" disabled>Accept Outline into Child Draft</button>
                <button class="secondary" id="outline-open-child" type="button" disabled>Open Existing Child Draft</button>
              </div>
              <div class="status" id="outline-preview-status">Open or select a governed handoff Letter, choose source passages, and enter a preview intent.</div>
            </div>
            <div class="source-grounded-prose-panel" id="source-grounded-prose-panel">
              <h4>Grounded Prose Candidate</h4>
              <div class="governed-disclosure">This generates a draft candidate for review. It does not approve, schedule, export, publish, or release anything.</div>
              <div class="governed-disclosure">Source references provide provenance context and are not independent fact verification. Direct quotations are unavailable in this version.</div>
              <label>Accepted Scaffold Letter
                <select id="prose-scaffold-letter"></select>
              </label>
              <label>Outline Section
                <select id="prose-outline-section"></select>
              </label>
              <label>Candidate Intent Ref
                <input id="prose-candidate-intent" type="text" placeholder="candidate-intent:primary">
              </label>
              <label>Length / Format
                <select id="prose-format-constraint">
                  <option value="section_paragraph">section_paragraph</option>
                  <option value="short_paragraph">short_paragraph</option>
                  <option value="medium_paragraph">medium_paragraph</option>
                  <option value="long_paragraph">long_paragraph</option>
                  <option value="brief_reflection">brief_reflection</option>
                  <option value="essay_section">essay_section</option>
                  <option value="letter_section">letter_section</option>
                </select>
              </label>
              <label>Writer Instruction
                <textarea id="prose-writer-instruction" placeholder="optional generation guidance"></textarea>
              </label>
              <label>Apply Intent Ref
                <input id="prose-apply-intent" type="text" placeholder="apply-intent:primary">
              </label>
              <div class="governed-brief-context" id="prose-candidate-context"></div>
              <div class="form-actions">
                <button class="secondary" id="prose-generate-action" type="button" disabled>Generate Grounded Candidate</button>
                <button id="prose-apply-action" type="button" disabled>Apply Candidate to Child Draft</button>
                <button class="secondary" id="prose-open-applied-child" type="button" disabled>Open Existing Applied Draft</button>
              </div>
              <div class="status" id="prose-candidate-status">Accept a source-grounded outline child, select an outline section and source passages, then enter a candidate intent.</div>
            </div>
            <div class="production-derivative-panel" id="production-derivative-panel">
              <h4>Production Derivative</h4>
              <div class="governed-disclosure" id="production-derivative-authority-notice">This creates a separate production derivative for normal pipeline processing.<br>It does not approve, release, export, schedule, publish, or grant platform authority.</div>
              <label>Expected Source Body Hash
                <input id="production-derivative-source-hash" type="text" placeholder="source body hash">
              </label>
              <label>Promotion Intent Ref
                <input id="production-derivative-intent" type="text" placeholder="production-derivative:intent:primary">
              </label>
              <label>Operator Ref
                <input id="production-derivative-operator" type="text" placeholder="operator.ref">
              </label>
              <label>Target Theme
                <input id="production-derivative-theme" type="text" placeholder="optional target theme">
              </label>
              <label>Operator Note
                <textarea id="production-derivative-note" placeholder="optional operator note"></textarea>
              </label>
              <div class="governed-brief-context" id="production-derivative-context"></div>
              <div class="form-actions">
                <button class="secondary" id="production-derivative-validate" type="button" disabled>Validate Production Derivative</button>
                <button id="production-derivative-create" type="button" disabled>Create Production Derivative</button>
              </div>
              <div class="status" id="production-derivative-status">Open or select a governed draft, then enter source hash, promotion intent, and operator reference.</div>
            </div>
            <div class="production-derivative-status-panel" id="production-derivative-status-panel">
              <h4>Production Derivative Status</h4>
              <div class="governed-disclosure" id="production-derivative-status-authority-notice">Promotion created a separate production derivative. This status view does not approve, release, export, schedule, publish, or grant platform authority.</div>
              <div class="governed-brief-context" id="production-derivative-status-context"></div>
              <div class="status" id="production-derivative-status-state">Open or select a governed draft to inspect production derivative status.</div>
            </div>
          </div>
          <div id="source-preview"></div>
          <div class="voice-sources">
            <div class="toolbar">
              <h3>Voice Sources</h3>
              <button class="secondary" id="record-project-voice" type="button">Record New Voice</button>
            </div>
            <div class="source-list" id="voice-source-list"></div>
            <div class="toolbar">
              <button class="secondary" id="voice-transcribe" type="button">Transcribe</button>
              <button class="secondary" id="voice-save-transcript" type="button">Save Transcript Edits</button>
              <button class="secondary" id="voice-copy-draft" type="button">Copy selected to draft</button>
            </div>
            <div class="theme-row">
              <input id="voice-letter-theme" type="text" placeholder="theme">
              <button id="voice-create-letter" type="button">Create Letter from selected transcript</button>
            </div>
            <button class="secondary" id="voice-use-composition" type="button">Use selected transcript as composition caption</button>
            <div class="transcript-list" id="voice-transcript-list"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="composition-title">
      <div class="panel-head">
        <h2 id="composition-title">Composition Editor V1</h2>
        <div class="status" id="composition-status"></div>
      </div>
      <div class="composition-grid">
        <div>
          <h3>Clips</h3>
          <div class="source-list" id="clip-list"></div>
          <div class="compact-grid">
            <label>Aspect
              <select id="composition-aspect">
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="1:1">1:1</option>
              </select>
            </label>
            <label>Image
              <select id="composition-image"></select>
            </label>
            <label>Voice
              <select id="composition-voice"></select>
            </label>
          </div>
          <label>Music
            <select id="composition-music"></select>
          </label>
        </div>
        <div>
          <label>Title Text
            <input id="composition-title-text" type="text">
          </label>
          <label>Caption Block
            <textarea id="composition-caption"></textarea>
          </label>
          <div class="form-actions">
            <button id="create-composition" type="button">Create Composition</button>
            <button id="render-composition" type="button">Render</button>
            <button class="secondary" id="promote-render" type="button">Promote to Release</button>
          </div>
          <div class="composition-list" id="composition-list"></div>
          <div class="render-list" id="render-list"></div>
          <div id="render-preview"></div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="create-title">
      <div class="panel-head">
        <h2 id="create-title">Create Letter</h2>
        <div class="status" id="status"></div>
      </div>
      <div class="create-grid">
        <form id="create-form">
          <div class="revision-notice" id="revision-notice">
            <span id="revision-label"></span>
            <button class="secondary" id="cancel-revision" type="button">Cancel</button>
          </div>
          <label>Theme
            <div class="theme-row">
              <select id="theme-select">
                <option value="release">release</option>
                <option value="discipline">discipline</option>
                <option value="fear">fear</option>
                <option value="purpose">purpose</option>
                <option value="gratitude">gratitude</option>
              </select>
              <input id="custom-theme" type="text" placeholder="custom theme">
            </div>
          </label>
          <label>Seed
            <textarea id="seed-field" placeholder="optional seed text"></textarea>
          </label>
          <div class="form-actions">
            <button id="create-button" type="submit">Create Letter</button>
            <button class="secondary" id="refresh" type="button">Refresh</button>
          </div>
        </form>

        <label>Manual Text
          <textarea id="manual-text" placeholder="optional full text override"></textarea>
          <button class="secondary" id="read-manual-text" type="button">Read Script</button>
        </label>

        <div>
          <h3>Configuration</h3>
          <div class="readiness" id="config-readiness"></div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="jobs-title">
      <div class="panel-head">
        <h2 id="jobs-title">Active Jobs</h2>
        <div class="status" id="job-summary"></div>
      </div>
      <table aria-label="Creation jobs">
        <thead>
          <tr>
            <th>Job</th>
            <th>State</th>
            <th>Theme</th>
            <th>Timeline</th>
            <th>Preview</th>
            <th>Score</th>
            <th>Release</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="jobs"></tbody>
      </table>
    </section>

    <section class="panel" aria-labelledby="library-title">
      <div class="panel-head">
        <h2 id="library-title">Release Controls</h2>
        <div class="toolbar">
          <div class="filters" id="filters"></div>
        </div>
      </div>
      <table aria-label="Letters">
        <thead>
          <tr>
            <th>Letter ID</th>
            <th>Title</th>
            <th>Theme</th>
            <th>Brand</th>
            <th>Score</th>
            <th>Audio</th>
            <th>Lifecycle</th>
            <th>Release</th>
            <th>Canonical</th>
            <th>YouTube</th>
            <th>Project / Revision</th>
            <th>Preview</th>
            <th>History</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="letters"></tbody>
      </table>
    </section>
  </main>

  <script>
    const tbody = document.getElementById("letters");
    const jobsBody = document.getElementById("jobs");
    const statusEl = document.getElementById("status");
    const summaryEl = document.getElementById("summary");
    const jobSummaryEl = document.getElementById("job-summary");
    const refreshBtn = document.getElementById("refresh");
    const form = document.getElementById("create-form");
    const createButton = document.getElementById("create-button");
    const themeSelect = document.getElementById("theme-select");
    const customTheme = document.getElementById("custom-theme");
    const seedField = document.getElementById("seed-field");
    const manualText = document.getElementById("manual-text");
    const readinessEl = document.getElementById("config-readiness");
    const filtersEl = document.getElementById("filters");
    const revisionNotice = document.getElementById("revision-notice");
    const revisionLabel = document.getElementById("revision-label");
    const cancelRevisionBtn = document.getElementById("cancel-revision");
    const projectListEl = document.getElementById("project-list");
    const projectSummaryEl = document.getElementById("project-summary");
    const brandRequirementsEl = document.getElementById("brand-requirements");
    const projectBrandFilter = document.getElementById("project-brand-filter");
    const newProjectBrand = document.getElementById("new-project-brand");
    const cloneBrand = document.getElementById("clone-brand");
    const cloneToBrandBtn = document.getElementById("clone-to-brand");
    const workspaceStatusEl = document.getElementById("workspace-status");
    const compositionStatusEl = document.getElementById("composition-status");
    const newProjectTitle = document.getElementById("new-project-title");
    const newProjectBtn = document.getElementById("new-project");
    const assetFile = document.getElementById("asset-file");
    const assetPath = document.getElementById("asset-path");
    const importAssetBtn = document.getElementById("import-asset");
    const extractAssetBtn = document.getElementById("extract-asset");
    const sourceListEl = document.getElementById("source-list");
    const passageSearch = document.getElementById("passage-search");
    const passageListEl = document.getElementById("passage-list");
    const selectVisiblePassagesBtn = document.getElementById("select-visible-passages");
    const clearPassagesBtn = document.getElementById("clear-passages");
    const selectedPassageCountEl = document.getElementById("selected-passage-count");
    const rawExtractionDetails = document.getElementById("raw-extraction-details");
    const rawExtractionDebug = document.getElementById("raw-extraction-debug");
    const projectDraft = document.getElementById("project-letter-draft");
    const projectLetterTheme = document.getElementById("project-letter-theme");
    const projectCreateLetterBtn = document.getElementById("project-create-letter");
    const governedFindProposalsBtn = document.getElementById("governed-find-proposals");
    const governedProposalSearch = document.getElementById("governed-proposal-search");
    const governedClearProposalSearchBtn = document.getElementById("governed-clear-proposal-search");
    const governedProposalDiscoveryStatus = document.getElementById("governed-proposal-discovery-status");
    const governedProposalResults = document.getElementById("governed-proposal-results");
    const governedProposalId = document.getElementById("governed-proposal-id");
    const governedDraftIntent = document.getElementById("governed-draft-intent");
    const governedWorkingTitle = document.getElementById("governed-working-title");
    const governedWriterNote = document.getElementById("governed-writer-note");
    const governedBriefContext = document.getElementById("governed-brief-context");
    const governedCheckProposalBtn = document.getElementById("governed-check-proposal");
    const governedOpenDraftBtn = document.getElementById("governed-open-draft");
    const governedOpenExistingDraftBtn = document.getElementById("governed-open-existing-draft");
    const governedDraftStatus = document.getElementById("governed-draft-status");
    const outlinePreviewIntent = document.getElementById("outline-preview-intent");
    const outlineFormatIntent = document.getElementById("outline-format-intent");
    const outlineWriterNote = document.getElementById("outline-writer-note");
    const outlinePreviewContext = document.getElementById("outline-preview-context");
    const outlinePreviewActionBtn = document.getElementById("outline-preview-action");
    const outlineAcceptActionBtn = document.getElementById("outline-accept-action");
    const outlineOpenChildBtn = document.getElementById("outline-open-child");
    const outlinePreviewStatus = document.getElementById("outline-preview-status");
    const proseScaffoldLetter = document.getElementById("prose-scaffold-letter");
    const proseOutlineSection = document.getElementById("prose-outline-section");
    const proseCandidateIntent = document.getElementById("prose-candidate-intent");
    const proseFormatConstraint = document.getElementById("prose-format-constraint");
    const proseWriterInstruction = document.getElementById("prose-writer-instruction");
    const proseApplyIntent = document.getElementById("prose-apply-intent");
    const proseCandidateContext = document.getElementById("prose-candidate-context");
    const proseGenerateActionBtn = document.getElementById("prose-generate-action");
    const proseApplyActionBtn = document.getElementById("prose-apply-action");
    const proseOpenAppliedChildBtn = document.getElementById("prose-open-applied-child");
    const proseCandidateStatus = document.getElementById("prose-candidate-status");
    const productionDerivativeSourceHash = document.getElementById("production-derivative-source-hash");
    const productionDerivativeIntent = document.getElementById("production-derivative-intent");
    const productionDerivativeOperator = document.getElementById("production-derivative-operator");
    const productionDerivativeTheme = document.getElementById("production-derivative-theme");
    const productionDerivativeNote = document.getElementById("production-derivative-note");
    const productionDerivativeContext = document.getElementById("production-derivative-context");
    const productionDerivativeValidateBtn = document.getElementById("production-derivative-validate");
    const productionDerivativeCreateBtn = document.getElementById("production-derivative-create");
    const productionDerivativeStatus = document.getElementById("production-derivative-status");
    const productionDerivativeStatusContext = document.getElementById("production-derivative-status-context");
    const productionDerivativeStatusState = document.getElementById("production-derivative-status-state");
    const sourcePreviewEl = document.getElementById("source-preview");
    const clipListEl = document.getElementById("clip-list");
    const compositionAspect = document.getElementById("composition-aspect");
    const compositionImage = document.getElementById("composition-image");
    const compositionVoice = document.getElementById("composition-voice");
    const compositionMusic = document.getElementById("composition-music");
    const compositionTitleText = document.getElementById("composition-title-text");
    const compositionCaption = document.getElementById("composition-caption");
    const createCompositionBtn = document.getElementById("create-composition");
    const renderCompositionBtn = document.getElementById("render-composition");
    const promoteRenderBtn = document.getElementById("promote-render");
    const compositionListEl = document.getElementById("composition-list");
    const renderListEl = document.getElementById("render-list");
    const renderPreviewEl = document.getElementById("render-preview");
    const voiceStatusEl = document.getElementById("voice-status");
    const voiceStateEl = document.getElementById("voice-state");
    const voiceElapsedEl = document.getElementById("voice-elapsed");
    const voiceNewBtn = document.getElementById("voice-new");
    const voiceFreeTalkBtn = document.getElementById("voice-free-talk");
    const voiceReadScriptBtn = document.getElementById("voice-read-script");
    const voiceSaveTarget = document.getElementById("voice-save-target");
    const voiceBrand = document.getElementById("voice-brand");
    const voiceProjectTitle = document.getElementById("voice-project-title");
    const voiceScriptText = document.getElementById("voice-script-text");
    const voiceStartBtn = document.getElementById("voice-start");
    const voicePauseBtn = document.getElementById("voice-pause");
    const voiceResumeBtn = document.getElementById("voice-resume");
    const voiceStopBtn = document.getElementById("voice-stop");
    const voiceDiscardBtn = document.getElementById("voice-discard");
    const voiceSaveBtn = document.getElementById("voice-save");
    const voicePlayback = document.getElementById("voice-playback");
    const voiceReader = document.getElementById("voice-reader");
    const voiceReaderSize = document.getElementById("voice-reader-size");
    const voiceAutoScroll = document.getElementById("voice-auto-scroll");
    const readSelectedPassagesBtn = document.getElementById("read-selected-passages");
    const recordProjectVoiceBtn = document.getElementById("record-project-voice");
    const voiceSourceListEl = document.getElementById("voice-source-list");
    const voiceTranscribeBtn = document.getElementById("voice-transcribe");
    const voiceSaveTranscriptBtn = document.getElementById("voice-save-transcript");
    const voiceCopyDraftBtn = document.getElementById("voice-copy-draft");
    const voiceLetterTheme = document.getElementById("voice-letter-theme");
    const voiceCreateLetterBtn = document.getElementById("voice-create-letter");
    const voiceUseCompositionBtn = document.getElementById("voice-use-composition");
    const voiceTranscriptListEl = document.getElementById("voice-transcript-list");
    const readManualTextBtn = document.getElementById("read-manual-text");

    const filters = ["All", "Creating", "Needs Review", "Eligible", "Published", "Failed"];
    let rows = [];
    let jobs = [];
    let projects = [];
    let brands = [];
    let activeProjectBrandFilter = "";
    let activeProject = null;
    let activeAssetId = null;
    let activeCompositionId = null;
    let activeRenderId = null;
    let activeVoiceAssetId = null;
    let activeVoiceTranscript = null;
    let selectedPassages = new Map();
    let selectedTranscriptSegments = new Set();
    let activeFilter = "All";
    let pollTimer = null;
    let revisionParentId = null;
    let voiceMode = "free_talk";
    let voiceRecorder = null;
    let voiceStream = null;
    let voiceChunks = [];
    let voiceBlob = null;
    let voiceObjectUrl = "";
    let voiceStartedAt = 0;
    let voiceElapsedBeforePause = 0;
    let voiceElapsedTimer = null;
    let voiceScrollTimer = null;
    let voiceCanonicalScript = {};
    let voiceDiscarding = false;
    let governedDraftInFlight = false;
    let governedContextInFlight = false;
    let governedDiscoveryInFlight = false;
    let governedDiscovery = null;
    let governedPreview = null;
    let governedPreviewKey = "";
    let governedPreviewError = "";
    let outlinePreview = null;
    let outlinePreviewKeyValue = "";
    let outlinePreviewError = "";
    let outlinePreviewStale = false;
    let outlinePreviewInFlight = false;
    let outlineAcceptanceInFlight = false;
    let proseCandidate = null;
    let proseCandidateKeyValue = "";
    let proseCandidateError = "";
    let proseCandidateStale = false;
    let proseCandidateInFlight = false;
    let proseApplyInFlight = false;
    let proseAppliedChild = null;
    let productionDerivativeCandidate = null;
    let productionDerivativeCandidateKeyValue = "";
    let productionDerivativeError = "";
    let productionDerivativeInFlight = false;
    let productionDerivativeApplyInFlight = false;
    let productionDerivativeApplied = null;
    let productionDerivativeStatusPayload = null;
    let productionDerivativeStatusKeyValue = "";
    let productionDerivativeStatusInFlight = false;
    let productionDerivativeStatusError = "";

    function stateClass(value) {
      return "state-" + String(value || "unseen").replace(/[^a-z0-9_]+/gi, "_").toLowerCase();
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function badge(text, cls) {
      return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
    }

    function yesNo(value) {
      return badge(value ? "yes" : "no", value ? "yes" : "no");
    }

    function brandById(brandId) {
      return brands.find((brand) => brand.brand_id === brandId) || null;
    }

    function brandBadge(brandId, fallbackName, fallbackStatus) {
      const brand = brandById(brandId) || {};
      const name = fallbackName || brand.display_name || brandId || "Letters of Light";
      const status = fallbackStatus || brand.status || "active";
      return `<div>${escapeHtml(name)}</div>${badge(status, stateClass(status))}`;
    }

    function renderBrandControls() {
      const options = brands.map((brand) => {
        const label = `${brand.display_name} (${brand.status})`;
        return `<option value="${escapeHtml(brand.brand_id)}">${escapeHtml(label)}</option>`;
      }).join("");
      const filterOptions = `<option value="">All brands</option>` + options;
      const previousNew = newProjectBrand.value || "letters_of_light";
      const previousVoice = voiceBrand.value || previousNew;
      const previousFilter = projectBrandFilter.value || "";
      const previousClone = cloneBrand.value || "";
      newProjectBrand.innerHTML = options;
      voiceBrand.innerHTML = options;
      projectBrandFilter.innerHTML = filterOptions;
      cloneBrand.innerHTML = options;
      newProjectBrand.value = brands.some((brand) => brand.brand_id === previousNew) ? previousNew : "letters_of_light";
      voiceBrand.value = brands.some((brand) => brand.brand_id === previousVoice) ? previousVoice : "letters_of_light";
      projectBrandFilter.value = brands.some((brand) => brand.brand_id === previousFilter) ? previousFilter : "";
      cloneBrand.value = brands.some((brand) => brand.brand_id === previousClone) ? previousClone : "letters_of_light";
    }

    function collectReviewFields() {
      const fields = {};
      brandRequirementsEl.querySelectorAll("[data-review-field]").forEach((input) => {
        fields[input.dataset.reviewField] = input.value.trim();
      });
      return fields;
    }

    function setBusy(isBusy) {
      form.querySelectorAll("button, input, select, textarea").forEach((control) => {
        if (control.id !== "refresh") control.disabled = isBusy;
      });
      refreshBtn.disabled = isBusy;
    }

    async function api(path, body) {
      const response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: body ? {"Content-Type": "application/json"} : {},
        body: body ? JSON.stringify(body) : undefined
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function apiForm(path, formData) {
      const response = await fetch(path, {method: "POST", body: formData});
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    function mediaLinks(row) {
      const links = [];
      if (row.video_url) links.push(`<a href="${escapeHtml(row.video_url)}" target="_blank" rel="noopener">Video</a>`);
      if (row.visual_url) links.push(`<a href="${escapeHtml(row.visual_url)}" target="_blank" rel="noopener">Visual</a>`);
      if (row.audio_url) links.push(`<a href="${escapeHtml(row.audio_url)}" target="_blank" rel="noopener">Audio</a>`);
      return links.length ? `<div class="media-links">${links.join("")}</div>` : "";
    }

    function activeProjectId() {
      return activeProject ? activeProject.project_id : "";
    }

    function mediaIcon(asset) {
      const type = asset.media_type || "";
      if (type === "pdf") return "PDF";
      if (type === "video") return "Video";
      if (type === "audio") return "Audio";
      if (type === "image") return "Image";
      return "Text";
    }

    function renderProjects() {
      const visibleProjects = activeProjectBrandFilter
        ? projects.filter((project) => project.brand_id === activeProjectBrandFilter)
        : projects;
      if (!visibleProjects.length) {
        projectListEl.innerHTML = `<div class="empty">No projects yet</div>`;
        return;
      }
      projectListEl.innerHTML = visibleProjects.map((project) => {
        const active = activeProject && activeProject.project_id === project.project_id ? "active" : "";
        const title = escapeHtml(project.title || project.project_id);
        const status = escapeHtml(project.status || "active");
        const brand = brandById(project.brand_id) || {};
        const source = project.source_project_id ? `<span>cloned from ${escapeHtml(project.source_brand_id || "source")}</span>` : "";
        return `<button class="project-row ${active}" type="button" data-project="${escapeHtml(project.project_id)}">
          <strong>${title}</strong>
          <span class="source-meta">
            <span>${escapeHtml(project.brand_display_name || brand.display_name || project.brand_id || "Letters of Light")}</span>
            <span>${escapeHtml(project.brand_status || brand.status || "active")}</span>
            <span>${status}</span>
            <span>${escapeHtml(project.source_count || 0)} sources</span>
            <span>${escapeHtml(project.output_count || 0)} outputs</span>
            <span>${escapeHtml(project.release_count || 0)} releases</span>
            ${source}
          </span>
        </button>`;
      }).join("");
      projectListEl.querySelectorAll("[data-project]").forEach((button) => {
        button.addEventListener("click", () => selectProject(button.dataset.project));
      });
    }

    async function selectProject(projectId) {
      activeProject = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      activeAssetId = activeProject.assets && activeProject.assets[0] ? activeProject.assets[0].asset_id : null;
      activeVoiceAssetId = activeProject.voice_captures && activeProject.voice_captures[0] ? activeProject.voice_captures[0].asset_id : null;
      activeVoiceTranscript = null;
      activeCompositionId = activeProject.compositions && activeProject.compositions[0] ? activeProject.compositions[0].composition_id : null;
      const succeeded = (activeProject.renders || []).filter((render) => render.status === "succeeded");
      activeRenderId = succeeded.length ? succeeded[succeeded.length - 1].render_id : null;
      selectedPassages = new Map();
      selectedTranscriptSegments = new Set();
      resetGovernedDiscovery();
      invalidateGovernedPreview();
      renderProjects();
      renderProjectWorkspace();
      if (activeVoiceAssetId) {
        await loadVoiceTranscript(activeVoiceAssetId);
      }
    }

    function renderProjectWorkspace() {
      if (!activeProject) {
        projectSummaryEl.textContent = "No project selected";
        brandRequirementsEl.innerHTML = "";
        sourceListEl.innerHTML = `<div class="empty">Select or create a Project</div>`;
        passageListEl.innerHTML = "";
        clipListEl.innerHTML = "";
        compositionListEl.innerHTML = "";
        renderListEl.innerHTML = "";
        sourcePreviewEl.innerHTML = "";
        renderPreviewEl.innerHTML = "";
        voiceSourceListEl.innerHTML = "";
        voiceTranscriptListEl.innerHTML = "";
        renderGovernedDraftPanel();
        return;
      }
      const summary = activeProject.summary || {};
      const brand = activeProject.brand || {};
      projectSummaryEl.innerHTML = `${escapeHtml(activeProject.title)} | ${escapeHtml(brand.display_name || activeProject.brand_id || "Letters of Light")} | ${summary.source_count || 0} sources | ${summary.output_count || 0} outputs | ${summary.release_count || 0} releases`;
      renderBrandRequirements();
      renderSources();
      renderPassages();
      renderSourcePreview();
      renderClipControls();
      renderCompositionChoices();
      renderRenderChoices();
      renderVoiceSources();
      renderVoiceTranscript();
      renderGovernedDraftPanel();
    }

    function renderBrandRequirements() {
      if (!activeProject) {
        brandRequirementsEl.innerHTML = "";
        return;
      }
      const brand = activeProject.brand || {};
      const requirements = activeProject.release_requirements || {};
      const disabled = Array.isArray(requirements.disabled_reasons) ? requirements.disabled_reasons : [];
      const fields = Array.isArray(requirements.required_review_fields) ? requirements.required_review_fields : [];
      const targets = requirements.available_release_targets || activeProject.release_targets || {};
      const targetBadges = Object.entries(targets).map(([target, enabled]) => {
        return `<span>${escapeHtml(target)} ${enabled ? "on" : "off"}</span>`;
      }).join("");
      const fieldControls = fields.map((field) => {
        const key = field.field || "";
        const value = (activeProject.review_fields || {})[key] || "";
        return `<label>${escapeHtml(field.label || key)}
          <textarea data-review-field="${escapeHtml(key)}" placeholder="${escapeHtml(field.description || "")}">${escapeHtml(value)}</textarea>
        </label>`;
      }).join("");
      const disabledHtml = disabled.length
        ? `<div class="readiness-row"><span>Release disabled</span><span>${escapeHtml(disabled.join("; "))}</span></div>`
        : `<div class="readiness-row"><span>Release gate</span>${badge("ready", "yes")}</div>`;
      brandRequirementsEl.innerHTML = `
        <div class="readiness-row"><span>Brand</span><span>${escapeHtml(brand.display_name || activeProject.brand_id)} ${badge(brand.status || "active", stateClass(brand.status || "active"))}</span></div>
        <div class="readiness-row"><span>Targets</span><span class="source-meta">${targetBadges}</span></div>
        ${disabledHtml}
        ${fieldControls}
      `;
    }

    function renderSources() {
      const assets = activeProject.assets || [];
      if (!assets.length) {
        sourceListEl.innerHTML = `<div class="empty">No imported sources</div>`;
        return;
      }
      sourceListEl.innerHTML = assets.map((asset) => {
        const active = asset.asset_id === activeAssetId ? "active" : "";
        const detail = asset.media_metadata && asset.media_metadata.duration_seconds
          ? `${Number(asset.media_metadata.duration_seconds).toFixed(2)}s`
          : `${asset.size_bytes || 0} bytes`;
        const status = asset.extraction_status || asset.probe_status || "";
        return `<button class="asset-row ${active}" type="button" data-asset="${escapeHtml(asset.asset_id)}">
          <strong>${escapeHtml(mediaIcon(asset))}: ${escapeHtml(asset.original_filename || asset.asset_id)}</strong>
          <span class="source-meta">
            <span>${escapeHtml(asset.media_type || "")}</span>
            <span>${escapeHtml(detail)}</span>
            <span>${escapeHtml(status)}</span>
          </span>
        </button>`;
      }).join("");
      sourceListEl.querySelectorAll("[data-asset]").forEach((button) => {
        button.addEventListener("click", () => {
          activeAssetId = button.dataset.asset;
          renderProjectWorkspace();
        });
      });
    }

    function activeAsset() {
      if (!activeProject) return null;
      return (activeProject.assets || []).find((asset) => asset.asset_id === activeAssetId) || null;
    }

    function governedHandoffEntries() {
      const index = activeProject && activeProject.governed_handoffs;
      if (!index || typeof index !== "object") return [];
      return Object.values(index).filter((entry) => entry && typeof entry === "object");
    }

    function matchingGovernedHandoff() {
      const proposalId = governedProposalId.value.trim();
      const draftIntent = governedDraftIntent.value.trim();
      if (!proposalId) return null;
      return governedHandoffEntries().find((entry) => {
        const matchesProposal = entry.proposal_id === proposalId;
        const matchesIntent = !draftIntent || entry.draft_intent_ref === draftIntent;
        return matchesProposal && matchesIntent;
      }) || null;
    }

    function governedInputKey() {
      return `${governedProposalId.value.trim()}::${governedDraftIntent.value.trim()}`;
    }

    function governedPreviewIsFresh() {
      return Boolean(governedPreview && governedPreviewKey === governedInputKey());
    }

    function selectedPassageKey() {
      return Array.from(selectedPassages.values()).map((passage) => {
        return passage.passage_id || `${passage.asset_id || passage.source_asset_id || ""}:${passage.passage_index || ""}`;
      }).sort().join("|");
    }

    function governedParentLetterContext() {
      const linked = governedPreviewIsFresh() && governedPreview ? (governedPreview.linked_letter || {}) : {};
      if (linked.available && linked.letter_id) {
        return {letter_id: linked.letter_id, title: linked.title || "", status: linked.status || "available"};
      }
      const matching = matchingGovernedHandoff();
      if (matching && matching.letter_id) {
        return {letter_id: matching.letter_id, title: matching.title || "", status: matching.status || "linked"};
      }
      return null;
    }

    function productionDerivativeSourceLetter() {
      return governedParentLetterContext();
    }

    function productionDerivativeDestinationBrand() {
      return activeProject ? (activeProject.brand_id || "") : "";
    }

    function productionDerivativeCandidateKey() {
      const source = productionDerivativeSourceLetter();
      return [
        activeProjectId(),
        source ? source.letter_id : "",
        productionDerivativeSourceHash.value.trim(),
        productionDerivativeDestinationBrand(),
        productionDerivativeIntent.value.trim(),
        productionDerivativeOperator.value.trim(),
        productionDerivativeTheme.value.trim()
      ].join("::");
    }

    function productionDerivativeCandidateIsFresh() {
      return Boolean(productionDerivativeCandidate && productionDerivativeCandidateKeyValue === productionDerivativeCandidateKey());
    }

    function invalidateProductionDerivative(render = true) {
      productionDerivativeCandidate = null;
      productionDerivativeCandidateKeyValue = "";
      productionDerivativeError = "";
      productionDerivativeApplied = null;
      if (render) renderGovernedDraftPanel();
    }

    function productionDerivativeStatusKey() {
      const source = productionDerivativeSourceLetter();
      return [activeProjectId(), source ? source.letter_id : ""].join("::");
    }

    function invalidateProductionDerivativeStatus(render = true) {
      productionDerivativeStatusPayload = null;
      productionDerivativeStatusKeyValue = "";
      productionDerivativeStatusError = "";
      productionDerivativeStatusInFlight = false;
      if (render) renderGovernedDraftPanel();
    }

    async function loadProductionDerivativeStatus(source) {
      const key = productionDerivativeStatusKey();
      if (!activeProjectId() || !source || !source.letter_id || productionDerivativeStatusInFlight) return;
      productionDerivativeStatusInFlight = true;
      productionDerivativeStatusError = "";
      renderProductionDerivativeStatusPanel();
      try {
        productionDerivativeStatusPayload = await api(
          `/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/${encodeURIComponent(source.letter_id)}/production-derivative-status`
        );
        productionDerivativeStatusKeyValue = key;
      } catch (error) {
        productionDerivativeStatusPayload = null;
        productionDerivativeStatusKeyValue = "";
        productionDerivativeStatusError = error.message;
      } finally {
        productionDerivativeStatusInFlight = false;
        renderGovernedDraftPanel();
      }
    }

    function outlinePreviewKey() {
      const parent = governedParentLetterContext();
      return [
        parent ? parent.letter_id : "",
        selectedPassageKey(),
        outlinePreviewIntent.value.trim(),
        outlineWriterNote.value.trim(),
        outlineFormatIntent.value.trim()
      ].join("::");
    }

    function outlinePreviewIsFresh() {
      return Boolean(outlinePreview && outlinePreviewKeyValue === outlinePreviewKey());
    }

    function invalidateProseCandidate(render = true) {
      if (proseCandidate && proseCandidate.status === "generated_candidate") proseCandidateStale = true;
      proseCandidate = null;
      proseCandidateKeyValue = "";
      proseCandidateError = "";
      proseAppliedChild = null;
      if (render) renderGovernedDraftPanel();
    }

    function invalidateOutlinePreview() {
      if (outlinePreview && outlinePreview.ready) outlinePreviewStale = true;
      outlinePreview = null;
      outlinePreviewKeyValue = "";
      outlinePreviewError = "";
      invalidateProseCandidate(false);
      invalidateProductionDerivative(false);
      invalidateProductionDerivativeStatus(false);
      renderGovernedDraftPanel();
    }

    function invalidateGovernedPreview() {
      if (outlinePreview && outlinePreview.ready) outlinePreviewStale = true;
      governedPreview = null;
      governedPreviewKey = "";
      governedPreviewError = "";
      outlinePreview = null;
      outlinePreviewKeyValue = "";
      outlinePreviewError = "";
      invalidateProseCandidate(false);
      invalidateProductionDerivative(false);
      invalidateProductionDerivativeStatus(false);
      renderGovernedDraftPanel();
    }

    function resetGovernedDiscovery() {
      governedDiscovery = null;
      governedDiscoveryInFlight = false;
    }

    function governedDiscoveryQuery() {
      const query = new URLSearchParams();
      const search = governedProposalSearch.value.trim();
      const draftIntent = governedDraftIntent.value.trim();
      if (search) query.set("q", search);
      if (draftIntent) query.set("draft_intent_ref", draftIntent);
      return query;
    }

    async function loadGovernedProposalDiscovery() {
      if (!activeProjectId()) {
        governedProposalDiscoveryStatus.textContent = "Select a project to find promoted proposals.";
        return;
      }
      governedDiscoveryInFlight = true;
      renderGovernedProposalDiscovery();
      try {
        const query = governedDiscoveryQuery();
        const suffix = query.toString() ? `?${query.toString()}` : "";
        governedDiscovery = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/proposals${suffix}`);
      } catch (error) {
        governedDiscovery = {error: error.message, actionable: [], needs_attention: []};
        workspaceStatusEl.textContent = error.message;
      } finally {
        governedDiscoveryInFlight = false;
        renderGovernedProposalDiscovery();
      }
    }

    const governedBlockerMessages = {
      missing_source_support: "This proposal does not yet include required source support.",
      missing_source_snapshot: "This proposal does not yet include a source snapshot reference.",
      missing_destination_brand: "This proposal does not identify a destination brand.",
      missing_destination_surface: "This proposal does not identify a destination surface.",
      missing_canonical_node: "This proposal is not connected to a visible canonical content node.",
      missing_origin_brand: "This proposal does not identify an origin brand.",
      missing_promotion_ref: "This proposal is missing promotion handoff context.",
      missing_draft_intent_context: "This proposal does not yet provide draft-intent context.",
      missing_proposal_intent: "This proposal is missing proposal intent context.",
      incompatible_project_brand: "This proposal is for a different brand than the selected project.",
      project_brand_missing: "The selected project does not identify a brand.",
      linked_draft_unavailable: "A linked draft exists, but it is no longer available to open.",
      draft_brief_blocked: "This proposal is missing required governed drafting information.",
      invalid_promotion_state: "This proposal is not currently promoted for draft handoff.",
      proposal_blocked: "This proposal is not ready for governed draft handoff."
    };

    function governedBlockerMessage(blocker) {
      const code = blocker && blocker.code ? String(blocker.code) : "proposal_blocked";
      return governedBlockerMessages[code] || (blocker && blocker.message ? String(blocker.message) : "This proposal needs attention before it can be opened.");
    }

    function governedBlockerList(blockers) {
      if (!Array.isArray(blockers) || !blockers.length) return "<span>none</span>";
      return `<span class="governed-blocker-list">${
        blockers.map((blocker) => {
          const code = blocker && blocker.code ? String(blocker.code) : "proposal_blocked";
          return `<span class="governed-blocker-message">${escapeHtml(governedBlockerMessage(blocker))}<span class="governed-blocker-code">(${escapeHtml(code)})</span></span>`;
        }).join("")
      }</span>`;
    }

    const outlineBlockerMessages = {
      selected_source_passages_required: "Select source passages before previewing a source-grounded outline.",
      selected_source_asset_refs_required: "Selected source passages must identify their source assets.",
      source_grounding_required: "The parent governed handoff is missing source grounding.",
      source_support_refs_required: "The parent governed handoff is missing source support references.",
      source_snapshot_ref_required: "The parent governed handoff is missing a source snapshot reference.",
      governed_handoff_metadata_required: "Open or select a governed handoff Letter before previewing an outline.",
      horizon_proposal_missing: "Governed semantic context is unavailable for this proposal.",
      thesis_or_claim_required: "Governed thesis context is unavailable.",
      reason_now_required: "Governed reason-now context is unavailable.",
      source_grounded_preview_id_mismatch: "Preview inputs changed. Run Preview Grounded Outline again before accepting.",
      accepted_child_unavailable: "An accepted child draft is recorded, but the Letter is no longer available.",
      blocked: "This outline preview needs attention before it can be accepted."
    };

    function outlineBlockerMessage(blocker) {
      const code = blocker && blocker.code ? String(blocker.code) : "blocked";
      return outlineBlockerMessages[code] || governedBlockerMessage(blocker);
    }

    function outlineBlockerList(blockers) {
      if (!Array.isArray(blockers) || !blockers.length) return "<span>none</span>";
      return `<span class="governed-blocker-list">${
        blockers.map((blocker) => {
          const code = blocker && blocker.code ? String(blocker.code) : "blocked";
          return `<span class="governed-blocker-message">${escapeHtml(outlineBlockerMessage(blocker))}<span class="governed-blocker-code">(${escapeHtml(code)})</span></span>`;
        }).join("")
      }</span>`;
    }

    function proposalDiscoveryRow(item, actionable) {
      const blockers = Array.isArray(item.blockers) ? item.blockers : [];
      const linked = item.linked_letter || {};
      const linkedBadge = linked.exists
        ? badge(linked.available ? "linked" : "link unavailable", linked.available ? "yes" : "no")
        : "";
      const selectButton = actionable
        ? `<button class="secondary" type="button" data-governed-select-proposal="${escapeHtml(item.proposal_id || "")}">Select</button>`
        : "";
      const copyButton = `<button class="secondary" type="button" data-governed-copy-proposal="${escapeHtml(item.proposal_id || "")}">Copy ID</button>`;
      const blockerLine = blockers.length ? `<div class="path">${governedBlockerList(blockers)}</div>` : "";
      return `
        <article class="governed-proposal-row">
          <div class="governed-proposal-title">${escapeHtml(item.thesis_or_claim || item.proposal_id || "Governed proposal")}</div>
          <div class="source-meta">
            ${badge(item.content_job || "job", stateClass(item.content_job || "ready"))}
            ${badge(item.horizon_class || "horizon", "state-pending")}
            ${badge(item.status_label || (actionable ? "Ready" : "Needs attention"), actionable ? "yes" : "no")}
            ${linkedBadge}
          </div>
          <div class="path">${escapeHtml(item.destination_brand_ref || "")} / ${escapeHtml(item.destination_surface_ref || "")} | ${escapeHtml(item.source_support_reference_count || 0)} refs</div>
          ${blockerLine}
          <div class="governed-proposal-actions">
            ${selectButton}
            ${copyButton}
          </div>
        </article>
      `;
    }

    function renderGovernedProposalDiscovery() {
      if (!activeProject) {
        governedFindProposalsBtn.disabled = true;
        governedProposalResults.innerHTML = "";
        governedProposalDiscoveryStatus.textContent = "Select a project to find promoted proposals.";
        return;
      }
      governedFindProposalsBtn.disabled = governedDiscoveryInFlight;
      governedFindProposalsBtn.textContent = governedDiscoveryInFlight ? "Finding..." : "Find Governed Proposal";
      if (governedDiscoveryInFlight) {
        governedProposalDiscoveryStatus.textContent = "Finding promoted proposals";
        return;
      }
      if (!governedDiscovery) {
        governedProposalResults.innerHTML = "";
        governedProposalDiscoveryStatus.textContent = "Find promoted proposals for this project.";
        return;
      }
      if (governedDiscovery.error) {
        governedProposalResults.innerHTML = "";
        governedProposalDiscoveryStatus.textContent = governedDiscovery.error;
        return;
      }
      const actionable = Array.isArray(governedDiscovery.actionable) ? governedDiscovery.actionable : [];
      const needsAttention = Array.isArray(governedDiscovery.needs_attention) ? governedDiscovery.needs_attention : [];
      governedProposalDiscoveryStatus.textContent = `${actionable.length} actionable; ${needsAttention.length} needs attention`;
      const actionableHtml = actionable.length
        ? actionable.map((item) => proposalDiscoveryRow(item, true)).join("")
        : `<div class="empty">No actionable promoted proposals found for this project and filter.</div>`;
      const needsHtml = needsAttention.length
        ? needsAttention.map((item) => proposalDiscoveryRow(item, false)).join("")
        : `<div class="empty">No promoted proposals currently need attention for this project and filter.</div>`;
      governedProposalResults.innerHTML = `
        <section class="governed-proposal-section" id="governed-actionable-proposals">
          <div class="governed-proposal-section-title">Actionable</div>
          ${actionableHtml}
        </section>
        <section class="governed-proposal-section" id="governed-needs-attention-proposals">
          <div class="governed-proposal-section-title">Needs Attention</div>
          ${needsHtml}
        </section>
      `;
      governedProposalResults.querySelectorAll("button[data-governed-select-proposal]").forEach((button) => {
        button.addEventListener("click", () => {
          governedProposalId.value = button.dataset.governedSelectProposal || "";
          invalidateGovernedPreview();
          governedDraftStatus.textContent = "Check Proposal before opening; source passages are still required.";
        });
      });
      governedProposalResults.querySelectorAll("button[data-governed-copy-proposal]").forEach((button) => {
        button.addEventListener("click", async () => {
          const proposalId = button.dataset.governedCopyProposal || "";
          try {
            await navigator.clipboard.writeText(proposalId);
            governedProposalDiscoveryStatus.textContent = `Copied ${proposalId}`;
          } catch (error) {
            governedProposalDiscoveryStatus.textContent = proposalId;
          }
        });
      });
    }

    function governedContextRows() {
      if (!governedPreviewIsFresh()) {
        const proposalId = governedProposalId.value.trim();
        const selectedCount = selectedPassages.size;
        return `
          <div class="readiness-row"><span>Proposal</span><span>${escapeHtml(proposalId || "required")}</span></div>
          <div class="readiness-row"><span>Selected support</span><span>${escapeHtml(selectedCount)} source passages</span></div>
          <div class="governed-disclosure">Check Proposal validates governed state, lineage, source snapshot, brands, and source grounding before opening a draft.</div>
        `;
      }
      const context = governedPreview || {};
      const linked = context.linked_letter || {};
      const blockers = Array.isArray(context.blockers) ? context.blockers : [];
      const blockerHtml = governedBlockerList(blockers);
      const linkedLabel = linked.exists
        ? `${linked.available ? "available" : "unavailable"} ${linked.letter_id || ""}`
        : "none";
      const sourceStep = selectedPassages.size
        ? `${selectedPassages.size} source passages selected`
        : "Select source passages before opening this governed draft.";
      return `
        <div class="readiness-row"><span>Proposal</span><span>${escapeHtml(context.proposal_id || "")}</span></div>
        <div class="readiness-row"><span>Thesis or claim</span><span>${escapeHtml(context.thesis_or_claim || "")}</span></div>
        <div class="readiness-row"><span>Content job</span><span>${escapeHtml(context.content_job || "")}</span></div>
        <div class="readiness-row"><span>Destination</span><span>${escapeHtml(context.destination_brand_ref || "")} / ${escapeHtml(context.destination_surface_ref || "")}</span></div>
        <div class="readiness-row"><span>Source support</span><span>${escapeHtml(context.source_support_reference_count || 0)} refs</span></div>
        <div class="readiness-row"><span>Snapshot</span><span>${escapeHtml(context.source_snapshot_ref || "")}</span></div>
        <div class="readiness-row"><span>Promotion/readiness</span><span>${escapeHtml(context.promotion_state || "")} / ${escapeHtml(context.readiness_state || "")}</span></div>
        <div class="readiness-row"><span>Blockers</span><span class="source-meta">${blockerHtml}</span></div>
        <div class="readiness-row"><span>Source step</span><span>${escapeHtml(sourceStep)}</span></div>
        <div class="readiness-row"><span>Existing linked Letter</span><span>${escapeHtml(linkedLabel)}</span></div>
      `;
    }

    function outlineSelectedPassages() {
      return sortedPassages(Array.from(selectedPassages.values()));
    }

    function outlineRequestBody(parent) {
      const selected = outlineSelectedPassages();
      const assetIds = [];
      selected.forEach((passage) => {
        const assetId = passage.asset_id || passage.source_asset_id || "";
        if (assetId && !assetIds.includes(assetId)) assetIds.push(assetId);
      });
      return {
        parent_letter_id: parent ? parent.letter_id : "",
        selected_passages: selected,
        selected_source_asset_ids: assetIds,
        preview_intent_ref: outlinePreviewIntent.value.trim(),
        writer_note: outlineWriterNote.value.trim(),
        format_intent: outlineFormatIntent.value.trim(),
        actor_ref: "operator.local"
      };
    }

    function outlineSectionsHtml(sections) {
      if (!Array.isArray(sections) || !sections.length) return `<div class="empty">No outline sections returned.</div>`;
      return sections.map((item) => {
        const refs = Array.isArray(item.selected_passage_refs) && item.selected_passage_refs.length
          ? ` | refs: ${item.selected_passage_refs.map((ref) => escapeHtml(ref)).join(", ")}`
          : "";
        return `<div class="readiness-row"><span>${escapeHtml(item.label || item.item_type || "Outline item")}</span><span>${escapeHtml(item.role || "")} ${badge(item.claim_classification || "context", stateClass(item.claim_classification || "context"))}${refs}</span></div>`;
      }).join("");
    }

    function outlinePreviewRows() {
      const parent = governedParentLetterContext();
      if (!outlinePreviewIsFresh()) {
        return `
          <div class="readiness-row"><span>Parent Letter</span><span>${escapeHtml(parent ? parent.letter_id : "open governed draft first")}</span></div>
          <div class="readiness-row"><span>Selected passages</span><span>${escapeHtml(selectedPassages.size)} selected</span></div>
          <div class="readiness-row"><span>Preview intent</span><span>${escapeHtml(outlinePreviewIntent.value.trim() || "required")}</span></div>
        `;
      }
      const preview = outlinePreview || {};
      const governed = preview.governed_context || {};
      const parentLetter = preview.parent_letter || {};
      const existingChild = preview.existing_child || {};
      const childLabel = existingChild.exists
        ? `${existingChild.available ? "available" : "unavailable"} ${existingChild.child_letter_id || ""}`
        : "none";
      const classifications = Array.isArray(preview.claim_classifications) && preview.claim_classifications.length
        ? preview.claim_classifications.join(", ")
        : "none";
      const provenance = Array.isArray(preview.provenance_limitations) && preview.provenance_limitations.length
        ? preview.provenance_limitations.join("; ")
        : "none";
      return `
        <div class="readiness-row"><span>Parent Letter</span><span>${escapeHtml(parentLetter.letter_id || "")} ${escapeHtml(parentLetter.title || "")}</span></div>
        <div class="readiness-row"><span>Proposal / canonical node</span><span>${escapeHtml(governed.proposal_id || preview.proposal_id || "")} / ${escapeHtml(governed.canonical_node_id || preview.canonical_node_id || "")}</span></div>
        <div class="readiness-row"><span>Thesis or claim</span><span>${escapeHtml(governed.thesis_or_claim || preview.thesis_or_claim || "")}</span></div>
        <div class="readiness-row"><span>Reason now</span><span>${escapeHtml(governed.reason_now || preview.reason_now || "")}</span></div>
        <div class="readiness-row"><span>Destination</span><span>${escapeHtml(governed.destination_brand_ref || preview.destination_brand_ref || "")} / ${escapeHtml(governed.destination_surface_ref || preview.destination_surface_ref || "")}</span></div>
        <div class="readiness-row"><span>Source snapshot</span><span>${escapeHtml(governed.source_snapshot_ref || preview.source_snapshot_ref || "")}</span></div>
        <div class="readiness-row"><span>Selected passages</span><span>${escapeHtml(preview.selected_passage_count || 0)} passages</span></div>
        <div class="readiness-row"><span>Semantic status</span><span>${escapeHtml(preview.semantic_resolution_status || "")}</span></div>
        <div class="readiness-row"><span>Claim classifications</span><span>${escapeHtml(classifications)}</span></div>
        <div class="readiness-row"><span>Provenance limits</span><span>${escapeHtml(provenance)}</span></div>
        <div class="readiness-row"><span>Blockers</span><span class="source-meta">${outlineBlockerList(preview.blockers || [])}</span></div>
        <div class="readiness-row"><span>Accepted child</span><span>${escapeHtml(childLabel)}</span></div>
        <div class="readiness-row"><span>Preview ID</span><span>${escapeHtml(preview.preview_id || "")}</span></div>
        <div class="outline-section-list">${outlineSectionsHtml(preview.outline_sections || preview.outline_items || [])}</div>
      `;
    }

    function proseSelectedPassageRefs() {
      return sortedPassages(Array.from(selectedPassages.values())).map((passage) => {
        return passage.passage_id || `${passage.asset_id || passage.source_asset_id || ""}:passage:${passage.passage_index || "selected"}`;
      }).filter(Boolean);
    }

    function proseSelectedAssetIds() {
      const ids = [];
      sortedPassages(Array.from(selectedPassages.values())).forEach((passage) => {
        const assetId = passage.asset_id || passage.source_asset_id || "";
        if (assetId && !ids.includes(assetId)) ids.push(assetId);
      });
      return ids;
    }

    function proseScaffoldOptions() {
      const options = [];
      const seen = new Set();
      function add(letterId, label) {
        if (!letterId || seen.has(letterId)) return;
        seen.add(letterId);
        options.push({letter_id: letterId, label: label || letterId});
      }
      if (outlinePreviewIsFresh() && outlinePreview) {
        const existingChild = outlinePreview.existing_child || {};
        if (existingChild.available && existingChild.child_letter_id) {
          add(existingChild.child_letter_id, existingChild.title || existingChild.child_letter_id);
        }
      }
      const outputs = activeProject && Array.isArray(activeProject.letter_outputs) ? activeProject.letter_outputs : [];
      outputs.forEach((output) => {
        const letterId = output.letter_id || "";
        if (letterId && (output.source_grounded_acceptance_id || output.accepted_preview_id || String(letterId).startsWith("source_grounded_letter"))) {
          add(letterId, output.theme || letterId);
        }
      });
      return options;
    }

    function proseOutlineSections() {
      if (outlinePreviewIsFresh() && outlinePreview) {
        return outlinePreview.outline_sections || outlinePreview.outline_items || [];
      }
      return [];
    }

    function syncProseCandidateControls() {
      const selectedScaffold = proseScaffoldLetter.value;
      const scaffoldOptions = proseScaffoldOptions();
      proseScaffoldLetter.innerHTML = scaffoldOptions.length
        ? scaffoldOptions.map((item) => `<option value="${escapeHtml(item.letter_id)}">${escapeHtml(item.label || item.letter_id)}</option>`).join("")
        : `<option value="">Accept an outline child first</option>`;
      if (selectedScaffold && scaffoldOptions.some((item) => item.letter_id === selectedScaffold)) {
        proseScaffoldLetter.value = selectedScaffold;
      }

      const selectedSection = proseOutlineSection.value;
      const sections = proseOutlineSections();
      proseOutlineSection.innerHTML = sections.length
        ? sections.map((item) => `<option value="${escapeHtml(item.item_id || "")}">${escapeHtml(item.label || item.item_type || item.item_id || "Outline section")}</option>`).join("")
        : `<option value="">Preview an outline first</option>`;
      if (selectedSection && sections.some((item) => item.item_id === selectedSection)) {
        proseOutlineSection.value = selectedSection;
      }
    }

    function proseCandidateKey() {
      return [
        proseScaffoldLetter.value.trim(),
        proseOutlineSection.value.trim(),
        selectedPassageKey(),
        proseCandidateIntent.value.trim(),
        proseWriterInstruction.value.trim(),
        proseFormatConstraint.value.trim()
      ].join("::");
    }

    function proseCandidateIsFresh() {
      return Boolean(proseCandidate && proseCandidateKeyValue === proseCandidateKey());
    }

    function proseCandidateRequestBody() {
      return {
        accepted_scaffold_letter_id: proseScaffoldLetter.value.trim(),
        accepted_outline_section_id: proseOutlineSection.value.trim(),
        selected_source_asset_ids: proseSelectedAssetIds(),
        selected_source_passage_refs: proseSelectedPassageRefs(),
        candidate_intent_ref: proseCandidateIntent.value.trim(),
        requested_length_or_format: proseFormatConstraint.value.trim(),
        writer_instruction: proseWriterInstruction.value.trim(),
        actor_ref: "operator.local"
      };
    }

    function proseAnnotationRows(annotations) {
      if (!Array.isArray(annotations) || !annotations.length) return `<div class="empty">No annotations returned.</div>`;
      return annotations.map((item) => {
        const support = []
          .concat(Array.isArray(item.supporting_source_refs) ? item.supporting_source_refs : [])
          .concat(Array.isArray(item.supporting_passage_refs) ? item.supporting_passage_refs : [])
          .join(", ");
        return `<div class="readiness-row"><span>${escapeHtml(item.classification || "annotation")}</span><span>${escapeHtml(item.support_status || "")} ${support ? `| ${escapeHtml(support)}` : ""}</span></div>`;
      }).join("");
    }

    function proseCandidateRows() {
      const candidateFresh = proseCandidateIsFresh();
      if (!candidateFresh) {
        return `
          <div class="readiness-row"><span>Accepted scaffold</span><span>${escapeHtml(proseScaffoldLetter.value.trim() || "required")}</span></div>
          <div class="readiness-row"><span>Outline section</span><span>${escapeHtml(proseOutlineSection.value.trim() || "required")}</span></div>
          <div class="readiness-row"><span>Selected passages</span><span>${escapeHtml(selectedPassages.size)} selected</span></div>
          <div class="readiness-row"><span>Candidate intent</span><span>${escapeHtml(proseCandidateIntent.value.trim() || "required")}</span></div>
        `;
      }
      const candidate = proseCandidate || {};
      const section = candidate.outline_section_target || {};
      const grounding = candidate.selected_grounding_summary || {};
      const lineage = candidate.immutable_lineage_summary || {};
      const annotations = candidate.segment_annotations || [];
      const warnings = Array.isArray(candidate.warnings) && candidate.warnings.length ? candidate.warnings.join(", ") : "none";
      const limitations = Array.isArray(candidate.provenance_limitations) && candidate.provenance_limitations.length ? candidate.provenance_limitations.join("; ") : "none";
      const refs = []
        .concat(Array.isArray(candidate.used_source_refs) ? candidate.used_source_refs : [])
        .concat(Array.isArray(candidate.used_passage_refs) ? candidate.used_passage_refs : [])
        .join(", ") || "none";
      const expiresAt = candidate.expires_at || (candidate.candidate_envelope && candidate.candidate_envelope.payload ? candidate.candidate_envelope.payload.expires_at : "");
      return `
        <div class="readiness-row"><span>Status</span><span>${escapeHtml(candidate.status || "")}</span></div>
        <div class="readiness-row"><span>Section target</span><span>${escapeHtml(section.label || section.section_id || "")} ${badge(section.claim_classification || "draft", stateClass(section.claim_classification || "draft"))}</span></div>
        <div class="readiness-row"><span>Proposal / canonical node</span><span>${escapeHtml(lineage.proposal_id || "")} / ${escapeHtml(lineage.canonical_node_id || "")}</span></div>
        <div class="readiness-row"><span>Source snapshot</span><span>${escapeHtml(grounding.source_snapshot_ref || lineage.source_snapshot_ref || "")}</span></div>
        <div class="readiness-row"><span>Used refs</span><span>${escapeHtml(refs)}</span></div>
        <div class="readiness-row"><span>Warnings</span><span>${escapeHtml(warnings)}</span></div>
        <div class="readiness-row"><span>Provenance limits</span><span>${escapeHtml(limitations)}</span></div>
        <div class="readiness-row"><span>Envelope</span><span>${escapeHtml(expiresAt ? `expires ${expiresAt}` : "unavailable")}</span></div>
        <div class="readiness-row"><span>Direct quotations</span><span>unavailable in this version</span></div>
        <div class="outline-section-list">${proseAnnotationRows(annotations)}</div>
        <div class="candidate-preview"><strong>Draft candidate</strong><pre>${escapeHtml(candidate.candidate_text || "")}</pre></div>
        <div class="readiness-row"><span>Blockers</span><span class="source-meta">${outlineBlockerList(candidate.blockers || [])}</span></div>
      `;
    }

    function renderProseCandidatePanel() {
      if (!activeProject) {
        proseCandidateContext.innerHTML = "";
        proseGenerateActionBtn.disabled = true;
        proseApplyActionBtn.disabled = true;
        proseOpenAppliedChildBtn.disabled = true;
        proseOpenAppliedChildBtn.dataset.openUrl = "";
        proseCandidateStatus.textContent = "Select a project before generating a grounded prose candidate.";
        return;
      }
      syncProseCandidateControls();
      const hasScaffold = Boolean(proseScaffoldLetter.value.trim());
      const hasSection = Boolean(proseOutlineSection.value.trim());
      const hasPassages = selectedPassages.size > 0;
      const hasCandidateIntent = Boolean(proseCandidateIntent.value.trim());
      const hasFormat = Boolean(proseFormatConstraint.value.trim());
      const hasApplyIntent = Boolean(proseApplyIntent.value.trim());
      const candidateFresh = proseCandidateIsFresh();
      const candidateGenerated = Boolean(candidateFresh && proseCandidate && proseCandidate.status === "generated_candidate" && proseCandidate.candidate_envelope);
      const appliedChild = proseAppliedChild || {};
      const appliedAvailable = Boolean(appliedChild.available && appliedChild.open_url);
      proseCandidateContext.innerHTML = proseCandidateRows();
      proseGenerateActionBtn.disabled = proseCandidateInFlight || !hasScaffold || !hasSection || !hasPassages || !hasCandidateIntent || !hasFormat;
      proseGenerateActionBtn.textContent = proseCandidateInFlight ? "Generating..." : "Generate Grounded Candidate";
      proseApplyActionBtn.disabled = proseApplyInFlight || !candidateGenerated || !hasApplyIntent || appliedAvailable;
      proseApplyActionBtn.textContent = proseApplyInFlight ? "Applying..." : "Apply Candidate to Child Draft";
      proseOpenAppliedChildBtn.disabled = !appliedAvailable;
      proseOpenAppliedChildBtn.dataset.openUrl = appliedAvailable ? appliedChild.open_url : "";
      if (proseCandidateInFlight) {
        proseCandidateStatus.textContent = "Generating grounded draft candidate";
      } else if (proseApplyInFlight) {
        proseCandidateStatus.textContent = "Applying candidate to child draft";
      } else if (proseCandidateStale || (proseCandidate && !candidateFresh)) {
        proseCandidateStatus.textContent = "Candidate is stale. Generate a new grounded candidate before applying it.";
      } else if (!hasScaffold) {
        proseCandidateStatus.textContent = "Accept or select a source-grounded scaffold child before generating prose.";
      } else if (!hasSection) {
        proseCandidateStatus.textContent = "Select one accepted outline section.";
      } else if (!hasPassages) {
        proseCandidateStatus.textContent = "Select source passages before generating a grounded candidate.";
      } else if (!hasCandidateIntent) {
        proseCandidateStatus.textContent = "Enter a candidate intent before generation.";
      } else if (proseCandidateError) {
        proseCandidateStatus.textContent = proseCandidateError;
      } else if (appliedAvailable) {
        proseCandidateStatus.textContent = `Open Existing Applied Draft: ${appliedChild.letter_id || ""}`;
      } else if (candidateGenerated) {
        proseCandidateStatus.textContent = "Candidate ready for review and explicit apply.";
      } else if (proseCandidate && proseCandidate.status && proseCandidate.status !== "generated_candidate") {
        const blockers = Array.isArray(proseCandidate.blockers) ? proseCandidate.blockers.map((item) => item.code).filter(Boolean).join(", ") : "";
        proseCandidateStatus.textContent = blockers ? `Grounded candidate blocked: ${blockers}` : `Grounded candidate ${proseCandidate.status}.`;
      } else {
        proseCandidateStatus.textContent = "Generate Grounded Candidate before applying.";
      }
    }

    function productionDerivativeRequestBody() {
      return {
        expected_source_body_hash: productionDerivativeSourceHash.value.trim(),
        promotion_intent_ref: productionDerivativeIntent.value.trim(),
        destination_brand_id: productionDerivativeDestinationBrand(),
        operator_ref: productionDerivativeOperator.value.trim(),
        target_theme: productionDerivativeTheme.value.trim(),
        operator_note: productionDerivativeNote.value.trim()
      };
    }

    function productionDerivativeLineageRows(lineage) {
      const summary = lineage || {};
      const handoffs = Array.isArray(summary.governed_handoff_ids) ? summary.governed_handoff_ids.join(", ") : "";
      const proposals = Array.isArray(summary.proposal_node_ids) ? summary.proposal_node_ids.join(", ") : "";
      const canonicals = Array.isArray(summary.canonical_node_ids) ? summary.canonical_node_ids.join(", ") : "";
      const snapshots = Array.isArray(summary.source_snapshot_refs) ? summary.source_snapshot_refs.join(", ") : "";
      const support = Array.isArray(summary.support_refs) ? summary.support_refs.join(", ") : "";
      return `
        <div class="readiness-row"><span>Governed handoff</span><span>${escapeHtml(handoffs || "required")}</span></div>
        <div class="readiness-row"><span>Proposal / canonical</span><span>${escapeHtml(proposals || "none")} / ${escapeHtml(canonicals || "none")}</span></div>
        <div class="readiness-row"><span>Source snapshot</span><span>${escapeHtml(snapshots || "required")}</span></div>
        <div class="readiness-row"><span>Support refs</span><span>${escapeHtml(support || "required")}</span></div>
      `;
    }

    function productionDerivativeRows() {
      const source = productionDerivativeSourceLetter();
      const candidateFresh = productionDerivativeCandidateIsFresh();
      const candidate = candidateFresh ? (productionDerivativeCandidate || {}) : {};
      const applied = productionDerivativeApplied || {};
      const warnings = Array.isArray(candidate.warnings) && candidate.warnings.length ? candidate.warnings.join(", ") : "none";
      const blockers = Array.isArray(candidate.blockers) ? candidate.blockers : [];
      const target = candidate.target_letter_id || applied.target_letter_id || "";
      const creationJob = applied.creation_job_id || "";
      const targetState = applied.target_lifecycle_state || "";
      return `
        <div class="readiness-row"><span>Source governed draft</span><span>${escapeHtml(source ? source.letter_id : "required")}</span></div>
        <div class="readiness-row"><span>Source body hash</span><span>${escapeHtml(candidate.source_body_hash || productionDerivativeSourceHash.value.trim() || "required")}</span></div>
        <div class="readiness-row"><span>Project context</span><span>${escapeHtml(activeProjectId() || "required")}</span></div>
        <div class="readiness-row"><span>Destination brand</span><span>${escapeHtml(productionDerivativeDestinationBrand() || "required")}</span></div>
        <div class="readiness-row"><span>Promotion intent</span><span>${escapeHtml(productionDerivativeIntent.value.trim() || "required")}</span></div>
        <div class="readiness-row"><span>Operator reference</span><span>${escapeHtml(productionDerivativeOperator.value.trim() || "required")}</span></div>
        ${productionDerivativeLineageRows(candidate.lineage_summary || {})}
        <div class="readiness-row"><span>Warnings</span><span>${escapeHtml(warnings)}</span></div>
        <div class="readiness-row"><span>Blockers</span><span class="source-meta">${outlineBlockerList(blockers)}</span></div>
        <div class="readiness-row"><span>Proposed target Letter</span><span>${escapeHtml(target || "validate first")}</span></div>
        <div class="readiness-row"><span>Creation job</span><span>${escapeHtml(creationJob || "not started")}</span></div>
        <div class="readiness-row"><span>Target pipeline state</span><span>${escapeHtml(targetState || "not started")}</span></div>
      `;
    }

    function renderProductionDerivativePanel() {
      if (!activeProject) {
        productionDerivativeContext.innerHTML = "";
        productionDerivativeValidateBtn.disabled = true;
        productionDerivativeCreateBtn.disabled = true;
        productionDerivativeStatus.textContent = "Select a project before validating a production derivative.";
        return;
      }
      const source = productionDerivativeSourceLetter();
      const hasSource = Boolean(source && source.letter_id);
      const hasHash = Boolean(productionDerivativeSourceHash.value.trim());
      const hasIntent = Boolean(productionDerivativeIntent.value.trim());
      const hasOperator = Boolean(productionDerivativeOperator.value.trim());
      const candidateFresh = productionDerivativeCandidateIsFresh();
      const candidateValid = Boolean(candidateFresh && productionDerivativeCandidate && productionDerivativeCandidate.validation_state === "valid" && productionDerivativeCandidate.candidate_envelope);
      const applied = Boolean(productionDerivativeApplied && productionDerivativeApplied.target_letter_id);
      productionDerivativeContext.innerHTML = productionDerivativeRows();
      productionDerivativeValidateBtn.disabled = productionDerivativeInFlight || !hasSource || !hasHash || !hasIntent || !hasOperator;
      productionDerivativeValidateBtn.textContent = productionDerivativeInFlight ? "Validating..." : "Validate Production Derivative";
      productionDerivativeCreateBtn.disabled = productionDerivativeApplyInFlight || !candidateValid || applied;
      productionDerivativeCreateBtn.textContent = productionDerivativeApplyInFlight ? "Creating..." : "Create Production Derivative";
      if (productionDerivativeInFlight) {
        productionDerivativeStatus.textContent = "Validating production derivative candidate";
      } else if (productionDerivativeApplyInFlight) {
        productionDerivativeStatus.textContent = "Creating production derivative";
      } else if (!hasSource) {
        productionDerivativeStatus.textContent = "Open or select a governed draft before validating.";
      } else if (!hasHash) {
        productionDerivativeStatus.textContent = "Enter the expected source body hash.";
      } else if (!hasIntent) {
        productionDerivativeStatus.textContent = "Enter a promotion intent reference.";
      } else if (!hasOperator) {
        productionDerivativeStatus.textContent = "Enter the operator reference.";
      } else if (productionDerivativeError) {
        productionDerivativeStatus.textContent = productionDerivativeError;
      } else if (applied) {
        productionDerivativeStatus.textContent = `Production derivative ready in normal pipeline: ${productionDerivativeApplied.target_letter_id}`;
      } else if (candidateValid) {
        productionDerivativeStatus.textContent = "Production derivative candidate validated for explicit creation.";
      } else if (productionDerivativeCandidate && !candidateFresh) {
        productionDerivativeStatus.textContent = "Production derivative candidate is stale. Validate again before creating.";
      } else {
        productionDerivativeStatus.textContent = "Validate Production Derivative before creating.";
      }
    }

    function productionDerivativeStatusRows(status) {
      if (!status || !status.promotion_found) {
        return `
          <div class="readiness-row"><span>Source governed draft</span><span>${escapeHtml(status ? status.source_letter_id || "" : "")}</span></div>
          <div class="readiness-row"><span>Promotion</span><span>none</span></div>
          <div class="readiness-row"><span>Target production derivative</span><span>not created</span></div>
        `;
      }
      const promotion = status.promotion || {};
      const target = status.target || {};
      const job = status.creation_job || {};
      const pipeline = status.pipeline || {};
      return `
        <div class="readiness-row"><span>Promotion ID</span><span>${escapeHtml(promotion.promotion_id || "")}</span></div>
        <div class="readiness-row"><span>Source governed draft</span><span>${escapeHtml(status.source_letter_id || "")}</span></div>
        <div class="readiness-row"><span>Source body hash</span><span>${escapeHtml(promotion.source_body_hash || "")}</span></div>
        <div class="readiness-row"><span>Promotion intent</span><span>${escapeHtml(promotion.promotion_intent_ref || "")}</span></div>
        <div class="readiness-row"><span>Destination brand</span><span>${escapeHtml(promotion.destination_brand_id || "")}</span></div>
        <div class="readiness-row"><span>Separate target</span><span>${escapeHtml(target.letter_id || "")}</span></div>
        <div class="readiness-row"><span>Target lifecycle</span><span>${escapeHtml(target.lifecycle_state || "")}</span></div>
        <div class="readiness-row"><span>Creation job</span><span>${escapeHtml(job.job_id || "")}</span></div>
        <div class="readiness-row"><span>Job status</span><span>${escapeHtml(job.status || "")}</span></div>
        <div class="readiness-row"><span>Pipeline state</span><span>${escapeHtml(pipeline.state || "")}</span></div>
        <div class="readiness-row"><span>Evaluation / registration</span><span>${escapeHtml(pipeline.evaluation_state || "")} / ${escapeHtml(pipeline.registration_state || "")}</span></div>
        <div class="readiness-row"><span>Release record</span><span>${escapeHtml(target.has_release_record ? "exists" : "none")}</span></div>
        <div class="readiness-row"><span>Release eligible</span><span>${escapeHtml(target.release_eligible ? "yes" : "no")}</span></div>
      `;
    }

    function renderProductionDerivativeStatusPanel() {
      if (!activeProject) {
        productionDerivativeStatusContext.innerHTML = "";
        productionDerivativeStatusState.textContent = "Select a project before inspecting production derivative status.";
        return;
      }
      const source = productionDerivativeSourceLetter();
      if (!source || !source.letter_id) {
        productionDerivativeStatusContext.innerHTML = "";
        productionDerivativeStatusState.textContent = "Open or select a governed draft to inspect production derivative status.";
        return;
      }
      const key = productionDerivativeStatusKey();
      const fresh = productionDerivativeStatusPayload && productionDerivativeStatusKeyValue === key;
      if (!fresh && !productionDerivativeStatusInFlight) {
        loadProductionDerivativeStatus(source);
      }
      if (productionDerivativeStatusInFlight) {
        productionDerivativeStatusContext.innerHTML = productionDerivativeStatusRows(productionDerivativeStatusPayload || {source_letter_id: source.letter_id, promotion_found: false});
        productionDerivativeStatusState.textContent = "Reading production derivative status";
        return;
      }
      if (productionDerivativeStatusError) {
        productionDerivativeStatusContext.innerHTML = productionDerivativeStatusRows({source_letter_id: source.letter_id, promotion_found: false});
        productionDerivativeStatusState.textContent = productionDerivativeStatusError;
        return;
      }
      const status = fresh ? productionDerivativeStatusPayload : {source_letter_id: source.letter_id, promotion_found: false};
      productionDerivativeStatusContext.innerHTML = productionDerivativeStatusRows(status);
      productionDerivativeStatusState.textContent = status.promotion_found
        ? "Production derivative status loaded."
        : "No production derivative has been created from this governed draft.";
    }

    function renderOutlinePreviewPanel() {
      if (!activeProject) {
        outlinePreviewContext.innerHTML = "";
        outlinePreviewActionBtn.disabled = true;
        outlineAcceptActionBtn.disabled = true;
        outlineOpenChildBtn.disabled = true;
        outlineOpenChildBtn.dataset.openUrl = "";
        outlinePreviewStatus.textContent = "Select a project before previewing an outline.";
        return;
      }
      const parent = governedParentLetterContext();
      const hasParent = Boolean(parent && parent.letter_id);
      const hasSelectedPassages = selectedPassages.size > 0;
      const hasIntent = Boolean(outlinePreviewIntent.value.trim());
      const previewFresh = outlinePreviewIsFresh();
      const existingChild = previewFresh && outlinePreview ? (outlinePreview.existing_child || {}) : {};
      const childUnavailable = Boolean(existingChild.exists && !existingChild.available);
      const childAvailable = Boolean(existingChild.available && existingChild.child_letter_id);
      const previewReady = Boolean(previewFresh && outlinePreview && outlinePreview.ready && outlinePreview.status === "ready" && !childUnavailable);
      outlinePreviewContext.innerHTML = outlinePreviewRows();
      outlinePreviewActionBtn.disabled = outlinePreviewInFlight || !hasParent || !hasSelectedPassages || !hasIntent;
      outlinePreviewActionBtn.textContent = outlinePreviewInFlight ? "Previewing..." : "Preview Grounded Outline";
      outlineAcceptActionBtn.disabled = outlineAcceptanceInFlight || !previewReady || childAvailable;
      outlineAcceptActionBtn.textContent = outlineAcceptanceInFlight ? "Accepting..." : "Accept Outline into Child Draft";
      outlineOpenChildBtn.disabled = !childAvailable;
      outlineOpenChildBtn.dataset.openUrl = childAvailable ? (existingChild.open_url || `/?letter_id=${existingChild.child_letter_id}`) : "";
      outlineOpenChildBtn.textContent = childAvailable ? "Open Existing Child Draft" : "Open Existing Child Draft";
      if (outlinePreviewInFlight) {
        outlinePreviewStatus.textContent = "Previewing source-grounded outline";
      } else if (outlineAcceptanceInFlight) {
        outlinePreviewStatus.textContent = "Accepting outline into child draft";
      } else if (outlinePreviewStale || (outlinePreview && !previewFresh)) {
        outlinePreviewStatus.textContent = "Preview is stale. Generate a new grounded outline before accepting it.";
      } else if (!hasParent) {
        outlinePreviewStatus.textContent = "Open or select the governed handoff Letter before previewing an outline.";
      } else if (!hasSelectedPassages) {
        outlinePreviewStatus.textContent = "Select source passages before previewing a source-grounded outline.";
      } else if (!hasIntent) {
        outlinePreviewStatus.textContent = "Enter an outline preview intent before previewing.";
      } else if (outlinePreviewError) {
        outlinePreviewStatus.textContent = outlinePreviewError;
      } else if (childUnavailable) {
        outlinePreviewStatus.textContent = "An accepted child draft is recorded, but the Letter is no longer available.";
      } else if (childAvailable) {
        outlinePreviewStatus.textContent = `Open Existing Child Draft: ${existingChild.child_letter_id}`;
      } else if (previewFresh && outlinePreview && !outlinePreview.ready) {
        const blockers = Array.isArray(outlinePreview.blockers) ? outlinePreview.blockers.map((item) => item.code).filter(Boolean).join(", ") : "";
        outlinePreviewStatus.textContent = blockers ? `Outline preview blocked: ${blockers}` : "Outline preview blocked.";
      } else if (previewReady) {
        outlinePreviewStatus.textContent = "Outline preview is ready for explicit acceptance.";
      } else {
        outlinePreviewStatus.textContent = "Preview Grounded Outline before accepting a child draft.";
      }
    }

    function renderGovernedDraftPanel() {
      if (!activeProject) {
        governedBriefContext.innerHTML = "";
        governedCheckProposalBtn.disabled = true;
        governedOpenDraftBtn.disabled = true;
        governedOpenExistingDraftBtn.disabled = true;
        governedOpenExistingDraftBtn.dataset.letterId = "";
        governedDraftStatus.textContent = "Select a project, proposal, draft intent, and source passages.";
        renderGovernedProposalDiscovery();
        renderOutlinePreviewPanel();
        renderProseCandidatePanel();
        renderProductionDerivativePanel();
        renderProductionDerivativeStatusPanel();
        return;
      }
      governedBriefContext.innerHTML = governedContextRows();
      const proposalId = governedProposalId.value.trim();
      const draftIntent = governedDraftIntent.value.trim();
      const previewFresh = governedPreviewIsFresh();
      const linked = previewFresh && governedPreview ? (governedPreview.linked_letter || {}) : {};
      const linkedUnavailable = Boolean(linked.exists && !linked.available);
      const existingLetterId = linked && linked.available && linked.letter_id ? linked.letter_id : "";
      const missingSourcePassages = !selectedPassages.size;
      const missing = [];
      if (!proposalId) missing.push("proposal ID required");
      if (!draftIntent) missing.push("draft intent required");
      if (!previewFresh) missing.push("check proposal first");
      if (previewFresh && governedPreview && !governedPreview.governed_brief_ready) missing.push("proposal blocked");
      if (missingSourcePassages) missing.push("select source passages before opening");
      governedCheckProposalBtn.disabled = governedContextInFlight || !proposalId || !draftIntent;
      governedCheckProposalBtn.textContent = governedContextInFlight ? "Checking..." : "Check Proposal";
      governedOpenDraftBtn.disabled = governedDraftInFlight || missing.length > 0 || linkedUnavailable;
      governedOpenDraftBtn.textContent = governedDraftInFlight ? "Opening..." : "Open Governed Draft";
      governedOpenExistingDraftBtn.disabled = !existingLetterId;
      governedOpenExistingDraftBtn.dataset.letterId = existingLetterId;
      if (governedContextInFlight) {
        governedDraftStatus.textContent = "Checking governed proposal";
      } else if (governedDraftInFlight) {
        governedDraftStatus.textContent = "Opening governed draft";
      } else if (governedPreviewError) {
        governedDraftStatus.textContent = governedPreviewError;
      } else if (existingLetterId && missingSourcePassages) {
        governedDraftStatus.textContent = `Select source passages before continuing this handoff. Linked draft already exists: ${existingLetterId}`;
      } else if (existingLetterId) {
        governedDraftStatus.textContent = `Existing governed draft linked: ${existingLetterId}`;
      } else if (linkedUnavailable) {
        governedDraftStatus.textContent = "Existing governed draft link is unavailable";
      } else {
        governedDraftStatus.textContent = missing.length ? missing.join("; ") : "Governed proposal checked and ready to open.";
      }
      renderGovernedProposalDiscovery();
      renderOutlinePreviewPanel();
      renderProseCandidatePanel();
      renderProductionDerivativePanel();
      renderProductionDerivativeStatusPanel();
    }

    function passageOrderKey(passage) {
      const page = passage.page_number === null || passage.page_number === undefined ? 999999 : Number(passage.page_number) || 0;
      const index = passage.passage_index === null || passage.passage_index === undefined ? 999999 : Number(passage.passage_index) || 0;
      return [page, index, String(passage.passage_id || "")];
    }

    function sortedPassages(passages) {
      return [...passages].sort((a, b) => {
        const left = passageOrderKey(a);
        const right = passageOrderKey(b);
        if (left[0] !== right[0]) return left[0] - right[0];
        if (left[1] !== right[1]) return left[1] - right[1];
        return left[2].localeCompare(right[2]);
      });
    }

    function passagePreview(text) {
      const normalized = String(text || "").replace(/\\s+/g, " ").trim();
      if (normalized.length <= 340) return normalized;
      return `${normalized.slice(0, 337).trim()}...`;
    }

    function updateSelectedPassageCount() {
      const count = selectedPassages.size;
      selectedPassageCountEl.textContent = `${count} selected`;
    }

    function visiblePassages() {
      const asset = activeAsset();
      const search = passageSearch.value.trim().toLowerCase();
      if (!asset || !asset.extracted || !Array.isArray(asset.extracted.passages)) {
        return [];
      }
      return sortedPassages(asset.extracted.passages).filter((passage) => {
        const haystack = `${passage.heading || ""} ${passage.text || ""}`.toLowerCase();
        return !search || haystack.includes(search);
      });
    }

    function renderRawExtractionDebug(asset) {
      const rawPages = asset && asset.extracted && Array.isArray(asset.extracted.raw_pages)
        ? asset.extracted.raw_pages
        : [];
      if (!rawPages.length) {
        rawExtractionDetails.style.display = "none";
        rawExtractionDebug.textContent = "";
        return;
      }
      rawExtractionDetails.style.display = "";
      rawExtractionDebug.textContent = rawPages.map((page) => {
        const fragments = Array.isArray(page.fragments) ? page.fragments : [];
        const sample = fragments.slice(0, 80).map((fragment) => {
          return `${fragment.fragment_index}: ${fragment.text}`;
        }).join("\\n");
        const suffix = fragments.length > 80 ? `\\n... ${fragments.length - 80} more fragments` : "";
        return `Page ${page.page_number} (${fragments.length} raw fragments)\\n${sample}${suffix}`;
      }).join("\\n\\n");
    }

    function renderPassages() {
      const asset = activeAsset();
      if (!asset || !asset.extracted || !Array.isArray(asset.extracted.passages) || !asset.extracted.passages.length) {
        passageListEl.innerHTML = `<div class="empty">No extracted PDF passage selection available</div>`;
        rawExtractionDetails.style.display = "none";
        updateSelectedPassageCount();
        renderGovernedDraftPanel();
        return;
      }
      renderRawExtractionDebug(asset);
      const passages = visiblePassages();
      passageListEl.innerHTML = passages.map((passage) => {
        const id = passage.passage_id || `${passage.asset_id}:${passage.passage_index}`;
        const checked = selectedPassages.has(id) ? "checked" : "";
        const page = passage.page_number ? `page ${passage.page_number}` : "source";
        const heading = passage.heading ? `<div class="passage-heading">${escapeHtml(passage.heading)}</div>` : "";
        const preview = passagePreview(passage.body_text || passage.text || "");
        const fullText = passage.text || "";
        return `<article class="passage-card" data-passage-card="${escapeHtml(id)}">
          <label>
            <input type="checkbox" ${checked} data-passage="${escapeHtml(id)}">
            <span>
              <span class="source-meta"><span>${escapeHtml(page)}</span><span>${escapeHtml(passage.classification || "passage")}</span></span>
              ${heading}
              <div class="passage-preview">${escapeHtml(preview)}</div>
            </span>
          </label>
          <details>
            <summary>Expand</summary>
            <div>${escapeHtml(fullText)}</div>
          </details>
        </article>`;
      }).join("") || `<div class="empty">No passages match</div>`;
      passageListEl.querySelectorAll("input[data-passage]").forEach((input) => {
        input.addEventListener("change", () => {
          const passage = passages.find((item) => (item.passage_id || `${item.asset_id}:${item.passage_index}`) === input.dataset.passage);
          if (!passage) return;
          if (input.checked) selectedPassages.set(input.dataset.passage, passage);
          else selectedPassages.delete(input.dataset.passage);
          buildProjectDraft();
          invalidateOutlinePreview();
        });
      });
      updateSelectedPassageCount();
      renderGovernedDraftPanel();
    }

    function buildProjectDraft() {
      const blocks = sortedPassages(Array.from(selectedPassages.values())).map((passage) => String(passage.text || "").trim()).filter(Boolean);
      projectDraft.value = blocks.join("\\n\\n");
      updateSelectedPassageCount();
      renderGovernedDraftPanel();
    }

    function renderSourcePreview() {
      const asset = activeAsset();
      if (!asset) {
        sourcePreviewEl.innerHTML = "";
        return;
      }
      const url = escapeHtml(asset.preview_url || "");
      const name = escapeHtml(asset.original_filename || asset.asset_id);
      if (asset.media_type === "video") {
        sourcePreviewEl.innerHTML = `<h3>Video Preview</h3><video class="preview-frame" controls src="${url}"></video>`;
      } else if (asset.media_type === "audio") {
        sourcePreviewEl.innerHTML = `<h3>Audio Preview</h3><audio controls src="${url}"></audio>`;
      } else if (asset.media_type === "image") {
        sourcePreviewEl.innerHTML = `<h3>Image Preview</h3><img class="preview-frame" src="${url}" alt="${name}">`;
      } else {
        sourcePreviewEl.innerHTML = `<h3>Source Metadata</h3><div class="source-meta"><span>${name}</span><span>${escapeHtml(asset.sha256 || "")}</span></div>`;
      }
    }

    function setVoiceMode(mode) {
      voiceMode = mode === "read_script" ? "read_script" : "free_talk";
      voiceFreeTalkBtn.classList.toggle("active", voiceMode === "free_talk");
      voiceReadScriptBtn.classList.toggle("active", voiceMode === "read_script");
      refreshVoiceReader();
    }

    function setVoiceState(state, message) {
      voiceStateEl.textContent = state;
      voiceStateEl.className = `badge ${stateClass(state)}`;
      voiceStatusEl.textContent = message || state;
    }

    function formatSeconds(value) {
      const seconds = Math.max(0, Math.floor(Number(value) || 0));
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    }

    function currentVoiceElapsed() {
      if (voiceRecorder && voiceRecorder.state === "recording") {
        return voiceElapsedBeforePause + ((Date.now() - voiceStartedAt) / 1000);
      }
      return voiceElapsedBeforePause;
    }

    function updateVoiceElapsed() {
      voiceElapsedEl.textContent = formatSeconds(currentVoiceElapsed());
    }

    function startVoiceElapsedTimer() {
      window.clearInterval(voiceElapsedTimer);
      voiceElapsedTimer = window.setInterval(updateVoiceElapsed, 250);
      updateVoiceElapsed();
    }

    function stopVoiceElapsedTimer() {
      window.clearInterval(voiceElapsedTimer);
      voiceElapsedTimer = null;
      updateVoiceElapsed();
    }

    function preferredAudioMimeType() {
      if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
      const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
      return candidates.find((value) => MediaRecorder.isTypeSupported(value)) || "";
    }

    function updateVoiceButtons() {
      const state = voiceRecorder ? voiceRecorder.state : "";
      voiceStartBtn.disabled = state === "recording" || state === "paused";
      voicePauseBtn.disabled = state !== "recording";
      voiceResumeBtn.disabled = state !== "paused";
      voiceStopBtn.disabled = !(state === "recording" || state === "paused");
      voiceDiscardBtn.disabled = !voiceBlob && !voiceRecorder;
      voiceSaveBtn.disabled = !voiceBlob;
    }

    function refreshVoiceReader() {
      const text = voiceMode === "read_script" ? voiceScriptText.value.trim() : "";
      voiceReader.textContent = text || (voiceMode === "read_script" ? "Paste or load text to use the reader." : "Free Talk mode keeps the reader open for optional notes.");
    }

    function loadScriptIntoReader(text, metadata = {}) {
      voiceScriptText.value = String(text || "").trim();
      voiceCanonicalScript = metadata || {};
      setVoiceMode("read_script");
      document.getElementById("voice-intake-title").scrollIntoView({behavior: "smooth", block: "start"});
    }

    function stopVoiceStream() {
      if (voiceStream) {
        voiceStream.getTracks().forEach((track) => track.stop());
        voiceStream = null;
      }
    }

    function discardVoiceCapture() {
      voiceDiscarding = true;
      if (voiceRecorder && voiceRecorder.state !== "inactive") {
        voiceRecorder.stop();
      }
      stopVoiceStream();
      voiceRecorder = null;
      voiceChunks = [];
      voiceBlob = null;
      voiceElapsedBeforePause = 0;
      if (voiceObjectUrl) {
        URL.revokeObjectURL(voiceObjectUrl);
        voiceObjectUrl = "";
      }
      voicePlayback.removeAttribute("src");
      stopVoiceElapsedTimer();
      setVoiceState("permission_required", "permission_required");
      updateVoiceButtons();
      window.setTimeout(() => { voiceDiscarding = false; }, 0);
    }

    async function startVoiceRecording() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
        setVoiceState("failed", "MediaRecorder microphone capture is not available in this browser");
        return;
      }
      discardVoiceCapture();
      voiceDiscarding = false;
      try {
        voiceStream = await navigator.mediaDevices.getUserMedia({audio: true});
        const mimeType = preferredAudioMimeType();
        voiceRecorder = new MediaRecorder(voiceStream, mimeType ? {mimeType} : undefined);
        voiceChunks = [];
        voiceBlob = null;
        voiceRecorder.addEventListener("dataavailable", (event) => {
          if (event.data && event.data.size > 0) voiceChunks.push(event.data);
        });
        voiceRecorder.addEventListener("stop", () => {
          if (voiceDiscarding) return;
          if (voiceRecorder && voiceRecorder.state === "recording") {
            voiceElapsedBeforePause = currentVoiceElapsed();
          }
          const type = voiceRecorder && voiceRecorder.mimeType ? voiceRecorder.mimeType : (mimeType || "audio/webm");
          voiceBlob = new Blob(voiceChunks, {type});
          if (voiceObjectUrl) URL.revokeObjectURL(voiceObjectUrl);
          voiceObjectUrl = URL.createObjectURL(voiceBlob);
          voicePlayback.src = voiceObjectUrl;
          stopVoiceStream();
          stopVoiceElapsedTimer();
          setVoiceState("ready", "ready for playback and save");
          updateVoiceButtons();
        });
        voiceStartedAt = Date.now();
        voiceElapsedBeforePause = 0;
        voiceRecorder.start();
        setVoiceState("recording", "recording");
        startVoiceElapsedTimer();
        updateVoiceButtons();
      } catch (error) {
        setVoiceState("failed", error.message || "microphone permission failed");
        stopVoiceStream();
        updateVoiceButtons();
      }
    }

    function pauseVoiceRecording() {
      if (!voiceRecorder || voiceRecorder.state !== "recording") return;
      voiceElapsedBeforePause = currentVoiceElapsed();
      voiceRecorder.pause();
      stopVoiceElapsedTimer();
      setVoiceState("paused", "paused");
      updateVoiceButtons();
    }

    function resumeVoiceRecording() {
      if (!voiceRecorder || voiceRecorder.state !== "paused") return;
      voiceStartedAt = Date.now();
      voiceRecorder.resume();
      setVoiceState("recording", "recording");
      startVoiceElapsedTimer();
      updateVoiceButtons();
    }

    function stopVoiceRecording() {
      if (!voiceRecorder || voiceRecorder.state === "inactive") return;
      if (voiceRecorder.state === "recording") {
        voiceElapsedBeforePause = currentVoiceElapsed();
      }
      voiceRecorder.stop();
      setVoiceState("processing", "processing recording");
      updateVoiceButtons();
    }

    async function saveVoiceCapture() {
      if (!voiceBlob) {
        setVoiceState("failed", "record before saving");
        return;
      }
      const data = new FormData();
      const extension = voiceBlob.type.includes("ogg") ? "ogg" : (voiceBlob.type.includes("mp4") ? "m4a" : "webm");
      data.append("file", voiceBlob, `${voiceMode}_${Date.now()}.${extension}`);
      data.append("capture_mode", voiceMode);
      data.append("duration_seconds", String(currentVoiceElapsed()));
      if (voiceMode === "read_script") {
        data.append("canonical_script_text", voiceScriptText.value.trim());
        data.append("canonical_script_source_reference", voiceCanonicalScript.source_reference || "voice_intake_reader");
        if (voiceCanonicalScript.source_asset_id) data.append("canonical_script_source_asset_id", voiceCanonicalScript.source_asset_id);
        if (voiceCanonicalScript.letter_id) data.append("canonical_script_letter_id", voiceCanonicalScript.letter_id);
        if (Array.isArray(voiceCanonicalScript.passage_ids)) data.append("canonical_script_passage_ids", JSON.stringify(voiceCanonicalScript.passage_ids));
      }
      const saveToActive = voiceSaveTarget.value === "active_project" && activeProjectId();
      if (!saveToActive) {
        data.append("brand_id", voiceBrand.value || "letters_of_light");
        data.append("title", voiceProjectTitle.value.trim() || "Voice Capture");
      }
      setVoiceState("processing", "saving recording");
      try {
        const path = saveToActive
          ? `/api/projects/${encodeURIComponent(activeProjectId())}/voice-captures`
          : "/api/voice-capture-project";
        const saved = await apiForm(path, data);
        activeProject = saved.project;
        activeVoiceAssetId = saved.asset.asset_id;
        try {
          await api(`/api/projects/${encodeURIComponent(activeProject.project_id)}/voice-captures/${encodeURIComponent(activeVoiceAssetId)}/transcribe`, {});
        } catch (error) {
          voiceStatusEl.textContent = `saved; transcript not queued: ${error.message}`;
        }
        discardVoiceCapture();
        await loadAll();
        setVoiceState("ready", "recording saved as project source");
      } catch (error) {
        setVoiceState("failed", error.message);
      }
    }

    function renderVoiceSources() {
      const captures = (activeProject && activeProject.voice_captures) || [];
      if (!captures.length) {
        voiceSourceListEl.innerHTML = `<div class="empty">No microphone recordings</div>`;
        return;
      }
      voiceSourceListEl.innerHTML = captures.map((asset) => {
        const active = asset.asset_id === activeVoiceAssetId ? "active" : "";
        const duration = asset.duration_seconds || (asset.media_metadata && asset.media_metadata.duration_seconds);
        const detail = duration ? `${Number(duration).toFixed(1)}s` : `${asset.size_bytes || 0} bytes`;
        return `<button class="asset-row ${active}" type="button" data-voice-asset="${escapeHtml(asset.asset_id)}">
          <strong>${escapeHtml(asset.capture_mode || "voice")}: ${escapeHtml(asset.original_filename || asset.asset_id)}</strong>
          <span class="source-meta">
            <span>${escapeHtml(detail)}</span>
            <span>${escapeHtml(asset.transcript_status || "not_started")}</span>
            <span>${escapeHtml(asset.recorded_at || "")}</span>
          </span>
        </button>`;
      }).join("");
      voiceSourceListEl.querySelectorAll("[data-voice-asset]").forEach((button) => {
        button.addEventListener("click", () => loadVoiceTranscript(button.dataset.voiceAsset));
      });
    }

    async function loadVoiceTranscript(assetId) {
      if (!activeProjectId() || !assetId) return;
      activeVoiceAssetId = assetId;
      selectedTranscriptSegments = new Set();
      activeVoiceTranscript = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/voice-captures/${encodeURIComponent(assetId)}/transcript`);
      renderVoiceSources();
      renderVoiceTranscript();
    }

    function transcriptTime(segment) {
      return `${formatSeconds(segment.start_seconds)}-${formatSeconds(segment.end_seconds)}`;
    }

    function renderVoiceTranscript() {
      if (!activeProject || !activeVoiceAssetId) {
        voiceTranscriptListEl.innerHTML = `<div class="empty">Select a voice source</div>`;
        return;
      }
      const transcript = activeVoiceTranscript || {};
      const status = transcript.transcript_status || transcript.status || "not_started";
      const edited = transcript.edited_transcript || {};
      const segments = Array.isArray(edited.segments) ? edited.segments : [];
      const error = transcript.error ? `<div class="path">${escapeHtml(transcript.error)}</div>` : "";
      if (!segments.length) {
        voiceTranscriptListEl.innerHTML = `<div class="empty">Transcript ${escapeHtml(status)}${error}</div>`;
        return;
      }
      voiceTranscriptListEl.innerHTML = `
        <div class="source-meta"><span>Transcript ${escapeHtml(status)}</span><span>${escapeHtml(segments.length)} segments</span></div>
        ${segments.map((segment, index) => {
          const id = segment.segment_id || `segment_${index + 1}`;
          const checked = selectedTranscriptSegments.has(id) ? "checked" : "";
          return `<div class="transcript-row">
            <input type="checkbox" ${checked} data-transcript-select="${escapeHtml(id)}">
            <span class="path">${escapeHtml(transcriptTime(segment))}</span>
            <textarea data-transcript-segment="${escapeHtml(id)}"
              data-index="${escapeHtml(segment.index || index + 1)}"
              data-start="${escapeHtml(segment.start_seconds || 0)}"
              data-end="${escapeHtml(segment.end_seconds || segment.start_seconds || 0)}"
              data-confidence="${escapeHtml(segment.confidence ?? "")}">${escapeHtml(segment.text || "")}</textarea>
          </div>`;
        }).join("")}
      `;
      voiceTranscriptListEl.querySelectorAll("[data-transcript-select]").forEach((input) => {
        input.addEventListener("change", () => {
          if (input.checked) selectedTranscriptSegments.add(input.dataset.transcriptSelect);
          else selectedTranscriptSegments.delete(input.dataset.transcriptSelect);
        });
      });
    }

    function collectEditedTranscriptSegments() {
      return Array.from(voiceTranscriptListEl.querySelectorAll("textarea[data-transcript-segment]")).map((textarea) => {
        return {
          segment_id: textarea.dataset.transcriptSegment,
          index: Number(textarea.dataset.index) || 0,
          start_seconds: Number(textarea.dataset.start) || 0,
          end_seconds: Number(textarea.dataset.end) || 0,
          confidence: textarea.dataset.confidence === "" ? null : Number(textarea.dataset.confidence),
          text: textarea.value.trim()
        };
      }).filter((segment) => segment.text);
    }

    function selectedTranscriptIds() {
      return Array.from(selectedTranscriptSegments);
    }

    function selectedTranscriptText() {
      const ids = selectedTranscriptIds();
      const segments = collectEditedTranscriptSegments().filter((segment) => ids.includes(segment.segment_id));
      return segments.map((segment) => segment.text).filter(Boolean).join("\\n\\n");
    }

    function assetOptions(type) {
      const assets = (activeProject && activeProject.assets) || [];
      const options = [`<option value="">None</option>`];
      assets.filter((asset) => asset.media_type === type).forEach((asset) => {
        options.push(`<option value="${escapeHtml(asset.asset_id)}">${escapeHtml(asset.original_filename || asset.asset_id)}</option>`);
      });
      return options.join("");
    }

    function renderClipControls() {
      const videos = ((activeProject && activeProject.assets) || []).filter((asset) => asset.media_type === "video");
      if (!videos.length) {
        clipListEl.innerHTML = `<div class="empty">Import video to create a composition</div>`;
      } else {
        clipListEl.innerHTML = videos.map((asset, index) => {
          return `<div class="asset-row" data-clip-row="${escapeHtml(asset.asset_id)}">
            <label><input type="checkbox" data-clip-asset="${escapeHtml(asset.asset_id)}"> ${escapeHtml(asset.original_filename || asset.asset_id)}</label>
            <div class="compact-grid">
              <input type="number" min="0" step="0.1" data-clip-in="${escapeHtml(asset.asset_id)}" value="0" aria-label="in point">
              <input type="number" min="0" step="0.1" data-clip-out="${escapeHtml(asset.asset_id)}" placeholder="out" aria-label="out point">
              <input type="number" min="1" step="1" data-clip-order="${escapeHtml(asset.asset_id)}" value="${index + 1}" aria-label="order">
            </div>
          </div>`;
        }).join("");
      }
      compositionImage.innerHTML = assetOptions("image");
      compositionVoice.innerHTML = assetOptions("audio");
      compositionMusic.innerHTML = assetOptions("audio");
    }

    function renderCompositionChoices() {
      const compositions = (activeProject && activeProject.compositions) || [];
      if (!compositions.length) {
        compositionListEl.innerHTML = `<div class="empty">No compositions</div>`;
        return;
      }
      compositionListEl.innerHTML = compositions.map((composition) => {
        const active = composition.composition_id === activeCompositionId ? "active" : "";
        return `<button class="composition-row ${active}" type="button" data-composition="${escapeHtml(composition.composition_id)}">
          <strong>${escapeHtml(composition.title || composition.composition_id)}</strong>
          <span class="source-meta"><span>${escapeHtml(composition.aspect_ratio || "")}</span><span>${escapeHtml(composition.clip_count || 0)} clips</span></span>
        </button>`;
      }).join("");
      compositionListEl.querySelectorAll("[data-composition]").forEach((button) => {
        button.addEventListener("click", () => {
          activeCompositionId = button.dataset.composition;
          renderCompositionChoices();
        });
      });
    }

    function renderRenderChoices() {
      const renders = (activeProject && activeProject.renders) || [];
      if (!renders.length) {
        renderListEl.innerHTML = `<div class="empty">No rendered outputs</div>`;
        renderPreviewEl.innerHTML = "";
        return;
      }
      renderListEl.innerHTML = renders.map((render) => {
        const active = render.render_id === activeRenderId ? "active" : "";
        const label = `v${render.version || ""} ${render.status || ""}`;
        return `<button class="render-row ${active}" type="button" data-render="${escapeHtml(render.render_id)}">
          <strong>${escapeHtml(label)}</strong>
          <span class="source-meta"><span>${escapeHtml(render.composition_id || "")}</span><span>${escapeHtml(render.promoted_letter_id || "")}</span></span>
        </button>`;
      }).join("");
      renderListEl.querySelectorAll("[data-render]").forEach((button) => {
        button.addEventListener("click", () => {
          activeRenderId = button.dataset.render;
          renderRenderChoices();
        });
      });
      const selected = renders.find((render) => render.render_id === activeRenderId);
      if (selected && selected.status === "succeeded") {
        renderPreviewEl.innerHTML = `<video class="render-preview" controls src="${escapeHtml(selected.preview_url)}"></video>`;
      } else {
        renderPreviewEl.innerHTML = "";
      }
    }

    function releaseActions(row) {
      const id = String(row.letter_id || "");
      const realLetter = Boolean(id) && !row.is_creation_job && !id.startsWith("create_");
      const eligible = row.eligible === true;
      const approved = row.approved === true;
      const releaseState = row.release_state || "unseen";
      const exported = releaseState === "exported" || releaseState === "published";
      const exportReady = Boolean(row.release_export_url || row.release_export_dir || exported);
      const siteAllowed = row.site_enabled !== false;
      const youtubeAllowed = row.youtube_enabled !== false;
      const candidateDisabled = realLetter && eligible ? "" : "disabled";
      const approveDisabled = realLetter && eligible ? "" : "disabled";
      const exportDisabled = realLetter && approved ? "" : "disabled";
      const siteDisabled = realLetter && exported && siteAllowed ? "" : "disabled";
      const youtubeDisabled = realLetter && approved && exportReady && youtubeAllowed ? "" : "disabled";
      const manualDisabled = row.release_export_url ? "" : "disabled";
      const revisionDisabled = realLetter ? "" : "disabled";
      const safeId = escapeHtml(id);
      return `<div class="actions">
        <button type="button" ${candidateDisabled} data-action="/api/candidate" data-id="${safeId}">Candidate</button>
        <button type="button" ${approveDisabled} data-action="/api/approve" data-id="${safeId}">Approve</button>
        <button type="button" ${exportDisabled} data-action="/api/export" data-id="${safeId}">Export</button>
        <button type="button" ${siteDisabled} data-action="/api/publish-site" data-id="${safeId}">Publish to Site</button>
        <select ${youtubeDisabled} data-youtube-privacy aria-label="YouTube privacy">
          <option value="unlisted" selected>Unlisted</option>
          <option value="private">Private</option>
          <option value="public">Public</option>
        </select>
        <button type="button" ${youtubeDisabled} data-action="/api/publish/youtube" data-id="${safeId}">Publish YouTube</button>
        <button type="button" ${manualDisabled} data-copy="${safeId}">Copy Manual Package</button>
        <button type="button" ${manualDisabled} data-open="${safeId}">Open</button>
        <button type="button" ${revisionDisabled} data-revise="${safeId}">Create Revision</button>
      </div>`;
    }

    async function runAction(path, letterId, extra = {}) {
      setBusy(true);
      statusEl.textContent = `${letterId}: working`;
      try {
        await api(path, {letter_id: letterId, ...extra});
        await loadAll();
        statusEl.textContent = `${letterId}: updated`;
      } catch (error) {
        statusEl.textContent = `${letterId}: ${error.message}`;
      } finally {
        setBusy(false);
      }
    }

    function openExport(row) {
      if (!row || !row.release_export_url) return;
      window.open(row.release_export_url, "_blank", "noopener");
    }

    async function copyManualPackage(row) {
      const lines = [
        `Letter: ${row.title || row.letter_id}`,
        `Canonical: ${row.canonical_url || ""}`,
        "Collection: https://brendonrcoleman.com/letters/",
        `Export: ${row.release_export_dir || ""}`
      ];
      await navigator.clipboard.writeText(lines.join("\\n"));
    }

    function loadRevision(row) {
      if (!row || !row.letter_id) return;
      revisionParentId = row.letter_id;
      customTheme.value = row.theme || "";
      seedField.value = "";
      manualText.value = row.text || "";
      revisionLabel.textContent = `Revision of ${row.letter_id}`;
      revisionNotice.classList.add("active");
      createButton.textContent = "Create Revision";
      statusEl.textContent = `${row.letter_id}: revision loaded`;
      document.getElementById("create-title").scrollIntoView({behavior: "smooth", block: "start"});
    }

    function clearRevision() {
      revisionParentId = null;
      revisionNotice.classList.remove("active");
      revisionLabel.textContent = "";
      createButton.textContent = "Create Letter";
    }

    function renderConfig(config) {
      const brandRows = (config.brands || []).map((brand) => {
        return `<div class="readiness-row"><span>${escapeHtml(brand.display_name)}</span>${badge(brand.status, stateClass(brand.status))}</div>`;
      }).join("");
      readinessEl.innerHTML = `
        <div class="readiness-row"><span>ElevenLabs configured</span>${yesNo(config.elevenlabs_configured)}</div>
        <div class="readiness-row"><span>YouTube OAuth configured</span>${yesNo(config.youtube_oauth_configured)}</div>
        <div class="readiness-row"><span>Website publisher available</span>${yesNo(config.website_publisher_available)}</div>
        <div class="readiness-row"><span>Local transcription available</span>${yesNo(config.local_transcription_available)}</div>
        ${brandRows}
      `;
    }

    function renderFilters() {
      filtersEl.innerHTML = filters.map((name) => {
        const active = name === activeFilter ? "active" : "";
        return `<button class="secondary filter ${active}" type="button" data-filter="${escapeHtml(name)}">${escapeHtml(name)}</button>`;
      }).join("");
      filtersEl.querySelectorAll("button[data-filter]").forEach((button) => {
        button.addEventListener("click", () => {
          activeFilter = button.dataset.filter;
          renderLibrary();
        });
      });
    }

    function isPublished(row) {
      return row.release_state === "published" || row.site_status === "published" || row.youtube_status === "published";
    }

    function matchesFilter(row) {
      if (activeFilter === "All") return true;
      if (activeFilter === "Creating") return row.creation_status === "queued" || row.creation_status === "running" || row.release_state === "creating";
      if (activeFilter === "Needs Review") return row.lifecycle_state === "registered" && !row.approved && !isPublished(row);
      if (activeFilter === "Eligible") return row.eligible === true && !isPublished(row);
      if (activeFilter === "Published") return isPublished(row);
      if (activeFilter === "Failed") return row.lifecycle_state === "failed" || row.release_state === "failed" || row.creation_status === "failed";
      return true;
    }

    function wireActions(scope) {
      scope.querySelectorAll("button[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const extra = {};
          if (button.dataset.action === "/api/publish/youtube") {
            const select = button.parentElement.querySelector("select[data-youtube-privacy]");
            extra.privacy_status = select ? select.value : "unlisted";
          }
          runAction(button.dataset.action, button.dataset.id, extra);
        });
      });
      scope.querySelectorAll("button[data-open]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.open);
        button.addEventListener("click", () => openExport(row));
      });
      scope.querySelectorAll("button[data-copy]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.copy);
        button.addEventListener("click", () => {
          copyManualPackage(row)
            .then(() => { statusEl.textContent = `${row.letter_id}: manual package copied`; })
            .catch((error) => { statusEl.textContent = `${row.letter_id}: ${error.message}`; });
        });
      });
      scope.querySelectorAll("button[data-revise]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.revise);
        button.addEventListener("click", () => loadRevision(row));
      });
    }

    function renderJobs() {
      const active = jobs.filter((job) => job.status === "queued" || job.status === "running");
      jobSummaryEl.textContent = `${active.length} active | ${jobs.length} total`;
      const visible = jobs.slice(0, 12);
      if (!visible.length) {
        jobsBody.innerHTML = `<tr><td colspan="8"><div class="empty">No creation jobs</div></td></tr>`;
        return;
      }
      jobsBody.innerHTML = visible.map((job) => {
        const events = Array.isArray(job.events) ? job.events.slice(-10) : [];
        const timeline = events.map((event) => {
          const label = event.lifecycle_state || event.event_type || "event";
          return badge(label, stateClass(label));
        }).join("");
        const score = job.final_score ?? "";
        const audio = job.audio_score ?? "";
        const release = job.release_eligible === null || job.release_eligible === undefined
          ? ""
          : yesNo(job.release_eligible);
        const stage = job.current_stage || job.status || "";
        const jobId = escapeHtml(job.job_id);
        const theme = escapeHtml(job.theme || "");
        const parent = job.parent_letter_id ? `<div class="path">parent ${escapeHtml(job.parent_letter_id)}</div>` : "";
        return `<tr>
          <td class="id">${jobId}<div class="path">${escapeHtml(job.letter_id || "")}</div></td>
          <td>${badge(job.status || "", stateClass(job.status))}<div class="path">${escapeHtml(stage)}</div></td>
          <td>${theme}${parent}</td>
          <td><div class="timeline">${timeline}</div></td>
          <td>${mediaLinks(job)}</td>
          <td class="score">${escapeHtml(score)}${audio !== "" ? `<div class="path">audio ${escapeHtml(audio)}</div>` : ""}</td>
          <td>${release}</td>
          <td>${releaseActions(job)}</td>
        </tr>`;
      }).join("");
      wireActions(jobsBody);
    }

    function renderLibrary() {
      renderFilters();
      const filtered = rows.filter(matchesFilter);
      const eligibleCount = rows.filter((row) => row.eligible).length;
      const publishedCount = rows.filter(isPublished).length;
      const creatingCount = rows.filter((row) => row.creation_status === "queued" || row.creation_status === "running").length;
      summaryEl.textContent = `${rows.length} letters | ${creatingCount} creating | ${eligibleCount} eligible | ${publishedCount} published`;
      if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="14"><div class="empty">No Letters in this filter</div></td></tr>`;
        return;
      }

      tbody.innerHTML = filtered.map((row) => {
        const eligible = row.eligible ? badge("eligible", "yes") : badge("blocked", "no");
        const lifecycle = badge(row.lifecycle_state || "unknown", stateClass(row.lifecycle_state || "unknown"));
        const releaseState = row.release_state || "unseen";
        const releaseBadge = badge(releaseState, stateClass(releaseState));
        const score = row.evaluation_total ?? "";
        const audio = row.audio_alignment ?? "";
        const letterId = escapeHtml(row.letter_id);
        const title = escapeHtml(row.title || "");
        const theme = escapeHtml(row.theme || "");
        const brand = brandBadge(row.brand_id, row.brand_display_name, row.brand_status);
        const canonical = row.canonical_url
          ? `<a href="${escapeHtml(row.canonical_url)}" target="_blank" rel="noopener">Open</a>`
          : "";
        const youtube = row.youtube_url
          ? `<a href="${escapeHtml(row.youtube_url)}" target="_blank" rel="noopener">${badge(row.youtube_status || "published", stateClass(row.youtube_status || "published"))}</a>`
          : badge(row.youtube_status || "pending", stateClass(row.youtube_status || "pending"));
        const parent = row.parent_letter_id ? `<div class="path">parent ${escapeHtml(row.parent_letter_id)}</div>` : "";
        const children = row.revision_count ? `<div class="path">${escapeHtml(row.revision_count)} revisions</div>` : "";
        const project = row.project_id ? `<div class="path">project ${escapeHtml(row.project_id)}</div>` : "";
        const sources = Array.isArray(row.source_asset_ids) && row.source_asset_ids.length
          ? `<div class="path">${escapeHtml(row.source_asset_ids.length)} source assets</div>`
          : "";
        const historyCount = Array.isArray(row.release_events) ? row.release_events.length : 0;
        const logCount = Object.values(row.manual_social_urls || {}).filter(Boolean).length;
        const history = `${historyCount} events${logCount ? `, ${logCount} URLs` : ""}`;
        const disabledReasons = Array.isArray(row.release_disabled_reasons)
          ? row.release_disabled_reasons.filter(Boolean).join("; ")
          : "";
        return `<tr>
          <td class="id">${letterId}</td>
          <td class="title">${title}</td>
          <td>${theme}</td>
          <td>${brand}</td>
          <td class="score">${escapeHtml(score)}</td>
          <td class="audio">${escapeHtml(audio)}</td>
          <td>${lifecycle}</td>
          <td>${releaseBadge}<div>${eligible}</div>${disabledReasons ? `<div class="path">${escapeHtml(disabledReasons)}</div>` : ""}</td>
          <td>${canonical}</td>
          <td>${youtube}</td>
          <td>${project}${sources}${parent}${children}</td>
          <td>${mediaLinks(row)}</td>
          <td>${escapeHtml(history)}</td>
          <td>${releaseActions(row)}</td>
        </tr>`;
      }).join("");
      wireActions(tbody);
    }

    function updatePoll() {
      const hasActive = jobs.some((job) => job.status === "queued" || job.status === "running");
      const projectJobs = activeProject ? Object.values(activeProject.jobs || {}) : [];
      const hasProjectActive = projectJobs.some((job) => job.status === "queued" || job.status === "running");
      if ((hasActive || hasProjectActive) && pollTimer === null) {
        pollTimer = window.setInterval(loadAll, 1500);
      } else if (!hasActive && !hasProjectActive && pollTimer !== null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    async function loadAll() {
      const [configData, jobData, letterData, projectData] = await Promise.all([
        api("/api/config"),
        api("/api/jobs"),
        api("/api/letters"),
        api("/api/projects")
      ]);
      brands = configData.brands || [];
      jobs = jobData;
      rows = letterData;
      projects = projectData;
      if (activeProject) {
        try {
          activeProject = await api(`/api/projects/${encodeURIComponent(activeProject.project_id)}`);
          if (!activeAssetId && activeProject.assets && activeProject.assets[0]) {
            activeAssetId = activeProject.assets[0].asset_id;
          }
          if (!activeCompositionId && activeProject.compositions && activeProject.compositions[0]) {
            activeCompositionId = activeProject.compositions[0].composition_id;
          }
          if (!activeVoiceAssetId && activeProject.voice_captures && activeProject.voice_captures[0]) {
            activeVoiceAssetId = activeProject.voice_captures[0].asset_id;
          }
          if (activeVoiceAssetId) {
            activeVoiceTranscript = await api(`/api/projects/${encodeURIComponent(activeProject.project_id)}/voice-captures/${encodeURIComponent(activeVoiceAssetId)}/transcript`);
          }
        } catch (error) {
          activeProject = null;
        }
      }
      renderBrandControls();
      renderConfig(configData);
      renderProjects();
      renderProjectWorkspace();
      renderJobs();
      renderLibrary();
      updatePoll();
    }

    newProjectBtn.addEventListener("click", async () => {
      workspaceStatusEl.textContent = "Creating project";
      try {
        activeProject = await api("/api/projects", {
          title: newProjectTitle.value.trim() || "Untitled Project",
          brand_id: newProjectBrand.value || "letters_of_light"
        });
        newProjectTitle.value = "";
        selectedPassages = new Map();
        await loadAll();
        workspaceStatusEl.textContent = `${activeProject.title}: ready`;
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    projectBrandFilter.addEventListener("change", () => {
      activeProjectBrandFilter = projectBrandFilter.value || "";
      renderProjects();
    });

    cloneToBrandBtn.addEventListener("click", async () => {
      if (!activeProjectId()) {
        workspaceStatusEl.textContent = "select a project first";
        return;
      }
      const targetBrandId = cloneBrand.value || "";
      if (!targetBrandId) {
        workspaceStatusEl.textContent = "select a target brand";
        return;
      }
      workspaceStatusEl.textContent = "Cloning project";
      try {
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/clone-to-brand`, {
          brand_id: targetBrandId
        });
        activeProject = result.project;
        selectedPassages = new Map();
        await loadAll();
        workspaceStatusEl.textContent = `${activeProject.title}: cloned`;
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    importAssetBtn.addEventListener("click", async () => {
      if (!activeProjectId()) {
        workspaceStatusEl.textContent = "select a project first";
        return;
      }
      workspaceStatusEl.textContent = "Importing source";
      try {
        if (assetFile.files && assetFile.files[0]) {
          const data = new FormData();
          data.append("file", assetFile.files[0]);
          await apiForm(`/api/projects/${encodeURIComponent(activeProjectId())}/assets`, data);
          assetFile.value = "";
        } else {
          await api(`/api/projects/${encodeURIComponent(activeProjectId())}/assets`, {source_path: assetPath.value.trim()});
          assetPath.value = "";
        }
        await loadAll();
        workspaceStatusEl.textContent = "Source imported";
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    extractAssetBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeAssetId) {
        workspaceStatusEl.textContent = "select a source first";
        return;
      }
      workspaceStatusEl.textContent = "Extraction queued";
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId())}/extract`, {asset_id: activeAssetId});
        await loadAll();
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    passageSearch.addEventListener("input", renderPassages);
    selectVisiblePassagesBtn.addEventListener("click", () => {
      visiblePassages().forEach((passage) => {
        const id = passage.passage_id || `${passage.asset_id}:${passage.passage_index}`;
        selectedPassages.set(id, passage);
      });
      renderPassages();
      buildProjectDraft();
      invalidateOutlinePreview();
    });
    clearPassagesBtn.addEventListener("click", () => {
      selectedPassages = new Map();
      projectDraft.value = "";
      renderPassages();
      updateSelectedPassageCount();
      invalidateOutlinePreview();
    });
    governedFindProposalsBtn.addEventListener("click", loadGovernedProposalDiscovery);
    governedProposalSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        loadGovernedProposalDiscovery();
      }
    });
    governedClearProposalSearchBtn.addEventListener("click", () => {
      governedProposalSearch.value = "";
      resetGovernedDiscovery();
      renderGovernedProposalDiscovery();
    });
    governedProposalId.addEventListener("input", invalidateGovernedPreview);
    governedDraftIntent.addEventListener("input", () => {
      resetGovernedDiscovery();
      invalidateGovernedPreview();
    });
    governedWorkingTitle.addEventListener("input", renderGovernedDraftPanel);
    governedWriterNote.addEventListener("input", renderGovernedDraftPanel);
    governedCheckProposalBtn.addEventListener("click", async () => {
      if (!activeProjectId()) {
        governedDraftStatus.textContent = "select a project first";
        return;
      }
      const proposalId = governedProposalId.value.trim();
      const draftIntent = governedDraftIntent.value.trim();
      if (!proposalId || !draftIntent) {
        renderGovernedDraftPanel();
        return;
      }
      governedContextInFlight = true;
      renderGovernedDraftPanel();
      try {
        const query = new URLSearchParams({proposal_id: proposalId, draft_intent_ref: draftIntent});
        governedPreview = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/context?${query.toString()}`);
        governedPreviewKey = governedInputKey();
        governedPreviewError = "";
      } catch (error) {
        governedPreview = null;
        governedPreviewKey = "";
        governedPreviewError = error.message;
        governedDraftStatus.textContent = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        governedContextInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    governedOpenExistingDraftBtn.addEventListener("click", () => {
      const letterId = governedOpenExistingDraftBtn.dataset.letterId || "";
      if (!letterId) return;
      workspaceStatusEl.textContent = `Open Existing Draft: ${letterId}`;
      document.getElementById("library-title").scrollIntoView({behavior: "smooth", block: "start"});
    });
    governedOpenDraftBtn.addEventListener("click", async () => {
      if (governedDraftInFlight) return;
      if (!activeProjectId()) {
        governedDraftStatus.textContent = "select a project first";
        return;
      }
      const proposalId = governedProposalId.value.trim();
      const draftIntent = governedDraftIntent.value.trim();
      const selected = Array.from(selectedPassages.values());
      if (!proposalId || !draftIntent || !selected.length || !governedPreviewIsFresh() || !governedPreview.governed_brief_ready) {
        renderGovernedDraftPanel();
        return;
      }
      governedDraftInFlight = true;
      renderGovernedDraftPanel();
      try {
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/open`, {
          proposal_id: proposalId,
          draft_intent_ref: draftIntent,
          selected_passages: selected,
          selected_source_asset_ids: selected.length ? [] : (activeAssetId ? [activeAssetId] : []),
          working_title: governedWorkingTitle.value.trim(),
          writer_note: governedWriterNote.value.trim(),
          actor_ref: "operator.local"
        });
        await loadAll();
        if (governedPreviewIsFresh() && result.letter_id) {
          governedPreview = {
            ...governedPreview,
            linked_project_studio_letter_exists: true,
            linked_letter: {
              exists: true,
              available: true,
              status: "available",
              letter_id: result.letter_id
            }
          };
        }
        const label = result.status === "linked_existing" ? "Open Existing Draft" : "Created governed draft";
        governedDraftStatus.textContent = `${label}: ${result.letter_id || result.job_id || result.output_id}`;
        workspaceStatusEl.textContent = governedDraftStatus.textContent;
        if (result.letter_id) {
          document.getElementById("library-title").scrollIntoView({behavior: "smooth", block: "start"});
        }
      } catch (error) {
        governedDraftInFlight = false;
        renderGovernedDraftPanel();
        governedDraftStatus.textContent = error.message;
        workspaceStatusEl.textContent = error.message;
        return;
      }
      governedDraftInFlight = false;
      renderGovernedDraftPanel();
    });
    outlinePreviewIntent.addEventListener("input", invalidateOutlinePreview);
    outlineFormatIntent.addEventListener("input", invalidateOutlinePreview);
    outlineWriterNote.addEventListener("input", invalidateOutlinePreview);
    outlinePreviewActionBtn.addEventListener("click", async () => {
      if (outlinePreviewInFlight) return;
      const parent = governedParentLetterContext();
      if (!activeProjectId() || !parent || !selectedPassages.size || !outlinePreviewIntent.value.trim()) {
        renderGovernedDraftPanel();
        return;
      }
      outlinePreviewInFlight = true;
      outlinePreviewError = "";
      outlinePreviewStale = false;
      invalidateProseCandidate(false);
      renderGovernedDraftPanel();
      try {
        outlinePreview = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/outline-preview`, outlineRequestBody(parent));
        outlinePreviewKeyValue = outlinePreviewKey();
        outlinePreviewStale = false;
        workspaceStatusEl.textContent = outlinePreview.ready ? "Source-grounded outline preview ready" : "Source-grounded outline preview blocked";
      } catch (error) {
        outlinePreview = null;
        outlinePreviewKeyValue = "";
        outlinePreviewError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        outlinePreviewInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    outlineAcceptActionBtn.addEventListener("click", async () => {
      if (outlineAcceptanceInFlight) return;
      const parent = governedParentLetterContext();
      if (!parent || !outlinePreviewIsFresh() || !outlinePreview || !outlinePreview.ready) {
        renderGovernedDraftPanel();
        return;
      }
      outlineAcceptanceInFlight = true;
      outlinePreviewError = "";
      renderGovernedDraftPanel();
      try {
        const body = outlineRequestBody(parent);
        body.preview_id = outlinePreview.preview_id;
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/outline-acceptance`, body);
        await loadAll();
        outlinePreview = {
          ...outlinePreview,
          existing_child: {
            exists: true,
            available: true,
            status: result.status || "linked_existing",
            acceptance_id: result.acceptance_id || "",
            child_letter_id: result.child_letter_id || "",
            title: result.child_letter ? result.child_letter.title || "" : "",
            lifecycle_state: result.child_letter ? result.child_letter.lifecycle_state || "" : "",
            open_url: result.open_url || (result.child_letter_id ? `/?letter_id=${result.child_letter_id}` : "")
          }
        };
        outlinePreviewKeyValue = outlinePreviewKey();
        invalidateProseCandidate(false);
        proseScaffoldLetter.value = result.child_letter_id || proseScaffoldLetter.value;
        const label = result.status === "linked_existing" ? "Open Existing Child Draft" : "Created child draft";
        outlinePreviewStatus.textContent = `${label}: ${result.child_letter_id}`;
        workspaceStatusEl.textContent = outlinePreviewStatus.textContent;
      } catch (error) {
        outlinePreviewError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        outlineAcceptanceInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    outlineOpenChildBtn.addEventListener("click", () => {
      const openUrl = outlineOpenChildBtn.dataset.openUrl || "";
      if (!openUrl) return;
      window.location.href = openUrl;
    });
    proseScaffoldLetter.addEventListener("change", invalidateProseCandidate);
    proseOutlineSection.addEventListener("change", invalidateProseCandidate);
    proseCandidateIntent.addEventListener("input", invalidateProseCandidate);
    proseFormatConstraint.addEventListener("change", invalidateProseCandidate);
    proseWriterInstruction.addEventListener("input", invalidateProseCandidate);
    proseApplyIntent.addEventListener("input", renderGovernedDraftPanel);
    proseGenerateActionBtn.addEventListener("click", async () => {
      if (proseCandidateInFlight) return;
      if (!activeProjectId() || !proseScaffoldLetter.value.trim() || !proseOutlineSection.value.trim() || !selectedPassages.size || !proseCandidateIntent.value.trim()) {
        renderGovernedDraftPanel();
        return;
      }
      proseCandidateInFlight = true;
      proseCandidateError = "";
      proseCandidateStale = false;
      proseAppliedChild = null;
      renderGovernedDraftPanel();
      try {
        proseCandidate = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/prose-candidate`, proseCandidateRequestBody());
        proseCandidateKeyValue = proseCandidateKey();
        proseCandidateStale = false;
        workspaceStatusEl.textContent = proseCandidate.status === "generated_candidate" ? "Grounded candidate ready for review" : `Grounded candidate ${proseCandidate.status || "blocked"}`;
      } catch (error) {
        proseCandidate = null;
        proseCandidateKeyValue = "";
        proseCandidateError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        proseCandidateInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    proseApplyActionBtn.addEventListener("click", async () => {
      if (proseApplyInFlight) return;
      if (!proseCandidateIsFresh() || !proseCandidate || !proseCandidate.candidate_envelope || !proseApplyIntent.value.trim()) {
        renderGovernedDraftPanel();
        return;
      }
      proseApplyInFlight = true;
      proseCandidateError = "";
      renderGovernedDraftPanel();
      try {
        const envelopePayload = proseCandidate.candidate_envelope.payload || {};
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/prose-apply`, {
          accepted_scaffold_letter_id: proseScaffoldLetter.value.trim(),
          candidate_envelope: proseCandidate.candidate_envelope,
          expected_scaffold_body_hash: envelopePayload.accepted_scaffold_body_hash || "",
          apply_intent_ref: proseApplyIntent.value.trim(),
          actor_ref: "operator.local"
        });
        await loadAll();
        proseAppliedChild = {
          available: true,
          letter_id: result.child_letter_id || "",
          title: result.child_letter ? result.child_letter.title || "" : "",
          lifecycle_state: result.child_letter ? result.child_letter.lifecycle_state || "" : "",
          open_url: result.open_url || (result.child_letter_id ? `/?letter_id=${result.child_letter_id}` : "")
        };
        const label = result.status === "linked_existing" ? "Open Existing Applied Draft" : "Created applied child draft";
        proseCandidateStatus.textContent = `${label}: ${result.child_letter_id}`;
        workspaceStatusEl.textContent = proseCandidateStatus.textContent;
      } catch (error) {
        proseCandidateError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        proseApplyInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    proseOpenAppliedChildBtn.addEventListener("click", () => {
      const openUrl = proseOpenAppliedChildBtn.dataset.openUrl || "";
      if (!openUrl) return;
      window.location.href = openUrl;
    });
    productionDerivativeSourceHash.addEventListener("input", invalidateProductionDerivative);
    productionDerivativeIntent.addEventListener("input", invalidateProductionDerivative);
    productionDerivativeOperator.addEventListener("input", invalidateProductionDerivative);
    productionDerivativeTheme.addEventListener("input", invalidateProductionDerivative);
    productionDerivativeNote.addEventListener("input", renderGovernedDraftPanel);
    productionDerivativeValidateBtn.addEventListener("click", async () => {
      if (productionDerivativeInFlight) return;
      const source = productionDerivativeSourceLetter();
      if (!activeProjectId() || !source || !source.letter_id || !productionDerivativeSourceHash.value.trim() || !productionDerivativeIntent.value.trim() || !productionDerivativeOperator.value.trim()) {
        renderGovernedDraftPanel();
        return;
      }
      productionDerivativeInFlight = true;
      productionDerivativeError = "";
      productionDerivativeApplied = null;
      renderGovernedDraftPanel();
      try {
        productionDerivativeCandidate = await api(
          `/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/${encodeURIComponent(source.letter_id)}/production-derivative-candidate`,
          productionDerivativeRequestBody()
        );
        productionDerivativeCandidateKeyValue = productionDerivativeCandidateKey();
        workspaceStatusEl.textContent = productionDerivativeCandidate.validation_state === "valid"
          ? "Production derivative candidate validated"
          : "Production derivative candidate blocked";
      } catch (error) {
        productionDerivativeCandidate = null;
        productionDerivativeCandidateKeyValue = "";
        productionDerivativeError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        productionDerivativeInFlight = false;
        renderGovernedDraftPanel();
      }
    });
    productionDerivativeCreateBtn.addEventListener("click", async () => {
      if (productionDerivativeApplyInFlight) return;
      const source = productionDerivativeSourceLetter();
      if (!productionDerivativeCandidateIsFresh() || !productionDerivativeCandidate || !productionDerivativeCandidate.candidate_envelope || !source || !source.letter_id) {
        renderGovernedDraftPanel();
        return;
      }
      productionDerivativeApplyInFlight = true;
      productionDerivativeError = "";
      renderGovernedDraftPanel();
      try {
        const result = await api(
          `/api/projects/${encodeURIComponent(activeProjectId())}/governed-drafts/${encodeURIComponent(source.letter_id)}/production-derivative-apply`,
          {
            candidate_envelope: productionDerivativeCandidate.candidate_envelope,
            expected_source_body_hash: productionDerivativeSourceHash.value.trim(),
            promotion_intent_ref: productionDerivativeIntent.value.trim(),
            operator_ref: productionDerivativeOperator.value.trim(),
            operator_note: productionDerivativeNote.value.trim()
          }
        );
        await loadAll();
        productionDerivativeApplied = result;
        invalidateProductionDerivativeStatus(false);
        const label = result.validation_state === "already_promoted" ? "Existing production derivative" : "Created production derivative";
        productionDerivativeStatus.textContent = `${label}: ${result.target_letter_id || ""}`;
        workspaceStatusEl.textContent = productionDerivativeStatus.textContent;
      } catch (error) {
        productionDerivativeError = error.message;
        workspaceStatusEl.textContent = error.message;
      } finally {
        productionDerivativeApplyInFlight = false;
        renderGovernedDraftPanel();
      }
    });

    voiceNewBtn.addEventListener("click", () => {
      discardVoiceCapture();
      voiceProjectTitle.value = "";
      setVoiceMode("free_talk");
    });
    voiceFreeTalkBtn.addEventListener("click", () => setVoiceMode("free_talk"));
    voiceReadScriptBtn.addEventListener("click", () => setVoiceMode("read_script"));
    voiceScriptText.addEventListener("input", refreshVoiceReader);
    voiceReaderSize.addEventListener("input", () => {
      voiceReader.style.fontSize = `${voiceReaderSize.value}px`;
    });
    voiceAutoScroll.addEventListener("change", () => {
      window.clearInterval(voiceScrollTimer);
      voiceScrollTimer = null;
      if (voiceAutoScroll.checked) {
        voiceScrollTimer = window.setInterval(() => {
          voiceReader.scrollTop = Math.min(voiceReader.scrollTop + 1, voiceReader.scrollHeight);
        }, 90);
      }
    });
    voiceStartBtn.addEventListener("click", startVoiceRecording);
    voicePauseBtn.addEventListener("click", pauseVoiceRecording);
    voiceResumeBtn.addEventListener("click", resumeVoiceRecording);
    voiceStopBtn.addEventListener("click", stopVoiceRecording);
    voiceDiscardBtn.addEventListener("click", discardVoiceCapture);
    voiceSaveBtn.addEventListener("click", saveVoiceCapture);

    readSelectedPassagesBtn.addEventListener("click", () => {
      buildProjectDraft();
      const selected = Array.from(selectedPassages.values());
      const text = projectDraft.value.trim();
      if (!text) {
        workspaceStatusEl.textContent = "select passages first";
        return;
      }
      loadScriptIntoReader(text, {
        source_reference: "pdf_passage_selector",
        source_asset_id: activeAssetId || "",
        passage_ids: selected.map((passage) => passage.passage_id || "").filter(Boolean)
      });
      voiceSaveTarget.value = activeProjectId() ? "active_project" : "new_project";
    });

    readManualTextBtn.addEventListener("click", () => {
      const text = manualText.value.trim();
      if (!text) {
        statusEl.textContent = "manual text is empty";
        return;
      }
      loadScriptIntoReader(text, {source_reference: "letter_draft_view"});
    });

    recordProjectVoiceBtn.addEventListener("click", () => {
      if (!activeProjectId()) {
        workspaceStatusEl.textContent = "select a project first";
        return;
      }
      voiceSaveTarget.value = "active_project";
      voiceBrand.value = activeProject.brand_id || voiceBrand.value;
      document.getElementById("voice-intake-title").scrollIntoView({behavior: "smooth", block: "start"});
      setVoiceState("permission_required", "ready to record into selected project");
    });

    voiceTranscribeBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeVoiceAssetId) {
        workspaceStatusEl.textContent = "select a voice source first";
        return;
      }
      workspaceStatusEl.textContent = "Transcript queued";
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId())}/voice-captures/${encodeURIComponent(activeVoiceAssetId)}/transcribe`, {});
        await loadAll();
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    voiceSaveTranscriptBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeVoiceAssetId) {
        workspaceStatusEl.textContent = "select a voice source first";
        return;
      }
      const editedSegments = collectEditedTranscriptSegments();
      try {
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/voice-captures/${encodeURIComponent(activeVoiceAssetId)}/transcript`, {
          edited_segments: editedSegments
        });
        activeVoiceTranscript = result.transcript;
        renderVoiceTranscript();
        workspaceStatusEl.textContent = "Transcript edits saved";
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    voiceCopyDraftBtn.addEventListener("click", () => {
      const text = selectedTranscriptText();
      if (!text) {
        workspaceStatusEl.textContent = "select transcript segments first";
        return;
      }
      projectDraft.value = text;
      workspaceStatusEl.textContent = "Selected transcript copied to draft";
    });

    voiceCreateLetterBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeVoiceAssetId) {
        workspaceStatusEl.textContent = "select a voice source first";
        return;
      }
      const text = selectedTranscriptText();
      const theme = voiceLetterTheme.value.trim() || projectLetterTheme.value.trim() || customTheme.value.trim() || themeSelect.value.trim();
      if (!theme) {
        workspaceStatusEl.textContent = "theme is required";
        return;
      }
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId())}/voice-captures/${encodeURIComponent(activeVoiceAssetId)}/create-letter`, {
          theme,
          segment_ids: selectedTranscriptIds(),
          manual_text: text || null
        });
        await loadAll();
        workspaceStatusEl.textContent = "Voice Letter queued";
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    voiceUseCompositionBtn.addEventListener("click", () => {
      if (!activeVoiceAssetId) {
        compositionStatusEl.textContent = "select a voice source first";
        return;
      }
      const text = selectedTranscriptText();
      compositionVoice.value = activeVoiceAssetId;
      if (text) compositionCaption.value = text;
      compositionStatusEl.textContent = "Voice and caption loaded into composition";
      document.getElementById("composition-title").scrollIntoView({behavior: "smooth", block: "start"});
    });

    projectCreateLetterBtn.addEventListener("click", async () => {
      if (!activeProjectId()) {
        workspaceStatusEl.textContent = "select a project first";
        return;
      }
      const theme = projectLetterTheme.value.trim() || customTheme.value.trim() || themeSelect.value.trim();
      if (!theme) {
        workspaceStatusEl.textContent = "theme is required";
        return;
      }
      const selected = Array.from(selectedPassages.values());
      workspaceStatusEl.textContent = "Project Letter queued";
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId())}/create-letter`, {
          theme,
          manual_text: projectDraft.value.trim() || null,
          selected_passages: selected,
          source_asset_ids: selected.length ? [] : (activeAssetId ? [activeAssetId] : [])
        });
        projectDraft.value = "";
        selectedPassages = new Map();
        await loadAll();
      } catch (error) {
        workspaceStatusEl.textContent = error.message;
      }
    });

    createCompositionBtn.addEventListener("click", async () => {
      if (!activeProjectId()) {
        compositionStatusEl.textContent = "select a project first";
        return;
      }
      const clips = Array.from(clipListEl.querySelectorAll("input[data-clip-asset]:checked")).map((input) => {
        const assetId = input.dataset.clipAsset;
        const inField = clipListEl.querySelector(`input[data-clip-in="${CSS.escape(assetId)}"]`);
        const outField = clipListEl.querySelector(`input[data-clip-out="${CSS.escape(assetId)}"]`);
        const orderField = clipListEl.querySelector(`input[data-clip-order="${CSS.escape(assetId)}"]`);
        return {
          asset_id: assetId,
          in_point: Number(inField ? inField.value : 0) || 0,
          out_point: outField && outField.value ? Number(outField.value) : null,
          order: Number(orderField ? orderField.value : 1) || 1
        };
      });
      compositionStatusEl.textContent = "Creating composition";
      try {
        const composition = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/compositions`, {
          title: compositionTitleText.value.trim() || "Project Composition",
          aspect_ratio: compositionAspect.value,
          clips,
          title_text: compositionTitleText.value.trim(),
          caption_text: compositionCaption.value.trim(),
          image_overlay_asset_id: compositionImage.value || null,
          voice_asset_id: compositionVoice.value || null,
          music_asset_id: compositionMusic.value || null
        });
        activeCompositionId = composition.composition_id;
        await loadAll();
        compositionStatusEl.textContent = "Composition saved";
      } catch (error) {
        compositionStatusEl.textContent = error.message;
      }
    });

    renderCompositionBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeCompositionId) {
        compositionStatusEl.textContent = "select a composition first";
        return;
      }
      compositionStatusEl.textContent = "Render queued";
      try {
        const result = await api(`/api/projects/${encodeURIComponent(activeProjectId())}/render`, {composition_id: activeCompositionId});
        activeRenderId = result.render.render_id;
        await loadAll();
      } catch (error) {
        compositionStatusEl.textContent = error.message;
      }
    });

    promoteRenderBtn.addEventListener("click", async () => {
      if (!activeProjectId() || !activeRenderId) {
        compositionStatusEl.textContent = "select a rendered output first";
        return;
      }
      compositionStatusEl.textContent = "Promoting to release gate";
      try {
        await api(`/api/projects/${encodeURIComponent(activeProjectId())}/promote-render`, {
          render_id: activeRenderId,
          review_fields: collectReviewFields()
        });
        await loadAll();
        compositionStatusEl.textContent = "Promoted to Release Controls";
      } catch (error) {
        compositionStatusEl.textContent = error.message;
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const theme = (customTheme.value.trim() || themeSelect.value.trim());
      if (!theme) {
        statusEl.textContent = "theme is required";
        return;
      }
      const body = {
        theme,
        seed: seedField.value.trim() || null,
        manual_text: manualText.value.trim() || null
      };
      const path = revisionParentId ? "/api/revise" : "/api/create";
      if (revisionParentId) body.parent_letter_id = revisionParentId;
      setBusy(true);
      try {
        const result = await api(path, body);
        statusEl.textContent = `${result.job_id}: queued`;
        clearRevision();
        seedField.value = "";
        manualText.value = "";
        await loadAll();
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        setBusy(false);
      }
    });

    cancelRevisionBtn.addEventListener("click", clearRevision);
    refreshBtn.addEventListener("click", () => {
      statusEl.textContent = "Refreshing";
      loadAll()
        .then(() => { statusEl.textContent = "Ready"; })
        .catch((error) => { statusEl.textContent = error.message; });
    });

    setVoiceMode("free_talk");
    voiceReader.style.fontSize = `${voiceReaderSize.value}px`;
    updateVoiceButtons();

    loadAll()
      .then(() => { statusEl.textContent = "Ready"; })
      .catch((error) => { statusEl.textContent = error.message; });
  </script>
</body>
</html>
"""


class ReleaseRequestHandler(BaseHTTPRequestHandler):
    server_version = "LettersReleaseServer/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(_render_page())
            return

        if path == "/wtpu-publication" or path.startswith("/wtpu-publication/"):
            html, status = render_wtpu_publication_dashboard_page(path, parsed.query)
            self._send_html(html, status)
            return

        if path.startswith("/api/wtpu-publication"):
            payload, status = handle_wtpu_publication_api(path, parsed.query)
            self._send_json(payload, status)
            return

        if path == "/api/config":
            self._send_json(_config_payload())
            return

        if path == "/api/letters":
            self._send_json(_letters_payload())
            return

        if path == "/api/projects":
            self._send_json(list_projects())
            return

        if path.startswith("/api/projects/"):
            parts = path.strip("/").split("/")
            try:
                if len(parts) == 5 and parts[3] == "governed-drafts" and parts[4] == "proposals":
                    self._handle_governed_draft_proposals(parts[2], parse_qs(parsed.query))
                    return
                if len(parts) == 5 and parts[3] == "governed-drafts" and parts[4] == "context":
                    self._handle_governed_draft_context(parts[2], parse_qs(parsed.query))
                    return
                if (
                    len(parts) == 6
                    and parts[3] == "governed-drafts"
                    and parts[5] == "production-derivative-status"
                ):
                    self._handle_production_derivative_status(parts[2], parts[4])
                    return
                if len(parts) == 3:
                    self._send_json(project_payload(parts[2]))
                    return
                if len(parts) == 4 and parts[3] == "voice-captures":
                    self._send_json(list_voice_captures(parts[2]))
                    return
                if len(parts) == 6 and parts[3] == "voice-captures" and parts[5] == "transcript":
                    self._send_json(get_voice_transcript(parts[2], parts[4]))
                    return
                if len(parts) == 6 and parts[3] == "assets" and parts[5] == "preview":
                    self._send_file(asset_file(parts[2], parts[4]))
                    return
                if len(parts) == 6 and parts[3] == "renders" and parts[5] == "preview":
                    self._send_file(render_file(parts[2], parts[4]))
                    return
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

        if path == "/api/jobs":
            self._send_json(_jobs_payload())
            return

        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1].strip()
            job = get_creation_job(job_id)
            if not job:
                self._send_json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(_job_payload(job))
            return

            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _handle_governed_draft_proposals(self, project_id: str, query: Dict[str, List[str]]) -> None:
        try:
            payload = _governed_draft_proposals_payload(project_id=project_id, query=query)
            self._send_json(payload)
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except (ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _handle_governed_draft_context(self, project_id: str, query: Dict[str, List[str]]) -> None:
        try:
            _reject_governed_draft_client_authority_fields(query)
            proposal_id = _governed_query_value(query, "proposal_id")
            draft_intent_ref = _governed_query_value(query, "draft_intent_ref")
            if not proposal_id:
                raise ValueError("proposal_id is required")
            if not draft_intent_ref:
                raise ValueError("draft_intent_ref is required")
            payload = _governed_draft_context_payload(
                project_id=project_id,
                proposal_id=proposal_id,
                draft_intent_ref=draft_intent_ref,
            )
            self._send_json(payload)
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except (ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _handle_production_derivative_status(self, project_id: str, source_letter_id: str) -> None:
        try:
            payload = governed_draft_production_derivative_status(
                project_id=project_id,
                source_letter_id=source_letter_id,
            )
            self._send_json(payload)
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except (GovernedDraftPromotionIntegrityError, ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if is_wtpu_publication_path(path):
            self._send_json(wtpu_method_not_allowed_payload("POST"), HTTPStatus.METHOD_NOT_ALLOWED)
            return

        if path == "/api/voice-capture-project":
            self._handle_voice_capture_project_post()
            return

        if path == "/api/projects" or path.startswith("/api/projects/"):
            self._handle_project_post(path)
            return

        body, error = self._read_body()
        if error:
            self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/create":
                theme = str(body.get("theme") or "").strip()
                if not theme:
                    raise ValueError("theme is required")
                job = start_creation_job(
                    theme=theme,
                    seed=body.get("seed"),
                    manual_text=body.get("manual_text"),
                )
                self._send_json(
                    {"ok": True, "job_id": job["job_id"], "job": _job_payload(job)},
                    HTTPStatus.ACCEPTED,
                )
                return

            if path == "/api/revise":
                parent_letter_id = str(body.get("parent_letter_id") or "").strip()
                if not parent_letter_id:
                    raise ValueError("parent_letter_id is required")
                if not _read_json(_letter_dir(parent_letter_id) / "letter.json"):
                    self._send_json({"error": "parent Letter not found"}, HTTPStatus.NOT_FOUND)
                    return
                theme = str(body.get("theme") or "").strip()
                if not theme:
                    raise ValueError("theme is required")
                job = start_creation_job(
                    theme=theme,
                    seed=body.get("seed"),
                    manual_text=body.get("manual_text"),
                    parent_letter_id=parent_letter_id,
                )
                self._send_json(
                    {"ok": True, "job_id": job["job_id"], "job": _job_payload(job)},
                    HTTPStatus.ACCEPTED,
                )
                return

            letter_id = _extract_letter_id(body)
            if path == "/api/candidate":
                result = create_release_candidate(letter_id)
            elif path == "/api/approve":
                result = approve_release(letter_id)
            elif path == "/api/export":
                result = export_campaign(letter_id)
            elif path in {"/api/publish-site", "/api/publish/site"}:
                result = publish_release_site(letter_id)
            elif path == "/api/publish/youtube":
                result = publish_youtube(
                    letter_id,
                    privacy_status=str(body.get("privacy_status", "unlisted")),
                    force=bool(body.get("force", False)),
                )
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"ok": True, "result": result, "letters": _letters_payload()})

    def do_PUT(self) -> None:
        self._handle_unsupported_wtpu_method("PUT")

    def do_PATCH(self) -> None:
        self._handle_unsupported_wtpu_method("PATCH")

    def do_DELETE(self) -> None:
        self._handle_unsupported_wtpu_method("DELETE")

    def _handle_unsupported_wtpu_method(self, method: str) -> None:
        path = urlparse(self.path).path
        if is_wtpu_publication_path(path):
            self._send_json(wtpu_method_not_allowed_payload(method), HTTPStatus.METHOD_NOT_ALLOWED)
            return
        self.send_error(HTTPStatus.NOT_IMPLEMENTED, f"Unsupported method ({method!r})")

    def _handle_project_post(self, path: str) -> None:
        parts = path.strip("/").split("/")
        try:
            if path == "/api/projects":
                body, error = self._read_body(allow_empty=True)
                if error:
                    self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                    return
                if body.get("parent_project_id"):
                    project = create_project_revision(
                        str(body.get("parent_project_id")),
                        title=body.get("title"),
                    )
                else:
                    project = create_project(
                        title=body.get("title"),
                        brand_id=body.get("brand_id") or DEFAULT_BRAND_ID,
                    )
                self._send_json(project, HTTPStatus.CREATED)
                return

            if len(parts) < 4:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return

            project_id = parts[2]
            action = parts[3]

            if action == "governed-drafts" and len(parts) == 5 and parts[4] == "open":
                self._handle_governed_draft_open(project_id)
                return

            if action == "governed-drafts" and len(parts) == 5 and parts[4] == "outline-preview":
                self._handle_source_grounded_outline_preview(project_id)
                return

            if action == "governed-drafts" and len(parts) == 5 and parts[4] == "outline-acceptance":
                self._handle_source_grounded_outline_acceptance(project_id)
                return

            if action == "governed-drafts" and len(parts) == 5 and parts[4] == "prose-candidate":
                self._handle_source_grounded_prose_candidate(project_id)
                return

            if action == "governed-drafts" and len(parts) == 5 and parts[4] == "prose-apply":
                self._handle_source_grounded_prose_apply(project_id)
                return

            if (
                action == "governed-drafts"
                and len(parts) == 6
                and parts[5] == "production-derivative-candidate"
            ):
                self._handle_production_derivative_candidate(project_id, parts[4])
                return

            if (
                action == "governed-drafts"
                and len(parts) == 6
                and parts[5] == "production-derivative-apply"
            ):
                self._handle_production_derivative_apply(project_id, parts[4])
                return

            if action == "voice-captures":
                if len(parts) == 4:
                    body, error = self._read_voice_capture_upload_body()
                    if error:
                        self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                        return
                    asset = register_voice_capture(
                        project_id,
                        file_bytes=body.get("file_bytes") or b"",
                        filename=body.get("filename"),
                        mime_type=body.get("mime_type"),
                        duration_seconds=body.get("duration_seconds"),
                        capture_mode=str(body.get("capture_mode") or "free_talk"),
                        canonical_script=body.get("canonical_script") if isinstance(body.get("canonical_script"), dict) else None,
                    )
                    self._send_json(
                        {"ok": True, "asset": asset, "project": project_payload(project_id)},
                        HTTPStatus.CREATED,
                    )
                    return

                if len(parts) == 6:
                    asset_id = parts[4]
                    subaction = parts[5]
                    if subaction == "transcribe":
                        body, error = self._read_body(allow_empty=True)
                        if error:
                            self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                            return
                        job = transcribe_voice_capture(
                            project_id,
                            asset_id,
                            language=str(body.get("language") or "").strip() or None,
                        )
                        self._send_json({"ok": True, "job": job, "project": project_payload(project_id)}, HTTPStatus.ACCEPTED)
                        return

                    body, error = self._read_body()
                    if error:
                        self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                        return

                    if subaction == "transcript":
                        transcript = update_voice_transcript(project_id, asset_id, body)
                        self._send_json({"ok": True, "transcript": transcript, "project": project_payload(project_id)})
                        return

                    if subaction == "create-letter":
                        result = create_letter_from_voice_capture(project_id, asset_id, body)
                        self._send_json(
                            {
                                "ok": True,
                                "job_id": result["job"]["job_id"],
                                "job": _job_payload(result["job"]),
                                "output": result["output"],
                                "draft": result.get("draft", ""),
                                "project": project_payload(project_id),
                            },
                            HTTPStatus.ACCEPTED,
                        )
                        return

                    if subaction == "create-composition":
                        recipe = create_composition_from_voice_capture(project_id, asset_id, body)
                        self._send_json({"ok": True, **recipe, "project": project_payload(project_id)}, HTTPStatus.CREATED)
                        return

                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return

            if action == "assets" and len(parts) == 4:
                body, error = self._read_asset_upload_body()
                if error:
                    self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                    return
                asset = import_asset(
                    project_id,
                    source_path=body.get("source_path"),
                    file_bytes=body.get("file_bytes"),
                    filename=body.get("filename"),
                )
                self._send_json({"ok": True, "asset": asset, "project": project_payload(project_id)}, HTTPStatus.CREATED)
                return

            body, error = self._read_body()
            if error:
                self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return

            if action == "extract" and len(parts) == 4:
                asset_id = str(body.get("asset_id") or "").strip()
                if not asset_id:
                    raise ValueError("asset_id is required")
                job = extract_project_asset(project_id, asset_id)
                self._send_json({"ok": True, "job": job, "project": project_payload(project_id)}, HTTPStatus.ACCEPTED)
                return

            if action == "create-letter" and len(parts) == 4:
                result = create_project_letter(project_id, body)
                self._send_json(
                    {
                        "ok": True,
                        "job_id": result["job"]["job_id"],
                        "job": _job_payload(result["job"]),
                        "output": result["output"],
                        "project": project_payload(project_id),
                    },
                    HTTPStatus.ACCEPTED,
                )
                return

            if action == "compositions" and len(parts) == 4:
                recipe = create_composition(project_id, body)
                self._send_json({"ok": True, **recipe, "project": project_payload(project_id)}, HTTPStatus.CREATED)
                return

            if action == "render" and len(parts) == 4:
                composition_id = str(body.get("composition_id") or "").strip()
                if not composition_id:
                    raise ValueError("composition_id is required")
                result = start_render(project_id, composition_id)
                self._send_json({"ok": True, **result, "project": project_payload(project_id)}, HTTPStatus.ACCEPTED)
                return

            if action == "promote-render" and len(parts) == 4:
                render_id = str(body.get("render_id") or "").strip()
                if not render_id:
                    raise ValueError("render_id is required")
                result = promote_render_to_release(
                    project_id,
                    render_id,
                    title=body.get("title"),
                    theme=body.get("theme"),
                    review_fields=body.get("review_fields") if isinstance(body.get("review_fields"), dict) else None,
                )
                self._send_json({"ok": True, **result, "project": project_payload(project_id)})
                return

            if action == "revision" and len(parts) == 4:
                project = create_project_revision(project_id, title=body.get("title"))
                self._send_json({"ok": True, "project": project}, HTTPStatus.CREATED)
                return

            if action == "clone-to-brand" and len(parts) == 4:
                target_brand_id = str(body.get("brand_id") or "").strip()
                if not target_brand_id:
                    raise ValueError("brand_id is required")
                project = clone_project_to_brand(
                    project_id,
                    target_brand_id,
                    title=body.get("title"),
                )
                self._send_json({"ok": True, "project": project}, HTTPStatus.CREATED)
                return

            if action == "review-fields" and len(parts) == 4:
                fields = body.get("review_fields")
                if not isinstance(fields, dict):
                    raise ValueError("review_fields must be an object")
                project = update_project_review_fields(project_id, fields)
                self._send_json({"ok": True, "project": project_payload(str(project["project_id"]))})
                return

            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_source_grounded_outline_preview(self, project_id: str) -> None:
        body, error = self._read_body(allow_empty=True)
        if error:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_source_grounded_outline_client_authority_fields(body)
            _read_project_without_mutation(project_id)
            request = _source_grounded_outline_preview_request(project_id=project_id, body=body)
            preview = build_source_grounded_outline_preview(request)
            semantic_context, semantic_status, semantic_blockers = _source_grounded_outline_semantic_context(request.letter_id)
            payload = _source_grounded_outline_preview_payload(
                request=request,
                preview=preview,
                semantic_context=semantic_context,
                semantic_status=semantic_status,
                semantic_blockers=semantic_blockers,
            )
            self._send_json(payload)
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except (ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _handle_source_grounded_outline_acceptance(self, project_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_source_grounded_outline_client_authority_fields(body)
            _read_project_without_mutation(project_id)
            preview_request = _source_grounded_outline_preview_request(project_id=project_id, body=body)
            preview = build_source_grounded_outline_preview(preview_request)
            semantic_context, semantic_status, semantic_blockers = _source_grounded_outline_semantic_context(preview_request.letter_id)
            if not preview.ready or semantic_status != SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_COMPLETE:
                payload = _source_grounded_outline_preview_payload(
                    request=preview_request,
                    preview=preview,
                    semantic_context=semantic_context,
                    semantic_status=semantic_status,
                    semantic_blockers=semantic_blockers,
                )
                payload["ok"] = False
                payload["status"] = "blocked"
                payload["error"] = ",".join(item.get("code", "") for item in payload["blockers"] if item.get("code")) or "outline_preview_blocked"
                self._send_json(payload, HTTPStatus.BAD_REQUEST)
                return
            submitted_preview_id = str(body.get("preview_id") or "").strip()
            if preview.preview_id != submitted_preview_id:
                self._send_json(
                    {
                        "ok": False,
                        "status": "validation_error",
                        "error": "source_grounded_preview_id_mismatch",
                        "submitted_preview_id": submitted_preview_id,
                        "rebuilt_preview_id": preview.preview_id,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return
            request = _source_grounded_outline_acceptance_request(
                preview_request=preview_request,
                preview=preview,
                body=body,
            )
            result = accept_source_grounded_outline_preview(request)
        except SourceGroundedOutlineAcceptanceNotFound as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except SourceGroundedOutlineAcceptanceIntegrityError as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        except SourceGroundedOutlineAcceptanceConflict as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        except SourceGroundedOutlineAcceptanceValidationError as exc:
            message = str(exc)
            route_status = "blocked" if message.startswith(
                f"{SOURCE_GROUNDED_ACCEPTANCE_SEMANTIC_STATUS_BLOCKED}:"
            ) or message.startswith("outline_preview_not_ready") else "validation_error"
            self._send_json(
                {"ok": False, "status": route_status, "error": message},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except (ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        if result.status == SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_CREATED:
            route_status = "created"
            http_status = HTTPStatus.CREATED
        elif result.status in {
            SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_ALREADY_LINKED,
            SOURCE_GROUNDED_OUTLINE_ACCEPTANCE_STATUS_REPAIRED_LINK,
        }:
            route_status = "linked_existing"
            http_status = HTTPStatus.OK
        else:
            route_status = result.status
            http_status = HTTPStatus.OK
        self._send_json(_source_grounded_outline_acceptance_payload(result, status=route_status), http_status)

    def _handle_source_grounded_prose_candidate(self, project_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_source_grounded_prose_candidate_client_authority_fields(body)
            generator, authorization, budget_policy = _resolve_source_grounded_prose_provider()
            signer = _source_grounded_candidate_signer()
            request = _source_grounded_prose_candidate_request(project_id=project_id, body=body)
            result = build_source_grounded_prose_candidate(
                request,
                generator=generator,
                authorization=authorization,
                budget_policy=budget_policy,
            )
            if result.status != SOURCE_GROUNDED_PROSE_CANDIDATE_STATUS_GENERATED:
                self._send_json(_source_grounded_prose_candidate_payload(result))
                return

            issued_at = datetime.now(timezone.utc)
            expires_at = _source_grounded_candidate_expiration(issued_at=issued_at)
            envelope = seal_source_grounded_candidate(
                result,
                signer=signer,
                candidate_intent_ref=request.candidate_intent_ref,
                issued_at=issued_at.isoformat(),
                expires_at=expires_at,
            )
            self._send_json(
                _source_grounded_prose_candidate_payload(
                    result,
                    envelope=envelope,
                    expires_at=expires_at,
                )
            )
        except SourceGroundedProseProviderAuthorizationError as exc:
            self._send_json(
                {"ok": False, "status": "provider_not_authorized", "error": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except (ValueError, TypeError, SourceGroundedCandidateEnvelopeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _handle_source_grounded_prose_apply(self, project_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_source_grounded_prose_apply_client_authority_fields(body)
            verifier = _source_grounded_candidate_verifier()
            request = _source_grounded_prose_apply_request(project_id=project_id, body=body)
            result = apply_source_grounded_prose_candidate(request, verifier=verifier)
        except SourceGroundedProseProviderAuthorizationError as exc:
            self._send_json(
                {"ok": False, "status": "provider_not_authorized", "error": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        except SourceGroundedProseApplyNotFound as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except (SourceGroundedProseApplyIntegrityError, SourceGroundedProseApplyConflict) as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        except (SourceGroundedProseApplyValidationError, SourceGroundedCandidateEnvelopeError, ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        if result.status == SOURCE_GROUNDED_PROSE_APPLY_STATUS_CREATED:
            route_status = "created"
            http_status = HTTPStatus.CREATED
        elif result.status in {
            SOURCE_GROUNDED_PROSE_APPLY_STATUS_ALREADY_LINKED,
            SOURCE_GROUNDED_PROSE_APPLY_STATUS_REPAIRED_LINK,
        }:
            route_status = "linked_existing"
            http_status = HTTPStatus.OK
        else:
            route_status = result.status
            http_status = HTTPStatus.OK
        self._send_json(_source_grounded_prose_apply_payload(result, status=route_status), http_status)

    def _handle_production_derivative_candidate(self, project_id: str, source_letter_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_production_derivative_candidate_client_fields(body)
            request = _production_derivative_promotion_request(
                project_id=project_id,
                source_letter_id=source_letter_id,
                body=body,
            )
            candidate = validate_governed_draft_production_derivative_candidate(request)
            issued_at = datetime.now(timezone.utc)
            expires_at = _promotion_envelope_expiration(issued_at=issued_at)
            envelope_payload = _production_derivative_candidate_envelope_payload(
                candidate=candidate,
                request=request,
                issued_at=issued_at.isoformat(),
                expires_at=expires_at,
            )
            envelope = _seal_production_derivative_promotion_envelope(envelope_payload)
            self._send_json(
                _production_derivative_candidate_payload(
                    candidate,
                    envelope=envelope,
                    expires_at=expires_at,
                )
            )
        except GovernedProductionDerivativePromotionEnvelopeAuthorizationError as exc:
            self._send_json(
                {"ok": False, "status": "provider_not_authorized", "error": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
        except GovernedDraftPromotionValidationError as exc:
            self._send_json(_production_derivative_blocked_candidate_payload(exc))
        except (GovernedDraftPromotionIntegrityError, GovernedDraftPromotionConflict) as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
        except (ValueError, TypeError) as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _handle_production_derivative_apply(self, project_id: str, source_letter_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_production_derivative_apply_client_fields(body)
            payload = _verify_production_derivative_promotion_envelope(body.get("candidate_envelope"))
            route_project_id = _promotion_required_text(project_id, "project_id")
            route_source_letter_id = _promotion_required_text(source_letter_id, "source_letter_id")
            if str(payload.get("project_id") or "") != route_project_id:
                raise ValueError("candidate_envelope_project_id_mismatch")
            if str(payload.get("destination_project_id") or "") != route_project_id:
                raise ValueError("candidate_envelope_destination_project_id_mismatch")
            if str(payload.get("source_letter_id") or "") != route_source_letter_id:
                raise ValueError("candidate_envelope_source_letter_id_mismatch")
            operator_ref = _promotion_required_text(body.get("operator_ref"), "operator_ref")
            if operator_ref != str(payload.get("operator_ref") or ""):
                raise ValueError("candidate_envelope_operator_ref_mismatch")
            promotion_intent_ref = _promotion_required_text(
                body.get("promotion_intent_ref"),
                "promotion_intent_ref",
            )
            if promotion_intent_ref != str(payload.get("promotion_intent_ref") or ""):
                raise ValueError("candidate_envelope_promotion_intent_ref_mismatch")
            expected_hash = _promotion_required_text(
                body.get("expected_source_body_hash"),
                "expected_source_body_hash",
            )
            if expected_hash != str(payload.get("source_body_hash") or ""):
                raise ValueError("candidate_envelope_source_body_hash_mismatch")
            request = GovernedDraftPromotionRequest(
                source_letter_id=route_source_letter_id,
                expected_source_body_hash=expected_hash,
                promotion_intent_ref=promotion_intent_ref,
                destination_project_id=route_project_id,
                destination_brand_id=str(payload.get("destination_brand_id") or ""),
                operator_ref=operator_ref,
                target_theme=str(payload.get("target_theme") or "").strip() or None,
                operator_note=str(body.get("operator_note") or "").strip() or None,
            )
            result = promote_governed_draft_to_production_derivative(request)
        except GovernedProductionDerivativePromotionEnvelopeAuthorizationError as exc:
            self._send_json(
                {"ok": False, "status": "provider_not_authorized", "error": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except (GovernedDraftPromotionIntegrityError, GovernedDraftPromotionConflict) as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        except (
            GovernedDraftPromotionValidationError,
            GovernedProductionDerivativePromotionEnvelopeError,
            ValueError,
            TypeError,
        ) as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "invalid_request", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        route_status = "already_promoted" if result.status == "already_promoted" else "created"
        http_status = HTTPStatus.OK if result.status == "already_promoted" else HTTPStatus.CREATED
        self._send_json(_production_derivative_apply_payload(result, status=route_status), http_status)

    def _handle_governed_draft_open(self, project_id: str) -> None:
        body, error = self._read_body()
        if error:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": error},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            _reject_governed_draft_client_authority_fields(body)
            proposal_id = str(body.get("proposal_id") or "").strip()
            draft_intent_ref = str(body.get("draft_intent_ref") or "").strip()
            selected_passages = body.get("selected_passages")
            if not proposal_id:
                raise ValueError("proposal_id is required")
            if not draft_intent_ref:
                raise ValueError("draft_intent_ref is required")
            if not isinstance(selected_passages, list) or not selected_passages:
                raise ValueError("selected_source_passages_required")

            working_title = str(body.get("working_title") or "").strip()
            writer_note = str(body.get("writer_note") or "").strip()
            readiness = _derive_governed_project_studio_readiness(
                proposal_id=proposal_id,
                draft_intent_ref=draft_intent_ref,
                selected_passages=selected_passages,
                working_title=working_title,
                writer_note=writer_note,
            )
            if not readiness.ready:
                blockers = _blockers_payload(readiness)
                codes = ", ".join(item.get("code", "") for item in blockers if item.get("code"))
                self._send_json(
                    {
                        "ok": False,
                        "status": "blocked",
                        "error": codes or "governed_drafting_brief_not_ready",
                        "blockers": blockers,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return

            result = open_governed_drafting_brief_in_project_studio(
                GovernedProjectStudioHandoffRequest(
                    project_id=project_id,
                    readiness=readiness,
                    actor_ref=str(body.get("actor_ref") or "operator.local").strip() or "operator.local",
                    draft_intent_ref=draft_intent_ref,
                    selected_source_asset_ids=tuple(body.get("selected_source_asset_ids") or ()),
                    selected_passages=tuple(selected_passages),
                    working_title=working_title,
                    writer_note=writer_note,
                )
            )
        except GovernedProjectStudioHandoffNotFound as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except GovernedProjectStudioHandoffConflict as exc:
            self._send_json(
                {"ok": False, "status": "conflict", "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        except (GovernedProjectStudioHandoffValidationError, ValueError) as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except FileNotFoundError as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.NOT_FOUND,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "status": "validation_error", "error": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        route_status = "linked_existing" if result.status in {"already_linked", "repaired_link"} else "created"
        http_status = HTTPStatus.OK if route_status == "linked_existing" else HTTPStatus.CREATED
        self._send_json(_governed_draft_result_payload(result, status=route_status), http_status)

    def _handle_voice_capture_project_post(self) -> None:
        body, error = self._read_voice_capture_upload_body()
        if error:
            self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        try:
            project = create_project(
                title=body.get("title") or "Voice Capture",
                brand_id=body.get("brand_id") or DEFAULT_BRAND_ID,
            )
            project_id = str(project["project_id"])
            asset = register_voice_capture(
                project_id,
                file_bytes=body.get("file_bytes") or b"",
                filename=body.get("filename"),
                mime_type=body.get("mime_type"),
                duration_seconds=body.get("duration_seconds"),
                capture_mode=str(body.get("capture_mode") or "free_talk"),
                canonical_script=body.get("canonical_script") if isinstance(body.get("canonical_script"), dict) else None,
            )
            self._send_json(
                {"ok": True, "project": project_payload(project_id), "asset": asset},
                HTTPStatus.CREATED,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _read_body(self, allow_empty: bool = False) -> Tuple[Dict[str, Any], Optional[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            if allow_empty:
                return {}, None
            return {}, "request body is required"

        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            return {}, f"invalid JSON: {exc}"

        if not isinstance(parsed, dict):
            return {}, "request body must be a JSON object"
        return parsed, None

    def _read_multipart_form_body(self) -> Tuple[Dict[str, Any], Optional[str]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            return self._read_body()

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        message = BytesParser(policy=email_default_policy).parsebytes(
            b"Content-Type: "
            + content_type.encode("utf-8")
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + raw
        )
        body: Dict[str, Any] = {}
        if message.is_multipart():
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                payload = part.get_payload(decode=True) or b""
                filename = part.get_filename()
                if filename:
                    body["filename"] = filename
                    body["file_bytes"] = payload
                    body["mime_type"] = part.get_content_type()
                else:
                    body[str(name)] = payload.decode("utf-8", errors="replace").strip()
        return body, None

    def _read_voice_capture_upload_body(self) -> Tuple[Dict[str, Any], Optional[str]]:
        body, error = self._read_multipart_form_body()
        if error:
            return {}, error
        if not body.get("file_bytes"):
            return {}, "recording file is required"

        if body.get("duration_seconds") not in (None, ""):
            try:
                body["duration_seconds"] = max(float(body.get("duration_seconds") or 0), 0.0)
            except (TypeError, ValueError):
                return {}, "duration_seconds must be numeric"
        else:
            body["duration_seconds"] = None

        canonical_script = body.get("canonical_script")
        if isinstance(canonical_script, str) and canonical_script.strip():
            try:
                parsed = json.loads(canonical_script)
            except json.JSONDecodeError:
                parsed = {"text": canonical_script}
            canonical_script = parsed if isinstance(parsed, dict) else {"text": str(canonical_script)}
        if not isinstance(canonical_script, dict):
            canonical_script = {}
        for source_key, target_key in (
            ("canonical_script_text", "text"),
            ("canonical_script_source_reference", "source_reference"),
            ("canonical_script_source_ref", "source_reference"),
            ("canonical_script_source_asset_id", "source_asset_id"),
            ("canonical_script_letter_id", "letter_id"),
        ):
            value = str(body.get(source_key) or "").strip()
            if value:
                canonical_script[target_key] = value
        passage_ids_value = body.get("canonical_script_passage_ids")
        if isinstance(passage_ids_value, str) and passage_ids_value.strip():
            try:
                parsed_ids = json.loads(passage_ids_value)
                if isinstance(parsed_ids, list):
                    canonical_script["passage_ids"] = parsed_ids
            except json.JSONDecodeError:
                canonical_script["passage_ids"] = [
                    item.strip()
                    for item in passage_ids_value.split(",")
                    if item.strip()
                ]
        body["canonical_script"] = canonical_script or None
        return body, None

    def _read_asset_upload_body(self) -> Tuple[Dict[str, Any], Optional[str]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            return self._read_body()

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        message = BytesParser(policy=email_default_policy).parsebytes(
            b"Content-Type: "
            + content_type.encode("utf-8")
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + raw
        )
        body: Dict[str, Any] = {}
        if message.is_multipart():
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                payload = part.get_payload(decode=True) or b""
                if name == "source_path":
                    body["source_path"] = payload.decode("utf-8", errors="replace").strip() or None
                elif name == "file":
                    filename = part.get_filename()
                    if filename:
                        body["filename"] = filename
                        body["file_bytes"] = payload
        if not body.get("file_bytes") and not body.get("source_path"):
            return {}, "file or source_path is required"
        return body, None

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(path.name)
        self.send_response(status)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


class ReleaseServer(ThreadingHTTPServer):
    quiet: bool = False


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, quiet: bool = False) -> None:
    server = ReleaseServer((host, port), ReleaseRequestHandler)
    server.quiet = quiet
    print(f"Letters of Light campaign manager: http://{host}:{port}/")
    server.serve_forever()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.letters_of_light.release_server",
        description="Local Letters of Light campaign manager",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    serve(host=args.host, port=args.port, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
