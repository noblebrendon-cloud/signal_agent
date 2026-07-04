from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from app.letters_of_light import creation_manager, project_studio
from app.letters_of_light.governed_handoff import GOVERNED_HANDOFF_METADATA_KEY
from app.letters_of_light.release import _letter_dir, _read_json
from app.letters_of_light.source_grounded_drafting import (
    SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY,
    SOURCE_GROUNDED_DRAFTING_METADATA_KEY,
)
from app.letters_of_light.source_grounded_prose_apply import (
    SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY,
    SOURCE_GROUNDED_PROSE_APPLICATION_METADATA_KEY,
)
from signal_agent.formal_governance.hashing import short_hash, stable_hash


RECEIPT_SCHEMA_VERSION = "letters_of_light.production_promotion.v1"
PRODUCTION_PROMOTION_METADATA_KEY = "production_promotion"
GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY = "governed_production_promotions"
AUTHORITY_FALSE: Dict[str, bool] = {
    "production_pipeline": False,
    "release_eligibility": False,
    "approval": False,
    "export": False,
    "schedule": False,
    "publication": False,
    "platform_action": False,
    "oauth": False,
}


class GovernedProductionPromotionError(Exception):
    """Base error for governed production promotion validation."""


class GovernedProductionPromotionValidationError(GovernedProductionPromotionError):
    """Raised when a request or source draft is not promotable."""


class GovernedProductionPromotionConflict(GovernedProductionPromotionError):
    """Raised when existing durable state conflicts with promotion validation."""


class GovernedProductionPromotionIntegrityError(GovernedProductionPromotionError):
    """Raised when durable promotion source state is malformed."""


@dataclass(frozen=True)
class GovernedProductionPromotionResult:
    status: str
    promotion_id: str
    project_id: str
    source_letter_id: str
    target_letter_id: str
    creation_job_id: Optional[str]
    promotion_receipt: Dict[str, Any]
    project: Dict[str, Any]
    job: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "promotion_id": self.promotion_id,
            "project_id": self.project_id,
            "source_letter_id": self.source_letter_id,
            "target_letter_id": self.target_letter_id,
            "creation_job_id": self.creation_job_id,
            "job_id": self.creation_job_id,
            "promotion_receipt": dict(self.promotion_receipt),
            "project": dict(self.project),
            "job": dict(self.job) if isinstance(self.job, Mapping) else None,
        }


@dataclass(frozen=True)
class GovernedProductionPromotionRequest:
    project_id: str
    source_letter_id: str
    operator_ref: str
    promotion_intent_ref: str
    expected_source_body_hash: str
    expected_source_record_hash: str
    expected_source_lineage_hash: str
    expected_source_manifest_hash: Optional[str] = None


def compute_source_body_hash(source: Mapping[str, Any] | str) -> str:
    text = str(source.get("text") or "") if isinstance(source, Mapping) else str(source or "")
    return stable_hash(text)


def compute_source_record_hash(source_letter: Mapping[str, Any]) -> str:
    return stable_hash(_source_record_payload(source_letter))


def compute_source_lineage_hash(source_letter: Mapping[str, Any]) -> str:
    return stable_hash(_source_lineage_payload(source_letter))


def compute_source_manifest_hash(source_manifest: Mapping[str, Any] | None) -> str:
    if not isinstance(source_manifest, Mapping) or not source_manifest:
        return ""
    return stable_hash(
        {
            "record": _source_record_payload(source_manifest),
            "lineage": _source_lineage_payload(source_manifest),
        }
    )


def compute_promotion_id(
    *,
    source_letter_id: str,
    source_body_hash: str,
    source_record_hash: str,
    source_lineage_hash: str,
    promotion_intent_ref: str,
) -> str:
    return "governed_production_promotion." + short_hash(
        {
            "source_letter_id": str(source_letter_id),
            "source_body_hash": str(source_body_hash),
            "source_record_hash": str(source_record_hash),
            "source_lineage_hash": str(source_lineage_hash),
            "promotion_intent_ref": str(promotion_intent_ref),
        }
    )


def compute_target_letter_id(promotion_id: str) -> str:
    return "production_derivative_" + short_hash(("target_letter_id", str(promotion_id)))


def validate_governed_draft_for_production_promotion(
    request: GovernedProductionPromotionRequest,
) -> Dict[str, Any]:
    _validate_request(request)
    source_dir = _letter_dir(request.source_letter_id)
    source = _read_json(source_dir / "letter.json")
    manifest = _read_json(source_dir / "manifest.json")
    if not source:
        raise GovernedProductionPromotionValidationError("source_letter_missing")
    if str(source.get("letter_id") or "") != request.source_letter_id:
        raise GovernedProductionPromotionIntegrityError("source_letter_id_mismatch")
    if str(source.get("lifecycle_state") or "") != "draft":
        raise GovernedProductionPromotionValidationError("source_lifecycle_state_not_draft")
    if not str(source.get("text") or ""):
        raise GovernedProductionPromotionValidationError("source_text_required")

    metadata = _mapping(source.get("metadata"))
    if not _governed_handoff_ids(metadata):
        raise GovernedProductionPromotionValidationError("governed_handoff_metadata_required")
    _reject_public_authority(source_dir, source, metadata)

    project = _validated_project(request, metadata)
    hashes = {
        "source_body_hash": compute_source_body_hash(source),
        "source_record_hash": compute_source_record_hash(source),
        "source_lineage_hash": compute_source_lineage_hash(source),
        "source_manifest_hash": compute_source_manifest_hash(manifest),
    }
    _reject_hash_mismatches(request, hashes)
    lineage = _receipt_lineage(metadata)
    return {
        "request": request,
        "source_letter": dict(source),
        "source_manifest": dict(manifest),
        "source_metadata": dict(metadata),
        "project": dict(project),
        "hashes": hashes,
        "lineage": lineage,
    }


def promote_governed_draft_to_production_derivative(
    *,
    project_id: str,
    source_letter_id: str,
    operator_ref: str,
    promotion_intent_ref: str,
    expected_source_body_hash: str,
    expected_source_record_hash: str,
    expected_source_lineage_hash: str,
    expected_source_manifest_hash: str = "",
    wait_for_completion: bool = False,
    wait_timeout: float = 0,
) -> GovernedProductionPromotionResult:
    request = GovernedProductionPromotionRequest(
        project_id=project_id,
        source_letter_id=source_letter_id,
        operator_ref=operator_ref,
        promotion_intent_ref=promotion_intent_ref,
        expected_source_body_hash=expected_source_body_hash,
        expected_source_record_hash=expected_source_record_hash,
        expected_source_lineage_hash=expected_source_lineage_hash,
        expected_source_manifest_hash=expected_source_manifest_hash or None,
    )
    context = validate_governed_draft_for_production_promotion(request)
    receipt = build_governed_production_promotion_receipt(request)
    promotion_id = str(receipt["promotion_id"])
    target_letter_id = compute_target_letter_id(promotion_id)
    if target_letter_id == source_letter_id:
        raise GovernedProductionPromotionConflict("target_letter_id_reuses_source_letter_id")

    _raise_on_same_intent_hash_conflict(project_id, receipt)
    existing = _existing_project_promotion(project_id, promotion_id)
    if existing:
        return _existing_result(project_id, promotion_id, existing)

    repaired = _repair_project_index_from_target_if_possible(project_id, promotion_id, receipt)
    if repaired:
        return _existing_result(project_id, promotion_id, repaired)

    source = dict(context["source_letter"])
    source_metadata = dict(context["source_metadata"])
    project = dict(context["project"])
    created_at = project_studio._utc_now()
    starting_receipt = _receipt_with_runtime_state(
        receipt,
        target_letter_id=target_letter_id,
        creation_job_id=None,
        status="starting",
        created_at=created_at,
        production_pipeline=False,
    )
    _record_project_promotion(project_id, starting_receipt)

    try:
        started_input_receipt = _receipt_with_runtime_state(
            receipt,
            target_letter_id=target_letter_id,
            creation_job_id=None,
            status="creation_job_started",
            created_at=created_at,
            production_pipeline=True,
        )
        job = creation_manager.start_creation_job(
            theme=str(source.get("theme") or target_letter_id),
            manual_text=str(source.get("text") or ""),
            parent_letter_id=source_letter_id,
            project_id=project_id,
            source_asset_ids=_source_asset_ids(source_metadata),
            source_passages=_selected_passages(source_metadata),
            brand_id=str(source_metadata.get("brand_id") or project.get("brand_id") or ""),
            brand_version=str(source_metadata.get("brand_version") or project.get("brand_version") or "1"),
            requested_letter_id=target_letter_id,
            initial_letter_metadata=_initial_target_metadata(
                request=request,
                source=source,
                source_metadata=source_metadata,
                project=project,
            ),
            production_promotion_receipt=started_input_receipt,
        )
    except Exception as exc:
        failed_receipt = _receipt_with_runtime_state(
            receipt,
            target_letter_id=target_letter_id,
            creation_job_id=None,
            status="failed_to_start",
            created_at=created_at,
            production_pipeline=False,
            error=str(exc),
        )
        _record_project_promotion(project_id, failed_receipt)
        raise

    creation_job_id = str(job.get("job_id") or "")
    started_receipt = dict(job.get("production_promotion_receipt") or started_input_receipt)
    started_receipt = _receipt_with_runtime_state(
        started_receipt,
        target_letter_id=target_letter_id,
        creation_job_id=creation_job_id,
        status="creation_job_started",
        created_at=created_at,
        production_pipeline=True,
    )
    _record_project_promotion(project_id, started_receipt)
    final_job = job
    if wait_for_completion and creation_job_id:
        final_job = creation_manager.wait_for_creation_job(
            creation_job_id,
            timeout=wait_timeout or None,
        ) or job
    result_status = "failed" if str((final_job or {}).get("status") or "") == "failed" else "creation_job_started"
    return GovernedProductionPromotionResult(
        status=result_status,
        promotion_id=promotion_id,
        project_id=project_id,
        source_letter_id=source_letter_id,
        target_letter_id=target_letter_id,
        creation_job_id=creation_job_id,
        promotion_receipt=started_receipt,
        project=project_studio._read_project(project_id),
        job=dict(final_job or {}),
    )


def build_governed_production_promotion_receipt(
    request: GovernedProductionPromotionRequest,
) -> Dict[str, Any]:
    context = validate_governed_draft_for_production_promotion(request)
    hashes = dict(context["hashes"])
    promotion_id = compute_promotion_id(
        source_letter_id=request.source_letter_id,
        source_body_hash=hashes["source_body_hash"],
        source_record_hash=hashes["source_record_hash"],
        source_lineage_hash=hashes["source_lineage_hash"],
        promotion_intent_ref=request.promotion_intent_ref,
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "promotion_id": promotion_id,
        "project_id": request.project_id,
        "source_letter_id": request.source_letter_id,
        "operator_ref": request.operator_ref,
        "promotion_intent_ref": request.promotion_intent_ref,
        "source_body_hash": hashes["source_body_hash"],
        "source_record_hash": hashes["source_record_hash"],
        "source_lineage_hash": hashes["source_lineage_hash"],
        "source_manifest_hash": hashes["source_manifest_hash"],
        "target_input_text_hash": hashes["source_body_hash"],
        "status": "validated",
        "lineage": dict(context["lineage"]),
        "authority": dict(AUTHORITY_FALSE),
    }


def _initial_target_metadata(
    *,
    request: GovernedProductionPromotionRequest,
    source: Mapping[str, Any],
    source_metadata: Mapping[str, Any],
    project: Mapping[str, Any],
) -> Dict[str, Any]:
    governed_handoff = _mapping(source_metadata.get(GOVERNED_HANDOFF_METADATA_KEY))
    source_grounding = _mapping(source_metadata.get("source_grounding") or governed_handoff.get("source_grounding"))
    parent_root = (
        source_metadata.get("parent_root_letter_id")
        or source_metadata.get("parent_letter_id")
        or source.get("parent_letter_id")
        or request.source_letter_id
    )
    metadata: Dict[str, Any] = {
        "parent_letter_id": request.source_letter_id,
        "revision_of": request.source_letter_id,
        "parent_root_letter_id": str(parent_root),
        "project_id": request.project_id,
        "brand_id": str(source_metadata.get("brand_id") or project.get("brand_id") or ""),
        "brand_version": str(source_metadata.get("brand_version") or project.get("brand_version") or "1"),
        "source_asset_ids": _source_asset_ids(source_metadata),
        "selected_source_passages": _selected_passages(source_metadata),
        "release_eligible": False,
        "approval_status": "unapproved",
        "review_status": "unreviewed",
        "publication_state": "not_started",
        "production_derivative_from_governed_draft": True,
        "authority": dict(AUTHORITY_FALSE),
    }
    handoff_ids = _governed_handoff_ids(source_metadata)
    if handoff_ids:
        metadata["governed_handoff_id"] = handoff_ids[0]
    if governed_handoff:
        metadata[GOVERNED_HANDOFF_METADATA_KEY] = dict(governed_handoff)
    if source_grounding:
        metadata["source_grounding"] = dict(source_grounding)
    for key in (
        "source_snapshot_ref",
        "source_support_refs",
        "source_packet_ref",
        "evidence_packet_path",
        "parent_root_letter_path",
        "campaign_id",
    ):
        if source_metadata.get(key):
            metadata[key] = source_metadata[key]
    return metadata


def _receipt_with_runtime_state(
    receipt: Mapping[str, Any],
    *,
    target_letter_id: str,
    creation_job_id: Optional[str],
    status: str,
    created_at: str,
    production_pipeline: bool,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    updated = dict(receipt)
    updated["target_letter_id"] = str(target_letter_id)
    updated["creation_job_id"] = str(creation_job_id or "")
    updated["status"] = str(status)
    updated["created_at"] = str(created_at)
    authority = dict(updated.get("authority") or {})
    authority["production_pipeline"] = bool(production_pipeline)
    for key in (
        "release_eligibility",
        "approval",
        "export",
        "schedule",
        "publication",
        "platform_action",
        "oauth",
    ):
        authority[key] = False
    updated["authority"] = authority
    if error:
        updated["error"] = str(error)
    else:
        updated.pop("error", None)
    return updated


def _record_project_promotion(project_id: str, receipt: Mapping[str, Any]) -> Dict[str, Any]:
    def mutate(project: Dict[str, Any]) -> None:
        index = project.setdefault(GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY, {})
        if not isinstance(index, dict):
            raise GovernedProductionPromotionIntegrityError(
                "governed_production_promotions_index_malformed"
            )
        index[str(receipt["promotion_id"])] = _project_index_entry(receipt)

    return project_studio._update_project(project_id, mutate)


def _project_index_entry(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": str(receipt.get("schema_version") or RECEIPT_SCHEMA_VERSION),
        "promotion_id": str(receipt.get("promotion_id") or ""),
        "project_id": str(receipt.get("project_id") or ""),
        "source_letter_id": str(receipt.get("source_letter_id") or ""),
        "target_letter_id": str(receipt.get("target_letter_id") or ""),
        "creation_job_id": str(receipt.get("creation_job_id") or ""),
        "operator_ref": str(receipt.get("operator_ref") or ""),
        "promotion_intent_ref": str(receipt.get("promotion_intent_ref") or ""),
        "source_body_hash": str(receipt.get("source_body_hash") or ""),
        "source_record_hash": str(receipt.get("source_record_hash") or ""),
        "source_lineage_hash": str(receipt.get("source_lineage_hash") or ""),
        "source_manifest_hash": str(receipt.get("source_manifest_hash") or ""),
        "target_input_text_hash": str(receipt.get("target_input_text_hash") or ""),
        "status": str(receipt.get("status") or ""),
        "created_at": str(receipt.get("created_at") or ""),
        "authority": dict(receipt.get("authority") or {}),
        "lineage": dict(receipt.get("lineage") or {}),
        "promotion_receipt": dict(receipt),
    }


def _existing_project_promotion(project_id: str, promotion_id: str) -> Dict[str, Any]:
    project = project_studio._read_project(project_id)
    index = project.get(GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY)
    if index is None:
        return {}
    if not isinstance(index, Mapping):
        raise GovernedProductionPromotionIntegrityError(
            "governed_production_promotions_index_malformed"
        )
    entry = index.get(promotion_id)
    if not isinstance(entry, Mapping):
        return {}
    _raise_on_index_target_mismatch(entry, promotion_id)
    return dict(entry)


def _existing_result(
    project_id: str,
    promotion_id: str,
    entry: Mapping[str, Any],
) -> GovernedProductionPromotionResult:
    receipt = dict(entry.get("promotion_receipt") or entry)
    target_letter_id = str(entry.get("target_letter_id") or receipt.get("target_letter_id") or "")
    creation_job_id = str(entry.get("creation_job_id") or entry.get("job_id") or receipt.get("creation_job_id") or "")
    job = creation_manager.get_creation_job(creation_job_id) if creation_job_id else None
    status = str(entry.get("status") or receipt.get("status") or "")
    if isinstance(job, Mapping) and str(job.get("status") or "") == "failed":
        status = "failed"
    return GovernedProductionPromotionResult(
        status=status,
        promotion_id=promotion_id,
        project_id=project_id,
        source_letter_id=str(entry.get("source_letter_id") or receipt.get("source_letter_id") or ""),
        target_letter_id=target_letter_id,
        creation_job_id=creation_job_id or None,
        promotion_receipt=receipt,
        project=project_studio._read_project(project_id),
        job=dict(job) if isinstance(job, Mapping) else None,
    )


def _raise_on_same_intent_hash_conflict(project_id: str, receipt: Mapping[str, Any]) -> None:
    project = project_studio._read_project(project_id)
    index = project.get(GOVERNED_PRODUCTION_PROMOTIONS_INDEX_KEY)
    if not isinstance(index, Mapping):
        return
    for entry in index.values():
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("source_letter_id") or "") != str(receipt.get("source_letter_id") or ""):
            continue
        if str(entry.get("promotion_intent_ref") or "") != str(receipt.get("promotion_intent_ref") or ""):
            continue
        for key in ("source_body_hash", "source_record_hash", "source_lineage_hash", "source_manifest_hash"):
            if str(entry.get(key) or "") != str(receipt.get(key) or ""):
                raise GovernedProductionPromotionConflict(f"same_source_and_intent_changed_{key}")


def _repair_project_index_from_target_if_possible(
    project_id: str,
    promotion_id: str,
    fallback_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    matches = _target_letters_with_promotion(promotion_id)
    if not matches:
        return {}
    if len(matches) > 1:
        raise GovernedProductionPromotionIntegrityError(
            "duplicate_targets_for_governed_production_promotion"
        )
    target_letter_id, target_receipt = matches[0]
    receipt = dict(fallback_receipt)
    receipt.update(dict(target_receipt))
    receipt["project_id"] = project_id
    receipt["promotion_id"] = promotion_id
    receipt["target_letter_id"] = target_letter_id
    if not receipt.get("created_at"):
        receipt["created_at"] = project_studio._utc_now()
    if not receipt.get("status"):
        receipt["status"] = "creation_job_started" if receipt.get("creation_job_id") else "validated"
    _record_project_promotion(project_id, receipt)
    return _existing_project_promotion(project_id, promotion_id)


def _raise_on_index_target_mismatch(entry: Mapping[str, Any], promotion_id: str) -> None:
    indexed_target_id = str(entry.get("target_letter_id") or "")
    matches = _target_letters_with_promotion(promotion_id)
    if len(matches) > 1:
        raise GovernedProductionPromotionIntegrityError(
            "duplicate_targets_for_governed_production_promotion"
        )
    if matches and indexed_target_id and matches[0][0] != indexed_target_id:
        raise GovernedProductionPromotionIntegrityError(
            "project_index_target_id_disagrees_with_target_metadata"
        )
    if indexed_target_id:
        target = _read_json(_letter_dir(indexed_target_id) / "letter.json")
        if target:
            metadata = _mapping(target.get("metadata"))
            target_receipt = _mapping(metadata.get(PRODUCTION_PROMOTION_METADATA_KEY))
            if str(target_receipt.get("promotion_id") or "") != promotion_id:
                raise GovernedProductionPromotionIntegrityError(
                    "project_index_target_metadata_disagrees_with_promotion_id"
                )


def _target_letters_with_promotion(promotion_id: str) -> List[tuple[str, Dict[str, Any]]]:
    letters_root = _letter_dir("__governed_production_probe__").parent
    if not letters_root.exists():
        return []
    matches: List[tuple[str, Dict[str, Any]]] = []
    for child in letters_root.iterdir():
        if not child.is_dir():
            continue
        letter = _read_json(child / "letter.json")
        if not letter:
            continue
        metadata = _mapping(letter.get("metadata"))
        receipt = _mapping(metadata.get(PRODUCTION_PROMOTION_METADATA_KEY))
        if str(receipt.get("promotion_id") or "") == promotion_id:
            matches.append((str(letter.get("letter_id") or child.name), receipt))
    return matches


def _validate_request(request: GovernedProductionPromotionRequest) -> None:
    _require_id(request.project_id, "project_id")
    _require_id(request.source_letter_id, "source_letter_id")
    for label in (
        "operator_ref",
        "promotion_intent_ref",
        "expected_source_body_hash",
        "expected_source_record_hash",
        "expected_source_lineage_hash",
    ):
        _required_text(getattr(request, label), label)
    if request.expected_source_manifest_hash is not None:
        _required_text(request.expected_source_manifest_hash, "expected_source_manifest_hash")


def _validated_project(
    request: GovernedProductionPromotionRequest,
    source_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    try:
        project = project_studio._read_project(request.project_id)
    except FileNotFoundError as exc:
        raise GovernedProductionPromotionValidationError("project_not_found") from exc

    source_project_id = str(source_metadata.get("project_id") or "")
    if source_project_id and source_project_id != request.project_id:
        raise GovernedProductionPromotionValidationError("source_project_mismatch")

    project_brand_id = str(project.get("brand_id") or "")
    source_brand_id = str(source_metadata.get("brand_id") or "")
    if source_brand_id and project_brand_id and source_brand_id != project_brand_id:
        raise GovernedProductionPromotionValidationError("source_brand_mismatch")

    governed_handoff = _mapping(source_metadata.get(GOVERNED_HANDOFF_METADATA_KEY))
    destination_brand_ref = str(governed_handoff.get("destination_brand_ref") or "")
    if destination_brand_ref and project_brand_id and destination_brand_ref != project_brand_id:
        raise GovernedProductionPromotionValidationError("governed_handoff_destination_brand_mismatch")
    return project


def _reject_hash_mismatches(
    request: GovernedProductionPromotionRequest,
    hashes: Mapping[str, str],
) -> None:
    if request.expected_source_body_hash != hashes["source_body_hash"]:
        raise GovernedProductionPromotionValidationError("source_body_hash_mismatch")
    if request.expected_source_record_hash != hashes["source_record_hash"]:
        raise GovernedProductionPromotionValidationError("source_record_hash_mismatch")
    if request.expected_source_lineage_hash != hashes["source_lineage_hash"]:
        raise GovernedProductionPromotionValidationError("source_lineage_hash_mismatch")
    if (
        request.expected_source_manifest_hash is not None
        and request.expected_source_manifest_hash != hashes["source_manifest_hash"]
    ):
        raise GovernedProductionPromotionValidationError("source_manifest_hash_mismatch")


def _reject_public_authority(
    source_dir: Any,
    source: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> None:
    if (source_dir / "release.json").exists():
        raise GovernedProductionPromotionValidationError("source_release_json_not_allowed")
    if bool(source.get("release_eligible")) or bool(metadata.get("release_eligible")):
        raise GovernedProductionPromotionValidationError("source_release_eligible_not_allowed")

    for field in (
        "release_state",
        "release_id",
        "release_candidate_id",
        "approved",
        "approved_at",
        "approval_id",
        "approved_by",
        "scheduled_at",
        "schedule_id",
        "exported_at",
        "export_id",
        "publication_id",
        "publication_url",
        "published_at",
        "platform_action_id",
        "oauth_token_ref",
        "oauth_credential_ref",
    ):
        if source.get(field) or metadata.get(field):
            raise GovernedProductionPromotionValidationError(f"source_public_authority_field_not_allowed:{field}")

    if str(source.get("approval_status") or metadata.get("approval_status") or "unapproved") not in {"", "unapproved"}:
        raise GovernedProductionPromotionValidationError("source_approval_status_not_allowed")
    if str(source.get("review_status") or metadata.get("review_status") or "unreviewed") not in {"", "unreviewed"}:
        raise GovernedProductionPromotionValidationError("source_review_status_not_allowed")
    if str(source.get("publication_state") or metadata.get("publication_state") or "not_started") not in {"", "not_started"}:
        raise GovernedProductionPromotionValidationError("source_publication_state_not_allowed")

    for label, authority in _authority_sources(metadata):
        for key in ("release_eligibility", "approval", "package_readiness", "schedule", "export", "publication", "queue", "platform_action", "oauth"):
            if authority.get(key) is True:
                raise GovernedProductionPromotionValidationError(f"source_authority_not_allowed:{label}.{key}")


def _authority_sources(metadata: Mapping[str, Any]) -> List[tuple[str, Dict[str, Any]]]:
    governed_handoff = _mapping(metadata.get(GOVERNED_HANDOFF_METADATA_KEY))
    source_grounded_drafting = _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY))
    accepted_plan = _mapping(
        metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        or source_grounded_drafting.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    )
    source_grounded_prose = _mapping(metadata.get(SOURCE_GROUNDED_PROSE_APPLICATION_METADATA_KEY))
    applied_candidate = _mapping(
        metadata.get(SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY)
        or source_grounded_prose.get(SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY)
    )
    sources = [
        ("metadata", _mapping(metadata.get("authority"))),
        ("governed_handoff", _mapping(governed_handoff.get("authority"))),
        ("accepted_plan", _mapping(accepted_plan.get("authority"))),
        ("applied_candidate", _mapping(applied_candidate.get("authority"))),
    ]
    return [(label, authority) for label, authority in sources if authority]


def _source_record_payload(source_letter: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _mapping(source_letter.get("metadata"))
    return {
        "letter_id": str(source_letter.get("letter_id") or ""),
        "artifact_type": str(source_letter.get("artifact_type") or ""),
        "lifecycle_state": str(source_letter.get("lifecycle_state") or ""),
        "parent_letter_id": str(source_letter.get("parent_letter_id") or ""),
        "title": str(source_letter.get("title") or ""),
        "theme": str(source_letter.get("theme") or ""),
        "text": str(source_letter.get("text") or ""),
        "metadata": {
            "project_id": str(metadata.get("project_id") or ""),
            "brand_id": str(metadata.get("brand_id") or ""),
            "brand_version": str(metadata.get("brand_version") or ""),
            "parent_letter_id": str(metadata.get("parent_letter_id") or ""),
            "parent_root_letter_id": str(metadata.get("parent_root_letter_id") or ""),
            "revision_of": str(metadata.get("revision_of") or ""),
            "release_eligible": bool(metadata.get("release_eligible")),
        },
    }


def _source_lineage_payload(source_letter: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _mapping(source_letter.get("metadata"))
    source_grounded_drafting = _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY))
    accepted_plan = _mapping(
        metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        or source_grounded_drafting.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    )
    source_grounded_prose = _mapping(metadata.get(SOURCE_GROUNDED_PROSE_APPLICATION_METADATA_KEY))
    applied_candidate = _mapping(
        metadata.get(SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY)
        or source_grounded_prose.get(SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY)
    )
    return {
        "source_letter_id": str(source_letter.get("letter_id") or ""),
        "parent_letter_id": str(source_letter.get("parent_letter_id") or metadata.get("parent_letter_id") or ""),
        "revision_of": str(metadata.get("revision_of") or ""),
        "parent_root_letter_id": str(metadata.get("parent_root_letter_id") or ""),
        "project_id": str(metadata.get("project_id") or ""),
        "brand_id": str(metadata.get("brand_id") or ""),
        "brand_version": str(metadata.get("brand_version") or ""),
        "governed_handoff_id": _governed_handoff_ids(metadata),
        GOVERNED_HANDOFF_METADATA_KEY: _mapping(metadata.get(GOVERNED_HANDOFF_METADATA_KEY)),
        "source_asset_ids": _source_asset_ids(metadata),
        "selected_source_passages": _selected_passages(metadata),
        "source_snapshot_ref": str(metadata.get("source_snapshot_ref") or ""),
        "source_support_refs": _string_list(metadata.get("source_support_refs")),
        "source_packet_ref": str(metadata.get("source_packet_ref") or ""),
        SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY: accepted_plan,
        SOURCE_GROUNDED_APPLIED_CANDIDATE_METADATA_KEY: applied_candidate,
    }


def _receipt_lineage(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    governed_handoff = _mapping(metadata.get(GOVERNED_HANDOFF_METADATA_KEY))
    source_grounding = _mapping(metadata.get("source_grounding") or governed_handoff.get("source_grounding"))
    accepted_plan = _mapping(
        metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        or _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY)).get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    )
    return {
        "governed_handoff_id": _first(
            _governed_handoff_ids(metadata)
        ),
        "proposal_id": _first(
            _string_list(metadata.get("proposal_id"))
            + _string_list(governed_handoff.get("proposal_id"))
            + _string_list(accepted_plan.get("proposal_id"))
        ),
        "canonical_node_id": _first(
            _string_list(metadata.get("canonical_node_id"))
            + _string_list(governed_handoff.get("canonical_node_id"))
            + _string_list(accepted_plan.get("canonical_node_id"))
        ),
        "source_snapshot_ref": _first(
            _string_list(metadata.get("source_snapshot_ref"))
            + _string_list(governed_handoff.get("source_snapshot_ref"))
            + _string_list(source_grounding.get("source_snapshot_ref"))
            + _string_list(accepted_plan.get("source_snapshot_ref"))
        ),
        "source_support_refs": _unique_strings(
            _string_list(metadata.get("source_support_refs"))
            + _string_list(governed_handoff.get("source_support_refs"))
            + _string_list(source_grounding.get("source_support_refs"))
            + _string_list(accepted_plan.get("source_support_refs"))
        ),
        "source_asset_ids": _source_asset_ids(metadata),
        "selected_source_passages": _selected_passages(metadata),
    }


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GovernedProductionPromotionValidationError(f"{label}_required")
    return text


def _require_id(value: str, label: str) -> str:
    text = _required_text(value, label)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise GovernedProductionPromotionValidationError(f"{label}_invalid")
    return text


def _string_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if str(value or "").strip():
        return [str(value)]
    return []


def _unique_strings(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        for item in _string_list(value):
            if item not in seen:
                result.append(item)
                seen.add(item)
    return result


def _first(values: List[str]) -> str:
    return values[0] if values else ""


def _source_asset_ids(metadata: Mapping[str, Any]) -> List[str]:
    accepted_plan = _mapping(
        metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        or _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY)).get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    )
    return _unique_strings(
        _string_list(metadata.get("source_asset_ids"))
        + _string_list(metadata.get("selected_source_asset_ids"))
        + _string_list(accepted_plan.get("selected_source_asset_ids"))
    )


def _selected_passages(metadata: Mapping[str, Any]) -> List[Dict[str, Any]]:
    passages = metadata.get("selected_source_passages")
    if not isinstance(passages, list):
        accepted_plan = _mapping(
            metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
            or _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY)).get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        )
        passages = accepted_plan.get("selected_passages")
    if not isinstance(passages, list):
        return []
    return [dict(item) for item in passages if isinstance(item, Mapping)]


def _governed_handoff_ids(metadata: Mapping[str, Any]) -> List[str]:
    governed_handoff = _mapping(metadata.get(GOVERNED_HANDOFF_METADATA_KEY))
    accepted_plan = _mapping(
        metadata.get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
        or _mapping(metadata.get(SOURCE_GROUNDED_DRAFTING_METADATA_KEY)).get(SOURCE_GROUNDED_ACCEPTED_PLAN_METADATA_KEY)
    )
    return _unique_strings(
        [
            metadata.get("governed_handoff_id"),
            metadata.get("handoff_id"),
            governed_handoff.get("governed_handoff_id"),
            governed_handoff.get("handoff_id"),
            accepted_plan.get("governed_handoff_id"),
            accepted_plan.get("handoff_id"),
        ]
    )
