from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app.retention.jsonl_store import compute_record_hash
from app.spine_observability.laviathon import normalize_observation
from app.spine_observability.laviathon_store import (
    LAVIATHON_OBSERVATIONS_FILE,
    append_laviathon_observation,
)
from signal_agent.laviathon.evidence_association_report import (
    build_evidence_association_report,
)
from signal_agent.laviathon.transition_context import (
    TransitionContextError,
    build_transition_generation_context,
)


def _registry_path(root: Path) -> Path:
    return root / "data" / "state" / "artifact_registry.jsonl"


def _observation_path(root: Path) -> Path:
    return root / "data" / "state" / LAVIATHON_OBSERVATIONS_FILE


def _append_state(
    root: Path,
    *,
    entity_id: str = "entity.alpha",
    state: str = "captured",
    path: str = "entities/entity.alpha.md",
    updated_at: str = "2026-06-23T00:00:00Z",
) -> None:
    registry = _registry_path(root)
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open(registry, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "artifact_id": entity_id,
                    "state": state,
                    "path": path,
                    "updated_at": updated_at,
                },
                sort_keys=True,
            )
            + "\n"
        )


def _observation(
    *,
    entity_id: str | None = "entity.alpha",
    source_context: str = "entity.alpha",
    source_artifact_id: str | None = None,
    created_at: str = "2026-06-23T00:00:00Z",
    claim: str = "Alpha entity has a bounded observation.",
) -> dict:
    payload = {
        "created_at": created_at,
        "source_context": source_context,
        "spine_target": "governance",
        "observation_type": "critique",
        "claim": claim,
        "evidence": "The stored observation is available for association reporting.",
        "recommendation": "Use this observation as report evidence only.",
        "public_safe": False,
        "requires_human_review": True,
        "review_status": "pending",
        "external_action_allowed": False,
    }
    if entity_id is not None:
        payload["entity_id"] = entity_id
    if source_artifact_id is not None:
        payload["source_artifact_id"] = source_artifact_id
    return payload


def _append_legacy_observation(root: Path, observation: dict) -> dict:
    normalized = normalize_observation(observation)
    path = _observation_path(root)
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        **normalized,
        "recorded_at": normalized["created_at"],
        "prev_hash": rows[-1]["record_hash"] if rows else None,
    }
    payload["record_hash"] = compute_record_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def test_report_counts_explicit_legacy_excluded_conflict_and_unassociated(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    explicit = append_laviathon_observation(_observation(), repo_root=root)
    legacy = _append_legacy_observation(
        root,
        _observation(entity_id=None, claim="Legacy Alpha observation."),
    )
    excluded = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.beta",
            claim="Beta explicit identity is not Alpha evidence.",
        ),
        repo_root=root,
    )
    conflict = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.alpha",
            claim="Conflicting explicit and legacy identity.",
        ),
        repo_root=root,
    )
    unassociated = _append_legacy_observation(
        root,
        _observation(
            entity_id=None,
            source_context="unrelated_context",
            claim="No usable Alpha association.",
        ),
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
    )

    assert report.total_observations_examined == 5
    assert report.explicit_entity_id_count == 1
    assert report.legacy_source_context_count == 1
    assert report.excluded_other_entity_count == 1
    assert report.conflict_count == 1
    assert report.unassociated_count == 1
    assert report.evidence_ids_by_method["explicit_entity_id"] == (explicit["observation_id"],)
    assert report.legacy_observation_ids == (legacy["observation_id"],)
    assert report.evidence_ids_by_method["excluded_other_entity"] == (excluded["observation_id"],)
    assert report.evidence_ids_by_method["conflict"] == (conflict["observation_id"],)
    assert report.evidence_ids_by_method["unassociated"] == (unassociated["observation_id"],)
    assert report.conflict_details[0]["explicit_entity_id"] == "entity.beta"


def test_report_to_dict_is_json_safe_and_preserves_contract(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    explicit = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:00:00Z"),
        repo_root=root,
    )
    legacy = _append_legacy_observation(
        root,
        _observation(
            entity_id=None,
            created_at="2026-06-23T00:01:00Z",
            claim="Legacy Alpha observation.",
        ),
    )
    excluded = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.beta",
            created_at="2026-06-23T00:02:00Z",
            claim="Beta explicit identity is not Alpha evidence.",
        ),
        repo_root=root,
    )
    conflict = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.alpha",
            created_at="2026-06-23T00:03:00Z",
            claim="Conflicting explicit and legacy identity.",
        ),
        repo_root=root,
    )
    unassociated = _append_legacy_observation(
        root,
        _observation(
            entity_id=None,
            source_context="unrelated_context",
            created_at="2026-06-23T00:04:00Z",
            claim="No usable Alpha association.",
        ),
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
    )

    serialized = report.to_dict()
    assert json.loads(json.dumps(serialized, sort_keys=True)) == serialized
    assert serialized["report_schema_version"] == "1.0"
    assert serialized["entity_id"] == "entity.alpha"
    assert serialized["generated_at"] == "2026-06-23T00:05:00Z"
    assert serialized["current_state"] == "captured"
    assert serialized["total_observations_examined"] == 5
    assert serialized["explicit_entity_id_count"] == 1
    assert serialized["legacy_source_context_count"] == 1
    assert serialized["excluded_other_entity_count"] == 1
    assert serialized["conflict_count"] == 1
    assert serialized["unassociated_count"] == 1
    assert serialized["evidence_ids_by_method"] == {
        "explicit_entity_id": [explicit["observation_id"]],
        "legacy_source_context": [legacy["observation_id"]],
        "excluded_other_entity": [excluded["observation_id"]],
        "conflict": [conflict["observation_id"]],
        "unassociated": [unassociated["observation_id"]],
    }
    assert serialized["legacy_observation_ids"] == [legacy["observation_id"]]
    assert serialized["source_event_ids"] == [
        explicit["record_hash"],
        legacy["record_hash"],
    ]
    assert serialized["conflict_details"] == [
        {
            "observation_id": conflict["observation_id"],
            "source_event_id": conflict["record_hash"],
            "explicit_entity_id": "entity.beta",
            "requested_entity_id": "entity.alpha",
            "reason": (
                "conflicting_observation_entity:"
                f"{conflict['observation_id']}:entity.beta:entity.alpha"
            ),
        }
    ]
    assert isinstance(serialized["conflict_details"][0], dict)


def test_report_matches_transition_context_for_accepted_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    explicit = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:02:00Z", claim="Later explicit."),
        repo_root=root,
    )
    legacy = _append_legacy_observation(
        root,
        _observation(entity_id=None, created_at="2026-06-23T00:01:00Z", claim="Earlier legacy."),
    )
    append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.beta",
            claim="Excluded Beta.",
        ),
        repo_root=root,
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
    )
    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    report_accepted = (
        report.evidence_ids_by_method["legacy_source_context"]
        + report.evidence_ids_by_method["explicit_entity_id"]
    )
    assert set(report_accepted) == {explicit["observation_id"], legacy["observation_id"]}
    assert set(context.source_observation_ids) == set(report_accepted)
    assert set(context.association_methods) == {"explicit_entity_id", "legacy_source_context"}


def test_report_output_ordering_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    later = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:02:00Z", claim="Later explicit."),
        repo_root=root,
    )
    earlier = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:01:00Z", claim="Earlier explicit."),
        repo_root=root,
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
    )

    assert report.evidence_ids_by_method["explicit_entity_id"] == (
        earlier["observation_id"],
        later["observation_id"],
    )


def test_report_detail_bounds_include_truncation_metadata(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    first = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:00:00Z", claim="First explicit."),
        repo_root=root,
    )
    append_laviathon_observation(
        _observation(created_at="2026-06-23T00:01:00Z", claim="Second explicit."),
        repo_root=root,
    )
    append_laviathon_observation(
        _observation(created_at="2026-06-23T00:02:00Z", claim="Third explicit."),
        repo_root=root,
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
        detail_limit=1,
    )

    assert report.explicit_entity_id_count == 3
    assert report.evidence_ids_by_method["explicit_entity_id"] == (first["observation_id"],)
    assert any(
        item.field_name == "evidence_ids_by_method.explicit_entity_id"
        and item.omitted_count == 2
        for item in report.detail_truncations
    )
    assert any(
        item.field_name == "source_event_ids" and item.omitted_count == 2
        for item in report.detail_truncations
    )


def test_report_to_dict_serializes_truncations_and_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    first_observation = append_laviathon_observation(
        _observation(created_at="2026-06-23T00:00:00Z", claim="First explicit."),
        repo_root=root,
    )
    append_laviathon_observation(
        _observation(created_at="2026-06-23T00:01:00Z", claim="Second explicit."),
        repo_root=root,
    )
    append_laviathon_observation(
        _observation(created_at="2026-06-23T00:02:00Z", claim="Third explicit."),
        repo_root=root,
    )

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        generated_at="2026-06-23T00:05:00Z",
        detail_limit=1,
    )

    first = report.to_dict()
    second = report.to_dict()

    assert first == second
    assert first["evidence_ids_by_method"]["explicit_entity_id"] == [
        first_observation["observation_id"],
    ]
    assert first["detail_truncations"] == [
        {
            "field_name": "evidence_ids_by_method.explicit_entity_id",
            "omitted_count": 2,
        },
        {
            "field_name": "source_event_ids",
            "omitted_count": 2,
        },
    ]
    for truncation in first["detail_truncations"]:
        assert isinstance(truncation, dict)
        assert set(truncation) == {"field_name", "omitted_count"}


def test_report_missing_entity_fails_explicitly(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    append_laviathon_observation(_observation(), repo_root=root)

    with pytest.raises(TransitionContextError, match="missing_entity_state:entity.alpha"):
        build_evidence_association_report(
            entity_id="entity.alpha",
            repo_root=root,
            registry_path=_registry_path(root),
            generated_at="2026-06-23T00:05:00Z",
        )


def test_report_is_read_only_and_makes_no_network_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    root = tmp_path / "repo"
    _append_state(root)
    append_laviathon_observation(_observation(), repo_root=root)
    observation_path = _observation_path(root)
    registry_path = _registry_path(root)
    proposal_ledger_path = root / "data" / "state" / "governed_transition_ledger.jsonl"
    observation_before = observation_path.read_text(encoding="utf-8")
    registry_before = registry_path.read_text(encoding="utf-8")

    report = build_evidence_association_report(
        entity_id="entity.alpha",
        repo_root=root,
        registry_path=registry_path,
        generated_at="2026-06-23T00:05:00Z",
    )
    observation_after_build = observation_path.read_text(encoding="utf-8")
    registry_after_build = registry_path.read_text(encoding="utf-8")

    serialized = report.to_dict()
    repeated_serialized = report.to_dict()

    assert report.explicit_entity_id_count == 1
    assert json.dumps(serialized, sort_keys=True)
    assert repeated_serialized == serialized
    assert observation_after_build == observation_before
    assert registry_after_build == registry_before
    assert observation_path.read_text(encoding="utf-8") == observation_after_build
    assert registry_path.read_text(encoding="utf-8") == registry_after_build
    assert not proposal_ledger_path.exists()
