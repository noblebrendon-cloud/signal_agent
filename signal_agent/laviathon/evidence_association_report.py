from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.spine_observability.laviathon_store import list_laviathon_observations
from shared.state_registry import get_state

from .transition_context import (
    ASSOCIATION_CONFLICT,
    ASSOCIATION_EXCLUDED_OTHER_ENTITY,
    ASSOCIATION_EXPLICIT_ENTITY_ID,
    ASSOCIATION_LEGACY_SOURCE_CONTEXT,
    ASSOCIATION_UNASSOCIATED,
    MAX_TEXT_CHARS,
    TransitionContextError,
    legacy_association_keys,
    resolve_observation_association,
)


MAX_REPORT_DETAIL_ITEMS = 20
REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ReportDetailTruncation:
    field_name: str
    omitted_count: int


@dataclass(frozen=True)
class EvidenceAssociationReport:
    entity_id: str
    generated_at: str
    current_state: str
    total_observations_examined: int
    explicit_entity_id_count: int
    legacy_source_context_count: int
    excluded_other_entity_count: int
    conflict_count: int
    unassociated_count: int
    evidence_ids_by_method: dict[str, tuple[str, ...]]
    conflict_details: tuple[dict[str, str], ...]
    legacy_observation_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    detail_truncations: tuple[ReportDetailTruncation, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "entity_id": self.entity_id,
            "generated_at": self.generated_at,
            "current_state": self.current_state,
            "total_observations_examined": self.total_observations_examined,
            "explicit_entity_id_count": self.explicit_entity_id_count,
            "legacy_source_context_count": self.legacy_source_context_count,
            "excluded_other_entity_count": self.excluded_other_entity_count,
            "conflict_count": self.conflict_count,
            "unassociated_count": self.unassociated_count,
            "evidence_ids_by_method": {
                method: list(evidence_ids)
                for method, evidence_ids in self.evidence_ids_by_method.items()
            },
            "legacy_observation_ids": list(self.legacy_observation_ids),
            "source_event_ids": list(self.source_event_ids),
            "conflict_details": [
                dict(conflict_detail)
                for conflict_detail in self.conflict_details
            ],
            "detail_truncations": [
                {
                    "field_name": truncation.field_name,
                    "omitted_count": truncation.omitted_count,
                }
                for truncation in self.detail_truncations
            ],
        }


def build_evidence_association_report(
    *,
    entity_id: str,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    generated_at: str | None = None,
    detail_limit: int = MAX_REPORT_DETAIL_ITEMS,
) -> EvidenceAssociationReport:
    trusted_entity_id = _required_text("entity_id", entity_id, MAX_TEXT_CHARS)
    if detail_limit < 0:
        raise TransitionContextError("invalid_detail_limit")

    state_record = _state_record(trusted_entity_id, registry_path=registry_path)
    current_state = _required_text(
        "current_state",
        state_record.get("current_state") or state_record.get("state"),
        MAX_TEXT_CHARS,
    )
    association_keys = legacy_association_keys(
        trusted_entity_id,
        state_record=state_record,
    )

    raw_ids_by_method: dict[str, list[str]] = {
        ASSOCIATION_EXPLICIT_ENTITY_ID: [],
        ASSOCIATION_LEGACY_SOURCE_CONTEXT: [],
        ASSOCIATION_EXCLUDED_OTHER_ENTITY: [],
        ASSOCIATION_CONFLICT: [],
        ASSOCIATION_UNASSOCIATED: [],
    }
    conflict_details: list[dict[str, str]] = []
    legacy_observation_ids: list[str] = []
    source_event_ids: list[str] = []
    counts = {key: 0 for key in raw_ids_by_method}

    observations = sorted(
        (dict(row) for row in list_laviathon_observations(repo_root=repo_root)),
        key=lambda row: (
            str(row.get("created_at", "")),
            str(row.get("observation_id", "")),
            str(row.get("record_hash", "")),
        ),
    )
    for row in observations:
        association = resolve_observation_association(
            row,
            entity_id=trusted_entity_id,
            legacy_association_keys=association_keys,
        )
        counts[association.category] += 1
        if association.observation_id:
            raw_ids_by_method[association.category].append(association.observation_id)

        if association.category == ASSOCIATION_LEGACY_SOURCE_CONTEXT:
            legacy_observation_ids.append(association.observation_id)
        if association.category in {
            ASSOCIATION_EXPLICIT_ENTITY_ID,
            ASSOCIATION_LEGACY_SOURCE_CONTEXT,
        }:
            source_event_ids.append(association.source_event_id)
        if association.category == ASSOCIATION_CONFLICT:
            conflict_details.append(
                {
                    "observation_id": association.observation_id,
                    "source_event_id": association.source_event_id,
                    "explicit_entity_id": association.explicit_entity_id,
                    "requested_entity_id": trusted_entity_id,
                    "reason": association.reason,
                }
            )

    truncations: list[ReportDetailTruncation] = []
    evidence_ids_by_method = {
        method: _bounded_tuple(
            ids,
            field_name=f"evidence_ids_by_method.{method}",
            detail_limit=detail_limit,
            truncations=truncations,
        )
        for method, ids in raw_ids_by_method.items()
    }

    return EvidenceAssociationReport(
        entity_id=trusted_entity_id,
        generated_at=generated_at or _utc_timestamp(),
        current_state=current_state,
        total_observations_examined=len(observations),
        explicit_entity_id_count=counts[ASSOCIATION_EXPLICIT_ENTITY_ID],
        legacy_source_context_count=counts[ASSOCIATION_LEGACY_SOURCE_CONTEXT],
        excluded_other_entity_count=counts[ASSOCIATION_EXCLUDED_OTHER_ENTITY],
        conflict_count=counts[ASSOCIATION_CONFLICT],
        unassociated_count=counts[ASSOCIATION_UNASSOCIATED],
        evidence_ids_by_method=evidence_ids_by_method,
        conflict_details=_bounded_tuple(
            conflict_details,
            field_name="conflict_details",
            detail_limit=detail_limit,
            truncations=truncations,
        ),
        legacy_observation_ids=_bounded_tuple(
            legacy_observation_ids,
            field_name="legacy_observation_ids",
            detail_limit=detail_limit,
            truncations=truncations,
        ),
        source_event_ids=_bounded_tuple(
            source_event_ids,
            field_name="source_event_ids",
            detail_limit=detail_limit,
            truncations=truncations,
        ),
        detail_truncations=tuple(truncations),
    )


def _state_record(entity_id: str, *, registry_path: Path | None) -> dict:
    record = get_state(entity_id, registry_path=registry_path)
    if record is None:
        raise TransitionContextError(f"missing_entity_state:{entity_id}")
    return dict(record)


def _bounded_tuple(
    values: list,
    *,
    field_name: str,
    detail_limit: int,
    truncations: list[ReportDetailTruncation],
) -> tuple:
    if len(values) > detail_limit:
        truncations.append(
            ReportDetailTruncation(
                field_name=field_name,
                omitted_count=len(values) - detail_limit,
            )
        )
    return tuple(values[:detail_limit])


def _required_text(field: str, value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise TransitionContextError(f"invalid_{field}")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise TransitionContextError(f"missing_{field}")
    if len(normalized) > max_chars:
        raise TransitionContextError(f"{field}_too_long")
    return normalized


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
