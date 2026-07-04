from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from app.letters_of_light import creation_manager, project_studio
from app.letters_of_light.brand_registry import DEFAULT_BRAND_ID, get_brand
from app.letters_of_light.release import _letter_dir, _read_json
from signal_agent.formal_governance.hashing import short_hash, stable_hash


PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY = "production_derivative_promotion"
PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY = "production_derivative_promotions"
PRODUCTION_DERIVATIVE_STATUS_AUTHORITY_NOTICE = (
    "Promotion created a separate production derivative. This status view does not approve, "
    "release, export, schedule, publish, or grant platform authority."
)
PRODUCTION_DERIVATIVE_STATUS_NO_PROMOTION_NOTICE = (
    "No production derivative has been created from this governed draft."
)


class GovernedDraftPromotionError(Exception):
    """Base error for governed-draft production derivative promotion."""


class GovernedDraftPromotionValidationError(GovernedDraftPromotionError):
    """Raised when a source draft or request is not promotable."""


class GovernedDraftPromotionConflict(GovernedDraftPromotionError):
    """Raised when a promotion request conflicts with durable state."""


class GovernedDraftPromotionIntegrityError(GovernedDraftPromotionError):
    """Raised when existing promotion state is malformed."""


@dataclass(frozen=True)
class GovernedDraftPromotionRequest:
    source_letter_id: str
    expected_source_body_hash: str
    promotion_intent_ref: str
    destination_project_id: str
    destination_brand_id: str
    operator_ref: str
    target_theme: Optional[str] = None
    operator_note: Optional[str] = None


@dataclass(frozen=True)
class GovernedDraftPromotionResult:
    status: str
    promotion_id: str
    source_letter_id: str
    target_letter_id: str
    job_id: Optional[str]
    promotion_receipt: Dict[str, Any]
    project: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "promotion_id": self.promotion_id,
            "source_letter_id": self.source_letter_id,
            "target_letter_id": self.target_letter_id,
            "job_id": self.job_id,
            "promotion_receipt": self.promotion_receipt,
            "project": self.project,
        }


@dataclass(frozen=True)
class GovernedDraftPromotionCandidate:
    validation_state: str
    promotion_id: str
    source_letter_id: str
    target_letter_id: str
    source_body_hash: str
    destination_project_id: str
    destination_brand_id: str
    promotion_intent_ref: str
    operator_ref: str
    lineage_summary: Dict[str, Any]
    warnings: List[str]
    blockers: List[str]
    existing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_state": self.validation_state,
            "promotion_id": self.promotion_id,
            "source_letter_id": self.source_letter_id,
            "target_letter_id": self.target_letter_id,
            "source_body_hash": self.source_body_hash,
            "destination_project_id": self.destination_project_id,
            "destination_brand_id": self.destination_brand_id,
            "promotion_intent_ref": self.promotion_intent_ref,
            "operator_ref": self.operator_ref,
            "lineage_summary": dict(self.lineage_summary),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "existing": self.existing,
        }


def source_letter_body_hash(text: str) -> str:
    return stable_hash(str(text or ""))


def production_derivative_promotion_id(
    *,
    source_letter_id: str,
    source_body_hash: str,
    promotion_intent_ref: str,
    destination_project_id: str,
    destination_brand_id: str,
) -> str:
    return "production_derivative_promotion." + short_hash(
        (
            source_letter_id,
            source_body_hash,
            promotion_intent_ref,
            destination_project_id,
            destination_brand_id,
        )
    )


def production_derivative_target_letter_id(promotion_id: str) -> str:
    return "production_derivative_" + short_hash(("target_letter_id", promotion_id))


def validate_governed_draft_production_derivative_candidate(
    request: GovernedDraftPromotionRequest,
) -> GovernedDraftPromotionCandidate:
    source, manifest, source_metadata = _validated_source(request)
    project = _validated_destination_project(request, source_metadata)
    body_hash = source_letter_body_hash(str(source.get("text") or ""))
    promotion_id = production_derivative_promotion_id(
        source_letter_id=request.source_letter_id,
        source_body_hash=body_hash,
        promotion_intent_ref=request.promotion_intent_ref,
        destination_project_id=request.destination_project_id,
        destination_brand_id=request.destination_brand_id,
    )
    existing = _existing_project_promotion(project, promotion_id)
    _raise_on_same_intent_body_conflict(project, request, body_hash)
    target_letter_id = str(existing.get("target_letter_id") or existing.get("letter_id") or "")
    if not target_letter_id:
        target_letter_id = production_derivative_target_letter_id(promotion_id)
    if target_letter_id == request.source_letter_id:
        raise GovernedDraftPromotionConflict("target_letter_id_reuses_source_letter_id")
    _raise_on_conflicting_target(target_letter_id, promotion_id)
    return GovernedDraftPromotionCandidate(
        validation_state="valid",
        promotion_id=promotion_id,
        source_letter_id=request.source_letter_id,
        target_letter_id=target_letter_id,
        source_body_hash=body_hash,
        destination_project_id=request.destination_project_id,
        destination_brand_id=request.destination_brand_id,
        promotion_intent_ref=request.promotion_intent_ref,
        operator_ref=request.operator_ref,
        lineage_summary=_promotion_lineage_summary(source_metadata, manifest),
        warnings=[],
        blockers=[],
        existing=bool(existing),
    )


def promote_governed_draft_to_production_derivative(
    request: GovernedDraftPromotionRequest,
    *,
    now: Optional[str] = None,
) -> GovernedDraftPromotionResult:
    requested_at = str(now or project_studio._utc_now())
    source, manifest, source_metadata = _validated_source(request)
    project = _validated_destination_project(request, source_metadata)
    body_hash = source_letter_body_hash(str(source.get("text") or ""))
    promotion_id = production_derivative_promotion_id(
        source_letter_id=request.source_letter_id,
        source_body_hash=body_hash,
        promotion_intent_ref=request.promotion_intent_ref,
        destination_project_id=request.destination_project_id,
        destination_brand_id=request.destination_brand_id,
    )

    existing = _existing_project_promotion(project, promotion_id)
    if existing:
        return _existing_result(request, existing)
    _raise_on_same_intent_body_conflict(project, request, body_hash)

    target_letter_id = production_derivative_target_letter_id(promotion_id)
    if target_letter_id == request.source_letter_id:
        raise GovernedDraftPromotionConflict("target_letter_id_reuses_source_letter_id")
    _raise_on_conflicting_target(target_letter_id, promotion_id)

    receipt = _promotion_receipt(
        request=request,
        source=source,
        manifest=manifest,
        source_metadata=source_metadata,
        project=project,
        promotion_id=promotion_id,
        target_letter_id=target_letter_id,
        requested_at=requested_at,
    )
    initial_metadata = _initial_target_metadata(
        request=request,
        source=source,
        source_metadata=source_metadata,
        project=project,
    )

    _record_project_promotion(
        request.destination_project_id,
        receipt,
        status="promotion_validated",
        job_id=None,
    )

    try:
        job = creation_manager.start_creation_job(
            theme=str(request.target_theme or source.get("theme") or target_letter_id),
            manual_text=str(source.get("text") or ""),
            parent_letter_id=request.source_letter_id,
            project_id=request.destination_project_id,
            source_asset_ids=_source_asset_ids(source_metadata),
            source_passages=_selected_passages(source_metadata),
            brand_id=request.destination_brand_id,
            brand_version=str(project.get("brand_version") or get_brand(request.destination_brand_id).get("version") or "1"),
            requested_letter_id=target_letter_id,
            initial_letter_metadata=initial_metadata,
            promotion_receipt=receipt,
        )
    except Exception as exc:
        _record_project_promotion(
            request.destination_project_id,
            receipt,
            status="creation_job_start_failed",
            job_id=None,
            error=str(exc),
        )
        raise

    receipt_with_job = dict(job.get("promotion_receipt") or receipt)
    _record_project_promotion(
        request.destination_project_id,
        receipt_with_job,
        status="creation_job_started",
        job_id=str(job.get("job_id") or ""),
    )
    return GovernedDraftPromotionResult(
        status="created",
        promotion_id=promotion_id,
        source_letter_id=request.source_letter_id,
        target_letter_id=target_letter_id,
        job_id=str(job.get("job_id") or ""),
        promotion_receipt=receipt_with_job,
        project=project_studio.project_payload(request.destination_project_id),
    )


def governed_draft_production_derivative_status(
    *,
    project_id: str,
    source_letter_id: str,
) -> Dict[str, Any]:
    _required_text(project_id, "project_id")
    _require_id(source_letter_id, "source_letter_id")
    project = project_studio._read_project(project_id)
    source = _read_json(_letter_dir(source_letter_id) / "letter.json")
    if not source:
        raise FileNotFoundError(f"Source Letter not found: {source_letter_id}")

    entries = _promotion_entries_for_source(project, source_letter_id)
    if not entries:
        return {
            "source_letter_id": source_letter_id,
            "project_id": project_id,
            "promotion_found": False,
            "authority_notice": PRODUCTION_DERIVATIVE_STATUS_NO_PROMOTION_NOTICE,
        }

    entry = _latest_promotion_entry(entries)
    receipt = _mapping(entry.get("promotion_receipt")) or dict(entry)
    target_letter_id = str(
        entry.get("target_letter_id")
        or entry.get("letter_id")
        or receipt.get("target_letter_id")
        or ""
    )
    target = _read_json(_letter_dir(target_letter_id) / "letter.json") if target_letter_id else {}
    target_metadata = _mapping(target.get("metadata"))
    target_receipt = _mapping(target_metadata.get(PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY))
    if target_receipt:
        receipt = {**receipt, **target_receipt}
    job_id = str(entry.get("job_id") or entry.get("creation_job_id") or receipt.get("creation_job_id") or "")
    job = creation_manager.get_creation_job(job_id) if job_id else None
    release_record = _read_json(_letter_dir(target_letter_id) / "release.json") if target_letter_id else {}

    return {
        "source_letter_id": source_letter_id,
        "project_id": project_id,
        "promotion_found": True,
        "promotion_count": len(entries),
        "promotion": _promotion_status_payload(entry, receipt),
        "target": _target_status_payload(target_letter_id, target, target_metadata, has_release_record=bool(release_record)),
        "creation_job": _creation_job_status_payload(job_id, job),
        "pipeline": _pipeline_status_payload(target, target_metadata, job),
        "authority_notice": PRODUCTION_DERIVATIVE_STATUS_AUTHORITY_NOTICE,
    }


def _validated_source(
    request: GovernedDraftPromotionRequest,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    _require_id(request.source_letter_id, "source_letter_id")
    for label in (
        "expected_source_body_hash",
        "promotion_intent_ref",
        "destination_project_id",
        "destination_brand_id",
        "operator_ref",
    ):
        _required_text(getattr(request, label), label)

    source_dir = _letter_dir(request.source_letter_id)
    source = _read_json(source_dir / "letter.json")
    manifest = _read_json(source_dir / "manifest.json")
    if not source:
        raise GovernedDraftPromotionValidationError("source_letter_missing")
    if not manifest:
        raise GovernedDraftPromotionValidationError("source_manifest_missing")
    if str(source.get("letter_id") or "") != request.source_letter_id:
        raise GovernedDraftPromotionValidationError("source_letter_id_mismatch")
    if str(source.get("lifecycle_state") or "") != "draft":
        raise GovernedDraftPromotionValidationError("source_lifecycle_state_not_draft")
    text = str(source.get("text") or "")
    if not text:
        raise GovernedDraftPromotionValidationError("source_text_required")
    body_hash = source_letter_body_hash(text)
    if request.expected_source_body_hash != body_hash:
        raise GovernedDraftPromotionValidationError("source_body_hash_mismatch")

    metadata = _mapping(source.get("metadata"))
    if not _governed_handoff_ids(metadata):
        raise GovernedDraftPromotionValidationError("governed_handoff_metadata_required")
    if not _source_asset_ids(metadata):
        raise GovernedDraftPromotionValidationError("source_asset_ids_required")
    if not _selected_passages(metadata):
        raise GovernedDraftPromotionValidationError("selected_source_passages_required")
    _reject_source_release_authority(source_dir, source, metadata)
    return source, manifest, metadata


def _validated_destination_project(
    request: GovernedDraftPromotionRequest,
    source_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    project = project_studio._read_project(request.destination_project_id)
    project_brand_id = str(project.get("brand_id") or DEFAULT_BRAND_ID)
    if project_brand_id != request.destination_brand_id:
        raise GovernedDraftPromotionValidationError("destination_brand_mismatch")
    destination_ref = str(_mapping(source_metadata.get("governed_handoff")).get("destination_brand_ref") or "")
    if destination_ref and destination_ref != request.destination_brand_id:
        raise GovernedDraftPromotionValidationError("governed_handoff_destination_brand_mismatch")

    known_assets = {
        str(asset.get("asset_id") or "")
        for asset in project.get("assets") or []
        if isinstance(asset, Mapping)
    }
    missing_assets = [asset_id for asset_id in _source_asset_ids(source_metadata) if asset_id not in known_assets]
    if missing_assets:
        raise GovernedDraftPromotionValidationError("source_assets_not_in_destination_project")
    return project


def _promotion_lineage_summary(
    source_metadata: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    governed_handoff = _mapping(source_metadata.get("governed_handoff"))
    source_grounding = _mapping(source_metadata.get("source_grounding") or governed_handoff.get("source_grounding"))
    selected_passages = _selected_passages(source_metadata)
    return {
        "source_manifest_hash": stable_hash(manifest),
        "governed_handoff_ids": _governed_handoff_ids(source_metadata),
        "proposal_node_ids": _unique_strings(
            [
                source_metadata.get("proposal_id"),
                governed_handoff.get("proposal_id"),
                _mapping(source_metadata.get("accepted_plan")).get("proposal_id"),
            ]
        ),
        "canonical_node_ids": _unique_strings(
            [
                source_metadata.get("canonical_node_id"),
                governed_handoff.get("canonical_node_id"),
                _mapping(source_metadata.get("accepted_plan")).get("canonical_node_id"),
            ]
        ),
        "source_snapshot_refs": _unique_strings(
            [
                source_metadata.get("source_snapshot_ref"),
                governed_handoff.get("source_snapshot_ref"),
                source_grounding.get("source_snapshot_ref"),
            ]
        ),
        "support_refs": _unique_strings(
            _string_list(source_metadata.get("source_support_refs"))
            + _string_list(governed_handoff.get("source_support_refs"))
            + _string_list(source_grounding.get("source_support_refs"))
        ),
        "source_asset_ids": _source_asset_ids(source_metadata),
        "selected_passage_hashes": [stable_hash(passage) for passage in selected_passages],
    }


def _promotion_receipt(
    *,
    request: GovernedDraftPromotionRequest,
    source: Mapping[str, Any],
    manifest: Mapping[str, Any],
    source_metadata: Mapping[str, Any],
    project: Mapping[str, Any],
    promotion_id: str,
    target_letter_id: str,
    requested_at: str,
) -> Dict[str, Any]:
    governed_handoff = _mapping(source_metadata.get("governed_handoff"))
    source_grounding = _mapping(source_metadata.get("source_grounding") or governed_handoff.get("source_grounding"))
    selected_passages = _selected_passages(source_metadata)
    receipt = {
        "promotion_id": promotion_id,
        "source_letter_id": request.source_letter_id,
        "target_letter_id": target_letter_id,
        "project_id": request.destination_project_id,
        "destination_project_id": request.destination_project_id,
        "destination_brand_id": request.destination_brand_id,
        "operator_ref": request.operator_ref,
        "operator_note": request.operator_note,
        "promotion_intent_ref": request.promotion_intent_ref,
        "source_body_hash": source_letter_body_hash(str(source.get("text") or "")),
        "source_manifest_hash": stable_hash(manifest),
        "governed_handoff_ids": _governed_handoff_ids(source_metadata),
        "proposal_node_ids": _unique_strings(
            [
                source_metadata.get("proposal_id"),
                governed_handoff.get("proposal_id"),
                _mapping(source_metadata.get("accepted_plan")).get("proposal_id"),
            ]
        ),
        "canonical_node_ids": _unique_strings(
            [
                source_metadata.get("canonical_node_id"),
                governed_handoff.get("canonical_node_id"),
                _mapping(source_metadata.get("accepted_plan")).get("canonical_node_id"),
            ]
        ),
        "source_snapshot_refs": _unique_strings(
            [
                source_metadata.get("source_snapshot_ref"),
                governed_handoff.get("source_snapshot_ref"),
                source_grounding.get("source_snapshot_ref"),
            ]
        ),
        "support_refs": _unique_strings(
            _string_list(source_metadata.get("source_support_refs"))
            + _string_list(governed_handoff.get("source_support_refs"))
            + _string_list(source_grounding.get("source_support_refs"))
        ),
        "source_asset_ids": _source_asset_ids(source_metadata),
        "selected_passage_hashes": [stable_hash(passage) for passage in selected_passages],
        "requested_at": requested_at,
        "validated_at": requested_at,
        "creation_job_id": None,
        "authority": _promotion_authority(),
    }
    if source_metadata.get("governed_drafting_brief_id") or governed_handoff.get("governed_drafting_brief_id"):
        receipt["governed_drafting_brief_id"] = str(
            source_metadata.get("governed_drafting_brief_id")
            or governed_handoff.get("governed_drafting_brief_id")
        )
    if source_metadata.get("source_packet_ref"):
        receipt["source_packet_ref"] = str(source_metadata.get("source_packet_ref"))
    if source_metadata.get("evidence_packet_path"):
        receipt["evidence_packet_path"] = str(source_metadata.get("evidence_packet_path"))
    return receipt


def _initial_target_metadata(
    *,
    request: GovernedDraftPromotionRequest,
    source: Mapping[str, Any],
    source_metadata: Mapping[str, Any],
    project: Mapping[str, Any],
) -> Dict[str, Any]:
    governed_handoff = _mapping(source_metadata.get("governed_handoff"))
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
        "project_id": request.destination_project_id,
        "brand_id": request.destination_brand_id,
        "brand_version": str(project.get("brand_version") or get_brand(request.destination_brand_id).get("version") or "1"),
        "source_asset_ids": _source_asset_ids(source_metadata),
        "selected_source_passages": _selected_passages(source_metadata),
        "release_eligible": False,
        "approval_status": "unapproved",
        "review_status": "unreviewed",
        "publication_state": "not_started",
        "production_derivative_from_governed_draft": True,
        "authority": _promotion_authority(),
    }
    handoff_ids = _governed_handoff_ids(source_metadata)
    if handoff_ids:
        metadata["governed_handoff_id"] = handoff_ids[0]
    if governed_handoff:
        metadata["governed_handoff"] = dict(governed_handoff)
    if source_grounding:
        metadata["source_grounding"] = dict(source_grounding)
    for key in (
        "source_snapshot_ref",
        "source_packet_ref",
        "evidence_packet_path",
        "parent_root_letter_path",
        "campaign_id",
    ):
        if source_metadata.get(key):
            metadata[key] = source_metadata[key]
    return metadata


def _existing_project_promotion(project: Mapping[str, Any], promotion_id: str) -> Dict[str, Any]:
    index = project.get(PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY)
    if index is None:
        return {}
    if not isinstance(index, Mapping):
        raise GovernedDraftPromotionIntegrityError("production_derivative_promotions_index_malformed")
    entry = index.get(promotion_id)
    return dict(entry) if isinstance(entry, Mapping) else {}


def _existing_result(
    request: GovernedDraftPromotionRequest,
    entry: Mapping[str, Any],
) -> GovernedDraftPromotionResult:
    target_letter_id = str(entry.get("target_letter_id") or entry.get("letter_id") or "")
    if not target_letter_id:
        raise GovernedDraftPromotionIntegrityError("existing_promotion_target_letter_id_missing")
    receipt = dict(entry.get("promotion_receipt") or entry)
    return GovernedDraftPromotionResult(
        status="already_promoted",
        promotion_id=str(entry.get("promotion_id") or receipt.get("promotion_id") or ""),
        source_letter_id=request.source_letter_id,
        target_letter_id=target_letter_id,
        job_id=str(entry.get("job_id") or receipt.get("creation_job_id") or "") or None,
        promotion_receipt=receipt,
        project=project_studio.project_payload(request.destination_project_id),
    )


def _raise_on_same_intent_body_conflict(
    project: Mapping[str, Any],
    request: GovernedDraftPromotionRequest,
    source_body_hash: str,
) -> None:
    index = project.get(PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY)
    if not isinstance(index, Mapping):
        return
    for entry in index.values():
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("source_letter_id") or "") != request.source_letter_id:
            continue
        if str(entry.get("promotion_intent_ref") or "") != request.promotion_intent_ref:
            continue
        if str(entry.get("destination_project_id") or entry.get("project_id") or "") != request.destination_project_id:
            continue
        if str(entry.get("destination_brand_id") or "") != request.destination_brand_id:
            continue
        if str(entry.get("source_body_hash") or "") != source_body_hash:
            raise GovernedDraftPromotionConflict("same_source_and_intent_changed_body_hash")


def _raise_on_conflicting_target(target_letter_id: str, promotion_id: str) -> None:
    existing = _read_json(_letter_dir(target_letter_id) / "letter.json")
    if not existing:
        return
    metadata = _mapping(existing.get("metadata"))
    receipt = _mapping(metadata.get(PRODUCTION_DERIVATIVE_PROMOTION_METADATA_KEY))
    if str(receipt.get("promotion_id") or "") != promotion_id:
        raise GovernedDraftPromotionConflict("target_letter_id_already_exists")


def _record_project_promotion(
    project_id: str,
    receipt: Mapping[str, Any],
    *,
    status: str,
    job_id: Optional[str],
    error: Optional[str] = None,
) -> None:
    def mutate(project: Dict[str, Any]) -> None:
        index = project.setdefault(PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY, {})
        if not isinstance(index, dict):
            raise GovernedDraftPromotionIntegrityError("production_derivative_promotions_index_malformed")
        entry = _project_index_entry(receipt, status=status, job_id=job_id, error=error)
        index[str(receipt["promotion_id"])] = entry
        outputs = project.setdefault("letter_outputs", [])
        if not isinstance(outputs, list):
            raise GovernedDraftPromotionIntegrityError("letter_outputs_malformed")
        output = _project_output_entry(receipt, status=status, job_id=job_id)
        for index_number, existing in enumerate(outputs):
            if isinstance(existing, Mapping) and existing.get("promotion_id") == receipt["promotion_id"]:
                outputs[index_number] = {**dict(existing), **output}
                break
        else:
            outputs.append(output)

    project_studio._update_project(project_id, mutate)


def _project_index_entry(
    receipt: Mapping[str, Any],
    *,
    status: str,
    job_id: Optional[str],
    error: Optional[str],
) -> Dict[str, Any]:
    entry = {
        "promotion_id": str(receipt.get("promotion_id") or ""),
        "status": status,
        "source_letter_id": str(receipt.get("source_letter_id") or ""),
        "target_letter_id": str(receipt.get("target_letter_id") or ""),
        "letter_id": str(receipt.get("target_letter_id") or ""),
        "job_id": job_id,
        "project_id": str(receipt.get("project_id") or ""),
        "destination_project_id": str(receipt.get("destination_project_id") or receipt.get("project_id") or ""),
        "destination_brand_id": str(receipt.get("destination_brand_id") or ""),
        "promotion_intent_ref": str(receipt.get("promotion_intent_ref") or ""),
        "source_body_hash": str(receipt.get("source_body_hash") or ""),
        "source_manifest_hash": str(receipt.get("source_manifest_hash") or ""),
        "governed_handoff_ids": list(receipt.get("governed_handoff_ids") or []),
        "proposal_node_ids": list(receipt.get("proposal_node_ids") or []),
        "canonical_node_ids": list(receipt.get("canonical_node_ids") or []),
        "source_snapshot_refs": list(receipt.get("source_snapshot_refs") or []),
        "support_refs": list(receipt.get("support_refs") or []),
        "selected_passage_hashes": list(receipt.get("selected_passage_hashes") or []),
        "requested_at": str(receipt.get("requested_at") or ""),
        "validated_at": str(receipt.get("validated_at") or ""),
        "creation_job_id": job_id,
        "promotion_receipt": dict(receipt),
    }
    if error:
        entry["error"] = error
    return entry


def _project_output_entry(
    receipt: Mapping[str, Any],
    *,
    status: str,
    job_id: Optional[str],
) -> Dict[str, Any]:
    promotion_id = str(receipt.get("promotion_id") or "")
    return {
        "output_id": "letter_output_" + short_hash(("production_derivative", promotion_id)),
        "type": "production_derivative",
        "status": status,
        "job_id": job_id,
        "letter_id": str(receipt.get("target_letter_id") or ""),
        "promotion_id": promotion_id,
        "source_letter_id": str(receipt.get("source_letter_id") or ""),
        "brand_id": str(receipt.get("destination_brand_id") or ""),
        "source_asset_ids": list(receipt.get("source_asset_ids") or []),
        "created_at": str(receipt.get("requested_at") or ""),
    }


def _promotion_entries_for_source(project: Mapping[str, Any], source_letter_id: str) -> List[Dict[str, Any]]:
    index = project.get(PRODUCTION_DERIVATIVE_PROMOTION_INDEX_KEY)
    if index is None:
        return []
    if not isinstance(index, Mapping):
        raise GovernedDraftPromotionIntegrityError("production_derivative_promotions_index_malformed")
    entries: List[Dict[str, Any]] = []
    for entry in index.values():
        if not isinstance(entry, Mapping):
            continue
        receipt = _mapping(entry.get("promotion_receipt"))
        if str(entry.get("source_letter_id") or receipt.get("source_letter_id") or "") != source_letter_id:
            continue
        entries.append(dict(entry))
    return entries


def _latest_promotion_entry(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    def sort_key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
        receipt = _mapping(entry.get("promotion_receipt"))
        return (
            str(entry.get("validated_at") or receipt.get("validated_at") or ""),
            str(entry.get("requested_at") or receipt.get("requested_at") or ""),
            str(entry.get("promotion_id") or receipt.get("promotion_id") or ""),
        )

    return dict(sorted(entries, key=sort_key)[-1])


def _promotion_status_payload(entry: Mapping[str, Any], receipt: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "promotion_id": str(entry.get("promotion_id") or receipt.get("promotion_id") or ""),
        "promotion_intent_ref": str(entry.get("promotion_intent_ref") or receipt.get("promotion_intent_ref") or ""),
        "operator_ref": str(receipt.get("operator_ref") or ""),
        "destination_brand_id": str(entry.get("destination_brand_id") or receipt.get("destination_brand_id") or ""),
        "source_body_hash": str(entry.get("source_body_hash") or receipt.get("source_body_hash") or ""),
        "validated_at": str(entry.get("validated_at") or receipt.get("validated_at") or ""),
        "created_at": str(entry.get("requested_at") or receipt.get("requested_at") or ""),
    }


def _target_status_payload(
    target_letter_id: str,
    target: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    has_release_record: bool,
) -> Dict[str, Any]:
    return {
        "letter_id": target_letter_id,
        "parent_letter_id": str(target.get("parent_letter_id") or metadata.get("parent_letter_id") or ""),
        "lifecycle_state": str(target.get("lifecycle_state") or metadata.get("lifecycle_state") or ""),
        "release_eligible": bool(metadata.get("release_eligible") or target.get("release_eligible") or False),
        "has_release_record": bool(has_release_record),
        "separate_from_source": True,
    }


def _creation_job_status_payload(job_id: str, job: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    payload = {
        "job_id": job_id,
        "status": "",
        "created_at": "",
        "updated_at": "",
    }
    if not job:
        return payload
    payload.update(
        {
            "status": str(job.get("status") or ""),
            "created_at": str(job.get("created_at") or ""),
            "updated_at": str(job.get("updated_at") or ""),
        }
    )
    error_summary = _safe_error_summary(job.get("error"))
    if error_summary:
        payload["error_summary"] = error_summary
    return payload


def _pipeline_status_payload(
    target: Mapping[str, Any],
    metadata: Mapping[str, Any],
    job: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    evaluation = _mapping(target.get("evaluation"))
    lifecycle_state = str(target.get("lifecycle_state") or metadata.get("lifecycle_state") or "")
    job_state = str((job or {}).get("current_stage") or (job or {}).get("status") or "")
    return {
        "state": job_state or lifecycle_state,
        "media_state": _media_state(target),
        "evaluation_state": str(evaluation.get("decision") or metadata.get("evaluation_state") or ""),
        "registration_state": "registered" if lifecycle_state == "registered" else lifecycle_state,
    }


def _media_state(target: Mapping[str, Any]) -> str:
    if target.get("video_path"):
        return "video_available"
    if target.get("visual_path"):
        return "visual_available"
    if target.get("music_path"):
        return "music_available"
    if target.get("audio_path"):
        return "audio_available"
    return ""


def _safe_error_summary(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    first_line = text.splitlines()[0]
    first_line = re.sub(r"[A-Za-z]:\\[^\s]+", "[path]", first_line)
    return first_line[:240]


def _reject_source_release_authority(source_dir: Any, source: Mapping[str, Any], metadata: Mapping[str, Any]) -> None:
    if _read_json(source_dir / "release.json"):
        raise GovernedDraftPromotionValidationError("source_release_json_not_allowed")
    if bool(metadata.get("release_eligible")):
        raise GovernedDraftPromotionValidationError("source_release_eligible_not_allowed")
    for field in ("release_state", "approved", "scheduled_at", "exported_at", "published_at"):
        if source.get(field) or metadata.get(field):
            raise GovernedDraftPromotionValidationError(f"source_release_authority_field_not_allowed:{field}")
    if str(metadata.get("approval_status") or "unapproved") not in {"", "unapproved"}:
        raise GovernedDraftPromotionValidationError("source_approval_status_not_allowed")
    if str(metadata.get("publication_state") or "not_started") not in {"", "not_started"}:
        raise GovernedDraftPromotionValidationError("source_publication_state_not_allowed")
    authority = _mapping(_mapping(metadata.get("governed_handoff")).get("authority"))
    for key in ("approval", "package_readiness", "release_eligibility", "schedule", "export", "publication", "queue", "platform_action", "oauth"):
        if authority.get(key) is True:
            raise GovernedDraftPromotionValidationError(f"source_governed_authority_not_allowed:{key}")


def _promotion_authority() -> Dict[str, bool]:
    return {
        "approval": False,
        "package_readiness": False,
        "release_eligibility": False,
        "schedule": False,
        "export": False,
        "publication": False,
        "queue": False,
        "platform_action": False,
        "oauth": False,
    }


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GovernedDraftPromotionValidationError(f"{label}_required")
    return text


def _require_id(value: str, label: str) -> str:
    text = _required_text(value, label)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise GovernedDraftPromotionValidationError(f"{label}_invalid")
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


def _source_asset_ids(metadata: Mapping[str, Any]) -> List[str]:
    accepted_plan = _mapping(_mapping(metadata.get("source_grounded_drafting")).get("accepted_plan"))
    return _unique_strings(
        _string_list(metadata.get("source_asset_ids"))
        + _string_list(metadata.get("selected_source_asset_ids"))
        + _string_list(accepted_plan.get("selected_source_asset_ids"))
    )


def _selected_passages(metadata: Mapping[str, Any]) -> List[Dict[str, Any]]:
    passages = metadata.get("selected_source_passages")
    if not isinstance(passages, list):
        accepted_plan = _mapping(_mapping(metadata.get("source_grounded_drafting")).get("accepted_plan"))
        passages = accepted_plan.get("selected_passages")
    if not isinstance(passages, list):
        return []
    return [dict(item) for item in passages if isinstance(item, Mapping)]


def _governed_handoff_ids(metadata: Mapping[str, Any]) -> List[str]:
    governed_handoff = _mapping(metadata.get("governed_handoff"))
    accepted_plan = _mapping(_mapping(metadata.get("source_grounded_drafting")).get("accepted_plan"))
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
