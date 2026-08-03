from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_agent.identity_reconciliation import (
    IdentityDecisionRationale,
    IdentityReviewAuthority,
    record_identity_decision,
)
from signal_agent.identity_reconciliation.errors import (
    IdentityArtifactCollisionError,
    IdentityDecisionError,
)

from .conftest import read_json


def _candidate(candidate_run, status: str = "proposed") -> tuple[Path, Path]:
    result, _source_runs = candidate_run
    for candidate_path in result.candidate_paths:
        candidate = read_json(candidate_path)
        if candidate["status"] == status:
            bundle_path = result.run_root / candidate["evidence_bundle"]["path"]
            return candidate_path, bundle_path
    raise AssertionError(f"candidate status not found: {status}")


def _authority() -> IdentityReviewAuthority:
    return IdentityReviewAuthority(
        authority_type="human_attestation",
        reviewer_id="reviewer-fixture-001",
        reviewer_role="identity_reconciliation_reviewer",
        authority_basis="Milestone 3 fixture review",
        attested_at="2026-08-03T14:00:00Z",
        attestation_version="identity_review_authority_attestation.v1",
    )


def _rationale(code: str = "fixture_review_complete") -> IdentityDecisionRationale:
    return IdentityDecisionRationale(
        reason_code=code,
        summary="Human reviewer evaluated the exact referenced evidence.",
    )


def _source_roots(candidate_run) -> dict[str, Path]:
    _result, source_runs = candidate_run
    return {
        "linkedin_connections_csv": source_runs["linkedin"],
        "interaction_event_export.v1": source_runs["interaction"],
    }


@pytest.mark.parametrize("decision", ["approved", "rejected", "deferred"])
def test_valid_human_decisions_create_immutable_receipts(
    candidate_run, tmp_path: Path, decision: str
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    result = record_identity_decision(
        candidate_path,
        bundle_path,
        tmp_path / decision,
        _authority(),
        decision,
        _rationale(),
        source_run_roots=_source_roots(candidate_run) if decision == "approved" else None,
    )
    receipt = read_json(result.receipt_path)
    schema = read_json(
        Path(__file__).resolve().parents[2]
        / "schemas/identity_reconciliation/identity_decision_receipt.v1.schema.json"
    )
    Draft202012Validator(schema).validate(receipt)
    assert receipt["projection_authorized"] is (decision == "approved")
    assert receipt["authority_limitations"]["reviewer_authenticated"] is False
    assert receipt["transition"] == {"origin": "proposed", "destination": decision}
    assert result.idempotent_replay is False


def test_conflicting_candidate_cannot_be_approved(candidate_run, tmp_path: Path) -> None:
    candidate_path, bundle_path = _candidate(candidate_run, "conflicting")
    with pytest.raises(IdentityDecisionError, match="approval_prohibited"):
        record_identity_decision(
            candidate_path,
            bundle_path,
            tmp_path,
            _authority(),
            "approved",
            _rationale(),
        )
    for allowed in ("rejected", "deferred"):
        result = record_identity_decision(
            candidate_path,
            bundle_path,
            tmp_path / allowed,
            _authority(),
            allowed,
            _rationale(),
        )
        assert result.decision == allowed


def test_nonconflicting_approval_requires_live_source_revalidation(
    candidate_run, tmp_path: Path
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    with pytest.raises(IdentityDecisionError, match="source_revalidation_required"):
        record_identity_decision(
            candidate_path,
            bundle_path,
            tmp_path,
            _authority(),
            "approved",
            _rationale(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("authority_type", "automation", "type_unsupported"),
        ("reviewer_id", "", "reviewer_id_required"),
        ("reviewer_role", "general_reviewer", "role_unsupported"),
        ("authority_basis", " ", "authority_basis_required"),
        ("attested_at", "2026-08-03T14:00:00", "offset_required"),
        ("attestation_version", "v2", "version_unsupported"),
    ],
)
def test_invalid_authority_fails_closed(
    candidate_run,
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    with pytest.raises(IdentityDecisionError, match=message):
        record_identity_decision(
            candidate_path,
            bundle_path,
            tmp_path,
            replace(_authority(), **{field: value}),
            "approved",
            _rationale(),
        )


def test_replay_is_idempotent_and_successor_slot_rejects_concurrent_fork(
    candidate_run, tmp_path: Path
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    root = tmp_path / "review"
    first = record_identity_decision(
        candidate_path,
        bundle_path,
        root,
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(candidate_run),
    )
    replay = record_identity_decision(
        candidate_path,
        bundle_path,
        root,
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(candidate_run),
    )
    assert replay.receipt_path == first.receipt_path
    assert replay.idempotent_replay is True
    with pytest.raises(IdentityArtifactCollisionError, match="successor_slot_occupied"):
        record_identity_decision(
            candidate_path,
            bundle_path,
            root,
            _authority(),
            "rejected",
            _rationale("different_root_successor"),
        )


def test_superseding_transition_preserves_history_and_rejects_same_state_spam(
    candidate_run, tmp_path: Path
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    root = tmp_path / "review"
    approval = record_identity_decision(
        candidate_path,
        bundle_path,
        root,
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(candidate_run),
    )
    rejection = record_identity_decision(
        candidate_path,
        bundle_path,
        root,
        _authority(),
        "rejected",
        _rationale("evidence_reconsidered"),
        prior_decision_path=approval.receipt_path,
    )
    assert approval.receipt_path.exists()
    assert rejection.receipt["prior_decision_receipt"] == {
        "decision_id": approval.decision_id,
        "receipt_hash": approval.receipt["receipt_hash"],
    }
    with pytest.raises(IdentityDecisionError, match="transition_invalid"):
        record_identity_decision(
            candidate_path,
            bundle_path,
            root,
            _authority(),
            "rejected",
            _rationale(),
            prior_decision_path=rejection.receipt_path,
        )
