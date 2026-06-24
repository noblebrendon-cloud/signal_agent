from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention.jsonl_store import compute_record_hash
from app.spine_observability.laviathon import normalize_observation
from app.spine_observability.laviathon_store import LAVIATHON_OBSERVATIONS_FILE
from app.spine_observability.laviathon_store import append_laviathon_observation
from signal_agent.laviathon.transition_context import (
    TransitionContextError,
    build_transition_generation_context,
)


def _registry_path(root: Path) -> Path:
    return root / "data" / "state" / "artifact_registry.jsonl"


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
    source_artifact_id: str | None = None,
    source_context: str = "entity.alpha",
    created_at: str = "2026-06-23T00:00:00Z",
    claim: str = "Alpha entity has a bounded observation.",
    evidence: str = "The stored Laviathon observation explicitly references Alpha.",
    recommendation: str = "Use this observation as proposal evidence only.",
) -> dict:
    payload = {
        "created_at": created_at,
        "source_context": source_context,
        "spine_target": "governance",
        "observation_type": "critique",
        "claim": claim,
        "evidence": evidence,
        "recommendation": recommendation,
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


def _observation_path(root: Path) -> Path:
    return root / "data" / "state" / LAVIATHON_OBSERVATIONS_FILE


def _append_legacy_observation(root: Path, observation: dict) -> dict:
    normalized = normalize_observation(observation)
    rows = []
    path = _observation_path(root)
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


def test_context_derives_current_state_from_state_registry_projection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root, state="captured", updated_at="2026-06-23T00:00:00Z")
    _append_state(root, state="classified", updated_at="2026-06-23T00:01:00Z")
    stored = append_laviathon_observation(_observation(), repo_root=root)

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert context.current_state == "classified"
    assert context.context_timestamp == "2026-06-23T00:01:00Z"
    assert context.source_observation_ids == (stored["observation_id"],)
    assert context.association_methods == ("explicit_entity_id",)


def test_context_derives_only_associated_observations(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root, path="entities/entity.alpha.md")
    direct = append_laviathon_observation(_observation(source_context="entity.alpha"), repo_root=root)
    by_path = append_laviathon_observation(
        _observation(
            source_context="entities/entity.alpha.md",
            claim="Alpha path reference has a bounded observation.",
        ),
        repo_root=root,
    )
    unrelated = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.beta",
            claim="Beta entity has unrelated evidence.",
        ),
        repo_root=root,
    )

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert set(context.source_observation_ids) == {
        direct["observation_id"],
        by_path["observation_id"],
    }
    assert unrelated["observation_id"] not in context.source_observation_ids
    assert context.association_methods == ("explicit_entity_id", "explicit_entity_id")


def test_context_evidence_ids_and_ordering_are_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    later = append_laviathon_observation(
        _observation(
            created_at="2026-06-23T00:02:00Z",
            claim="Later Alpha observation.",
        ),
        repo_root=root,
    )
    earlier = append_laviathon_observation(
        _observation(
            created_at="2026-06-23T00:01:00Z",
            claim="Earlier Alpha observation.",
        ),
        repo_root=root,
    )

    first = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )
    second = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert first.source_observation_ids == (
        earlier["observation_id"],
        later["observation_id"],
    )
    assert second.source_observation_ids == first.source_observation_ids
    assert tuple(item.evidence_id for item in first.evidence) == first.source_observation_ids
    assert all(item.source_type == "laviathon_observation" for item in first.evidence)
    assert all(item.observed_at for item in first.evidence)
    assert all(item.association_method == "explicit_entity_id" for item in first.evidence)


def test_context_missing_entity_or_evidence_fails_explicitly(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    append_laviathon_observation(_observation(), repo_root=root)

    with pytest.raises(TransitionContextError, match="missing_entity_state:entity.alpha"):
        build_transition_generation_context(
            "entity.alpha",
            repo_root=root,
            registry_path=_registry_path(root),
        )

    root_with_state = tmp_path / "repo-with-state"
    _append_state(root_with_state)
    with pytest.raises(TransitionContextError, match="missing_entity_evidence:entity.alpha"):
        build_transition_generation_context(
            "entity.alpha",
            repo_root=root_with_state,
            registry_path=_registry_path(root_with_state),
        )


def test_legacy_observation_without_entity_id_uses_compatibility_association(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    legacy = _append_legacy_observation(root, _observation(entity_id=None))

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert context.source_observation_ids == (legacy["observation_id"],)
    assert context.association_methods == ("legacy_source_context",)
    assert context.evidence[0].association_method == "legacy_source_context"


def test_explicit_entity_id_excludes_unrelated_observations(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    included = append_laviathon_observation(_observation(), repo_root=root)
    excluded = append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="unrelated_human_context",
            claim="Beta explicit identity must not be used for Alpha.",
        ),
        repo_root=root,
    )

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert context.source_observation_ids == (included["observation_id"],)
    assert excluded["observation_id"] not in context.source_observation_ids


def test_explicit_and_legacy_association_conflict_fails(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    append_laviathon_observation(
        _observation(
            entity_id="entity.beta",
            source_context="entity.alpha",
            claim="Conflicting explicit and legacy identity should fail.",
        ),
        repo_root=root,
    )

    with pytest.raises(TransitionContextError, match="conflicting_observation_entity"):
        build_transition_generation_context(
            "entity.alpha",
            repo_root=root,
            registry_path=_registry_path(root),
        )


def test_context_preserves_source_artifact_id_when_supplied(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    append_laviathon_observation(
        _observation(source_artifact_id="artifact.alpha"),
        repo_root=root,
    )

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
    )

    assert context.source_artifact_ids == ("artifact.alpha",)
    assert context.evidence[0].source_artifact_id == "artifact.alpha"


def test_context_evidence_bounds_fail_closed_without_silent_loss(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    append_laviathon_observation(_observation(claim="First Alpha observation."), repo_root=root)
    omitted = append_laviathon_observation(_observation(claim="Second Alpha observation."), repo_root=root)

    with pytest.raises(TransitionContextError) as excinfo:
        build_transition_generation_context(
            "entity.alpha",
            repo_root=root,
            registry_path=_registry_path(root),
            max_evidence_items=1,
        )

    assert "too_many_evidence_items:2" in str(excinfo.value)
    assert omitted["observation_id"] in str(excinfo.value)


def test_context_evidence_summaries_are_bounded_with_marker(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _append_state(root)
    append_laviathon_observation(
        _observation(
            claim="Alpha has a long observation.",
            evidence=" ".join(["evidence"] * 80),
            recommendation="Keep the context prompt bounded.",
        ),
        repo_root=root,
    )

    context = build_transition_generation_context(
        "entity.alpha",
        repo_root=root,
        registry_path=_registry_path(root),
        max_summary_chars=80,
    )

    assert len(context.evidence[0].summary) <= 80
    assert context.evidence[0].summary.endswith("[truncated]")
