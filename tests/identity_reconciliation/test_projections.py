from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_agent.identity_reconciliation import (
    IdentityDecisionRationale,
    IdentityReviewAuthority,
    build_reconciled_identity_projection,
    record_identity_decision,
    record_projection_status,
)
from signal_agent.identity_reconciliation.errors import (
    IdentityEvidenceError,
    IdentityProjectionError,
)

from .conftest import FIXED_CLOCK, read_json, tree
from .test_decisions import _authority, _candidate, _rationale


def _source_roots(source_runs: dict[str, Path]) -> dict[str, Path]:
    return {
        "linkedin_connections_csv": source_runs["linkedin"],
        "interaction_event_export.v1": source_runs["interaction"],
    }


def test_approval_builds_traceable_projection_and_rejection_or_defer_does_not(
    candidate_run, tmp_path: Path
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    _result, source_runs = candidate_run
    approval = record_identity_decision(
        candidate_path,
        bundle_path,
        tmp_path / "review",
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(source_runs),
    )
    projection = build_reconciled_identity_projection(
        candidate_path,
        bundle_path,
        approval.receipt_path,
        tmp_path / "projections",
        clock=lambda: FIXED_CLOCK,
        source_run_roots=_source_roots(source_runs),
    )
    payload = read_json(projection.projection_path)
    schema = read_json(
        source_runs["repository"]
        / "schemas/identity_reconciliation/reconciled_identity_projection.v1.schema.json"
    )
    Draft202012Validator(schema).validate(payload)
    assert payload["status"] == "active"
    assert payload["source_records_mutated"] is False
    assert len(payload["member_references"]) == 2
    assert payload["approval_decision_receipt"]["decision_id"] == approval.decision_id
    for denied in ("rejected", "deferred"):
        receipt = record_identity_decision(
            candidate_path,
            bundle_path,
            tmp_path / f"review-{denied}",
            _authority(),
            denied,
            _rationale(),
        )
        with pytest.raises(IdentityProjectionError, match="valid_approval_required"):
            build_reconciled_identity_projection(
                candidate_path,
                bundle_path,
                receipt.receipt_path,
                tmp_path / f"projection-{denied}",
                clock=lambda: FIXED_CLOCK,
            )


def test_superseding_rejection_withdraws_without_mutating_projection(
    candidate_run, tmp_path: Path
) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    _result, source_runs = candidate_run
    review_root = tmp_path / "review"
    projection_root = tmp_path / "projections"
    approval = record_identity_decision(
        candidate_path,
        bundle_path,
        review_root,
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(source_runs),
    )
    projection = build_reconciled_identity_projection(
        candidate_path,
        bundle_path,
        approval.receipt_path,
        projection_root,
        clock=lambda: FIXED_CLOCK,
        source_run_roots=_source_roots(source_runs),
    )
    projection_before = projection.projection_path.read_bytes()
    rejection = record_identity_decision(
        candidate_path,
        bundle_path,
        review_root,
        _authority(),
        "rejected",
        _rationale("withdraw_projection"),
        prior_decision_path=approval.receipt_path,
    )
    status = record_projection_status(
        projection.projection_path,
        rejection.receipt_path,
        projection_root,
        clock=lambda: "2026-08-03T16:00:00Z",
    )
    assert status.effective_status == "withdrawn"
    assert projection.projection_path.read_bytes() == projection_before
    status_payload = read_json(status.status_receipt_path)
    assert status_payload["effective_status"] == "withdrawn"
    status_schema = read_json(
        source_runs["repository"]
        / "schemas/identity_reconciliation/projection_status_receipt.v1.schema.json"
    )
    manifest_schema = read_json(
        source_runs["repository"]
        / "schemas/identity_reconciliation/identity_reconciliation_manifest.v1.schema.json"
    )
    Draft202012Validator(status_schema).validate(status_payload)
    Draft202012Validator(manifest_schema).validate(read_json(status.manifest_path))
    Draft202012Validator(manifest_schema).validate(read_json(projection.manifest_path))
    with pytest.raises(IdentityProjectionError, match="decision_superseded"):
        build_reconciled_identity_projection(
            candidate_path,
            bundle_path,
            approval.receipt_path,
            tmp_path / "stale-projection",
            clock=lambda: FIXED_CLOCK,
        )


def test_reapproval_creates_new_revision_in_same_lineage(candidate_run, tmp_path: Path) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    _result, source_runs = candidate_run
    review_root = tmp_path / "review"
    projection_root = tmp_path / "projections"
    approval = record_identity_decision(
        candidate_path,
        bundle_path,
        review_root,
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(source_runs),
    )
    first = build_reconciled_identity_projection(
        candidate_path,
        bundle_path,
        approval.receipt_path,
        projection_root,
        clock=lambda: FIXED_CLOCK,
        source_run_roots=_source_roots(source_runs),
    )
    rejection = record_identity_decision(
        candidate_path,
        bundle_path,
        review_root,
        _authority(),
        "rejected",
        _rationale("withdraw_projection"),
        prior_decision_path=approval.receipt_path,
    )
    record_projection_status(
        first.projection_path,
        rejection.receipt_path,
        projection_root,
        clock=lambda: "2026-08-03T16:00:00Z",
    )
    reapproval = record_identity_decision(
        candidate_path,
        bundle_path,
        review_root,
        _authority(),
        "approved",
        _rationale("reapprove_after_review"),
        prior_decision_path=rejection.receipt_path,
        source_run_roots=_source_roots(source_runs),
    )
    second = build_reconciled_identity_projection(
        candidate_path,
        bundle_path,
        reapproval.receipt_path,
        projection_root,
        prior_projection_path=first.projection_path,
        clock=lambda: "2026-08-03T18:00:00Z",
        source_run_roots=_source_roots(source_runs),
    )
    assert second.projection_lineage_id == first.projection_lineage_id
    assert second.projection_id != first.projection_id
    assert first.projection_path.exists()


def test_source_hash_change_blocks_projection_consumption(candidate_run, tmp_path: Path) -> None:
    candidate_path, bundle_path = _candidate(candidate_run)
    _result, source_runs = candidate_run
    approval = record_identity_decision(
        candidate_path,
        bundle_path,
        tmp_path / "review",
        _authority(),
        "approved",
        _rationale(),
        source_run_roots=_source_roots(source_runs),
    )
    normalized = source_runs["interaction"] / "01_normalized/relationship_records.jsonl"
    normalized.write_bytes(normalized.read_bytes() + b"\n")
    with pytest.raises(IdentityEvidenceError, match="normalized_sha256_mismatch"):
        build_reconciled_identity_projection(
            candidate_path,
            bundle_path,
            approval.receipt_path,
            tmp_path / "projections",
            clock=lambda: FIXED_CLOCK,
            source_run_roots=_source_roots(source_runs),
        )
