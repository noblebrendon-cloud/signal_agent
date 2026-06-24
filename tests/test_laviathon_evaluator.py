from __future__ import annotations

from pathlib import Path

import pytest

from app.spine_observability.laviathon import (
    ALLOWED_OBSERVATION_TYPES,
    ALLOWED_REVIEW_STATUSES,
    ALLOWED_SPINE_TARGETS,
    LAVIATHON_IDENTITY,
    normalize_observation,
)


def _base_observation() -> dict:
    return {
        "entity_id": "entity.alpha",
        "created_at": "2026-05-14T12:00:00Z",
        "source_context": "stage_1_spine_summary_review",
        "spine_target": "governance",
        "observation_type": "critique",
        "claim": "The summary is useful but still manual-only.",
        "evidence": "The current module accepts operator-entered snapshots only.",
        "recommendation": "Keep the next patch limited to local observation validation.",
        "public_safe": False,
        "requires_human_review": True,
        "review_status": "pending",
        "external_action_allowed": False,
    }


def test_valid_observation_normalizes_successfully() -> None:
    normalized = normalize_observation(_base_observation())

    assert normalized["schema_version"] == "1.0"
    assert normalized["observation_id"].startswith("lob_")
    assert normalized["created_at"] == "2026-05-14T12:00:00Z"
    assert normalized["entity_id"] == "entity.alpha"
    assert normalized["spine_target"] == "governance"
    assert normalized["observation_type"] == "critique"
    assert normalized["public_safe"] is False
    assert normalized["requires_human_review"] is True
    assert normalized["review_status"] == "pending"
    assert normalized["external_action_allowed"] is False
    assert LAVIATHON_IDENTITY["not_human"] is True
    assert LAVIATHON_IDENTITY["autonomous"] is False


def test_legacy_observation_without_entity_id_still_normalizes_for_reads() -> None:
    record = _base_observation()
    del record["entity_id"]

    normalized = normalize_observation(record)

    assert "entity_id" not in normalized
    assert normalized["observation_id"].startswith("lob_")


def test_new_observation_requires_entity_id_when_requested() -> None:
    record = _base_observation()
    del record["entity_id"]

    with pytest.raises(ValueError, match="missing_entity_id"):
        normalize_observation(record, require_entity_id=True)


def test_source_artifact_id_is_preserved_when_supplied() -> None:
    record = _base_observation()
    record["source_artifact_id"] = "artifact.alpha"

    normalized = normalize_observation(record, require_entity_id=True)

    assert normalized["entity_id"] == "entity.alpha"
    assert normalized["source_artifact_id"] == "artifact.alpha"


def test_missing_required_field_fails() -> None:
    record = _base_observation()
    del record["claim"]

    with pytest.raises(ValueError, match="missing_required_fields:claim"):
        normalize_observation(record)


def test_invalid_spine_target_fails() -> None:
    record = _base_observation()
    record["spine_target"] = "external_platform"

    with pytest.raises(ValueError, match="invalid_spine_target:external_platform"):
        normalize_observation(record)


def test_invalid_observation_type_fails() -> None:
    record = _base_observation()
    record["observation_type"] = "autonomous_action"

    with pytest.raises(ValueError, match="invalid_observation_type:autonomous_action"):
        normalize_observation(record)


def test_invalid_review_status_fails() -> None:
    record = _base_observation()
    record["review_status"] = "published"

    with pytest.raises(ValueError, match="invalid_review_status:published"):
        normalize_observation(record)


def test_external_action_allowed_true_fails() -> None:
    record = _base_observation()
    record["external_action_allowed"] = True

    with pytest.raises(ValueError, match="external_action_not_allowed"):
        normalize_observation(record)


def test_public_post_candidate_requires_human_review() -> None:
    record = _base_observation()
    record["observation_type"] = "public_post_candidate"
    record["requires_human_review"] = False

    with pytest.raises(ValueError, match="public_candidate_requires_human_review"):
        normalize_observation(record)

    record["requires_human_review"] = True
    normalized = normalize_observation(record)
    assert normalized["requires_human_review"] is True
    assert normalized["review_status"] == "pending"


def test_omitted_review_status_defaults_to_pending() -> None:
    record = _base_observation()
    del record["review_status"]

    normalized = normalize_observation(record)

    assert normalized["review_status"] == "pending"


def test_omitted_requires_human_review_defaults_to_true() -> None:
    record = _base_observation()
    del record["requires_human_review"]

    normalized = normalize_observation(record)

    assert normalized["requires_human_review"] is True


def test_deterministic_observation_id_for_same_stable_input() -> None:
    first = normalize_observation(_base_observation())
    second = normalize_observation(_base_observation())
    later = _base_observation()
    later["created_at"] = "2026-05-15T12:00:00Z"
    third = normalize_observation(later)

    assert first["observation_id"] == second["observation_id"]
    assert first["observation_id"] == third["observation_id"]


def test_laviathon_cannot_represent_itself_as_human() -> None:
    record = _base_observation()
    record["actor_type"] = "human"

    with pytest.raises(ValueError, match="laviathon_not_human"):
        normalize_observation(record)


def test_source_scan_has_no_network_or_external_action_primitives() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "spine_observability" / "laviathon.py").read_text(
        encoding="utf-8"
    )

    forbidden_tokens = (
        "requests",
        "urllib",
        "http.client",
        "socket",
        ".post(",
        "send_message",
        "smtp",
        "scrape",
        "schedule",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_allowed_values_are_narrow() -> None:
    assert ALLOWED_SPINE_TARGETS == (
        "reflective",
        "governance",
        "retention",
        "dashboard",
        "unknown",
    )
    assert ALLOWED_OBSERVATION_TYPES == (
        "critique",
        "risk",
        "opportunity",
        "coherence_check",
        "public_post_candidate",
    )
    assert ALLOWED_REVIEW_STATUSES == ("pending", "approved", "rejected")
