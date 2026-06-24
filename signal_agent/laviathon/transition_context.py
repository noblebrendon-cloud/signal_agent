from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.spine_observability.laviathon_store import list_laviathon_observations
from shared.state_registry import get_state


MAX_EVIDENCE_ITEMS = 20
MAX_EVIDENCE_SUMMARY_CHARS = 500
MAX_TEXT_CHARS = 200
ASSOCIATION_EXPLICIT_ENTITY_ID = "explicit_entity_id"
ASSOCIATION_LEGACY_SOURCE_CONTEXT = "legacy_source_context"
ASSOCIATION_EXCLUDED_OTHER_ENTITY = "excluded_other_entity"
ASSOCIATION_CONFLICT = "conflict"
ASSOCIATION_UNASSOCIATED = "unassociated"


@dataclass(frozen=True)
class ObservationAssociation:
    category: str
    observation_id: str
    source_event_id: str
    explicit_entity_id: str = ""
    legacy_matched: bool = False
    reason: str = ""


@dataclass(frozen=True)
class TransitionEvidence:
    evidence_id: str
    summary: str
    source_type: str = "laviathon_observation"
    observed_at: str = ""
    association_method: str = ""
    source_artifact_id: str = ""


@dataclass(frozen=True)
class TransitionGenerationContext:
    entity_id: str
    current_state: str
    evidence: tuple[TransitionEvidence, ...]
    context_timestamp: str
    source_event_ids: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    association_methods: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]


class TransitionContextError(ValueError):
    """Raised when deterministic transition context cannot be derived."""


def build_transition_generation_context(
    entity_id: str,
    *,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    max_evidence_items: int = MAX_EVIDENCE_ITEMS,
    max_summary_chars: int = MAX_EVIDENCE_SUMMARY_CHARS,
) -> TransitionGenerationContext:
    trusted_entity_id = _required_text("entity_id", entity_id, MAX_TEXT_CHARS)
    state_record = _state_record(trusted_entity_id, registry_path=registry_path)
    current_state = _required_text("current_state", _state_value(state_record), MAX_TEXT_CHARS)
    context_timestamp = _required_text(
        "context_timestamp",
        state_record.get("updated_at"),
        MAX_TEXT_CHARS,
    )

    associated = _associated_observations(
        trusted_entity_id,
        state_record=state_record,
        repo_root=repo_root,
    )
    if not associated:
        raise TransitionContextError(f"missing_entity_evidence:{trusted_entity_id}")
    if len(associated) > max_evidence_items:
        omitted = [
            str(row.get("observation_id", ""))
            for row, _association_method in associated[max_evidence_items:]
            if str(row.get("observation_id", ""))
        ]
        raise TransitionContextError(
            f"too_many_evidence_items:{len(associated)}:{','.join(omitted)}"
        )

    evidence: list[TransitionEvidence] = []
    source_event_ids: list[str] = []
    source_observation_ids: list[str] = []
    association_methods: list[str] = []
    source_artifact_ids: list[str] = []
    seen_evidence_ids: set[str] = set()
    for row, association_method in associated:
        observation_id = _required_text("observation_id", row.get("observation_id"), MAX_TEXT_CHARS)
        if observation_id in seen_evidence_ids:
            raise TransitionContextError(f"duplicate_evidence_id:{observation_id}")
        seen_evidence_ids.add(observation_id)
        source_event_id = _required_text("record_hash", row.get("record_hash"), MAX_TEXT_CHARS)
        observed_at = _required_text("observed_at", row.get("created_at"), MAX_TEXT_CHARS)
        source_artifact_id = _optional_text("source_artifact_id", row.get("source_artifact_id"), MAX_TEXT_CHARS) or ""
        evidence.append(
            TransitionEvidence(
                evidence_id=observation_id,
                summary=_bounded_summary(row, max_summary_chars),
                source_type="laviathon_observation",
                observed_at=observed_at,
                association_method=association_method,
                source_artifact_id=source_artifact_id,
            )
        )
        source_event_ids.append(source_event_id)
        source_observation_ids.append(observation_id)
        association_methods.append(association_method)
        source_artifact_ids.append(source_artifact_id)

    return TransitionGenerationContext(
        entity_id=trusted_entity_id,
        current_state=current_state,
        evidence=tuple(evidence),
        context_timestamp=context_timestamp,
        source_event_ids=tuple(source_event_ids),
        source_observation_ids=tuple(source_observation_ids),
        association_methods=tuple(association_methods),
        source_artifact_ids=tuple(source_artifact_ids),
    )


def context_provenance(context: TransitionGenerationContext) -> dict[str, object]:
    return {
        "entity_id": context.entity_id,
        "context_timestamp": context.context_timestamp,
        "source_event_ids": list(context.source_event_ids),
        "source_observation_ids": list(context.source_observation_ids),
        "association_methods": list(context.association_methods),
        "source_artifact_ids": list(context.source_artifact_ids),
    }


def _state_record(entity_id: str, *, registry_path: Path | None) -> dict:
    record = get_state(entity_id, registry_path=registry_path)
    if record is None:
        raise TransitionContextError(f"missing_entity_state:{entity_id}")
    return dict(record)


def _state_value(record: Mapping[str, object]) -> object:
    return record.get("current_state") or record.get("state")


def legacy_association_keys(
    entity_id: str,
    *,
    state_record: Mapping[str, object],
) -> set[str]:
    association_keys = {entity_id}
    for key in ("path", "artifact_path"):
        value = state_record.get(key)
        if isinstance(value, str) and value.strip():
            association_keys.add(value.strip())
    return association_keys


def resolve_observation_association(
    row: Mapping[str, object],
    *,
    entity_id: str,
    legacy_association_keys: set[str],
) -> ObservationAssociation:
    explicit_entity_id = _optional_text("entity_id", row.get("entity_id"), MAX_TEXT_CHARS) or ""
    legacy_matches = row.get("source_context") in legacy_association_keys
    observation_id = str(row.get("observation_id") or "")
    source_event_id = str(row.get("record_hash") or "")

    if explicit_entity_id:
        if explicit_entity_id == entity_id:
            return ObservationAssociation(
                category=ASSOCIATION_EXPLICIT_ENTITY_ID,
                observation_id=observation_id,
                source_event_id=source_event_id,
                explicit_entity_id=explicit_entity_id,
                legacy_matched=legacy_matches,
            )
        if legacy_matches:
            return ObservationAssociation(
                category=ASSOCIATION_CONFLICT,
                observation_id=observation_id,
                source_event_id=source_event_id,
                explicit_entity_id=explicit_entity_id,
                legacy_matched=True,
                reason=f"conflicting_observation_entity:{observation_id}:{explicit_entity_id}:{entity_id}",
            )
        return ObservationAssociation(
            category=ASSOCIATION_EXCLUDED_OTHER_ENTITY,
            observation_id=observation_id,
            source_event_id=source_event_id,
            explicit_entity_id=explicit_entity_id,
            legacy_matched=False,
            reason=f"other_explicit_entity:{explicit_entity_id}",
        )

    if legacy_matches:
        return ObservationAssociation(
            category=ASSOCIATION_LEGACY_SOURCE_CONTEXT,
            observation_id=observation_id,
            source_event_id=source_event_id,
            legacy_matched=True,
        )
    return ObservationAssociation(
        category=ASSOCIATION_UNASSOCIATED,
        observation_id=observation_id,
        source_event_id=source_event_id,
        legacy_matched=False,
    )


def _associated_observations(
    entity_id: str,
    *,
    state_record: Mapping[str, object],
    repo_root: Path | None,
) -> list[tuple[dict, str]]:
    association_keys = legacy_association_keys(entity_id, state_record=state_record)
    rows: list[tuple[dict, str]] = []
    for row in list_laviathon_observations(repo_root=repo_root):
        candidate = dict(row)
        association = resolve_observation_association(
            candidate,
            entity_id=entity_id,
            legacy_association_keys=association_keys,
        )
        if association.category == ASSOCIATION_CONFLICT:
            raise TransitionContextError(association.reason)
        if association.category not in {
            ASSOCIATION_EXPLICIT_ENTITY_ID,
            ASSOCIATION_LEGACY_SOURCE_CONTEXT,
        }:
            continue
        rows.append((candidate, association.category))

    # Observation-store order is append-only, but the prompt context is sorted
    # by stable observation facts to avoid depending on file append timing.
    return sorted(
        rows,
        key=lambda item: (
            str(item[0].get("created_at", "")),
            str(item[0].get("observation_id", "")),
            str(item[0].get("record_hash", "")),
        ),
    )


def _bounded_summary(row: Mapping[str, object], max_chars: int) -> str:
    if max_chars < 32:
        raise TransitionContextError("evidence_summary_bound_too_small")
    parts = (
        ("type", row.get("observation_type")),
        ("claim", row.get("claim")),
        ("evidence", row.get("evidence")),
        ("recommendation", row.get("recommendation")),
        ("review_status", row.get("review_status")),
    )
    summary = " | ".join(
        f"{label}: {_required_text(label, value, 2000)}"
        for label, value in parts
    )
    if len(summary) <= max_chars:
        return summary
    suffix = " [truncated]"
    return summary[: max_chars - len(suffix)].rstrip() + suffix


def _required_text(field: str, value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise TransitionContextError(f"invalid_{field}")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise TransitionContextError(f"missing_{field}")
    if len(normalized) > max_chars:
        raise TransitionContextError(f"{field}_too_long")
    return normalized


def _optional_text(field: str, value: object, max_chars: int) -> str | None:
    if value is None:
        return None
    return _required_text(field, value, max_chars)
