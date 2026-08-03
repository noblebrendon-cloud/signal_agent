from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from signal_agent.identity_reconciliation import (
    IdentityDecisionRationale,
    build_reconciled_identity_projection,
    record_identity_decision,
    record_projection_status,
)
from signal_agent.identity_reconciliation.errors import IdentityDecisionError

from .conftest import FIXED_CLOCK, read_json, tree
from .test_decisions import _authority, _rationale


WITNESS_SCHEMA_VERSION = "signal_agent.identity_reconciliation_compatibility_witness.v1"


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path: _sha256(payload) for path, payload in tree(root).items()}


def build_witness(
    candidate_root: Path,
    scenario_root: Path,
    source_run_roots: dict[str, Path],
) -> dict:
    candidates = [
        read_json(path) for path in sorted((candidate_root / "02_candidates").glob("*.json"))
    ]
    proposed = sorted(
        (item for item in candidates if item["status"] == "proposed"),
        key=lambda item: item["candidate_id"],
    )
    conflicting = next(item for item in candidates if item["status"] == "conflicting")

    def paths(candidate: dict) -> tuple[Path, Path]:
        return (
            candidate_root / "02_candidates" / f"{candidate['candidate_id']}.json",
            candidate_root / candidate["evidence_bundle"]["path"],
        )

    blocked_code = ""
    try:
        record_identity_decision(
            *paths(conflicting),
            scenario_root / "blocked-review",
            _authority(),
            "approved",
            _rationale("conflict_must_block"),
        )
    except IdentityDecisionError as exc:
        blocked_code = str(exc)
    approval = record_identity_decision(
        *paths(proposed[0]),
        scenario_root / "review",
        _authority(),
        "approved",
        _rationale("witness_approved"),
        source_run_roots=source_run_roots,
    )
    rejection = record_identity_decision(
        *paths(proposed[1]),
        scenario_root / "review",
        _authority(),
        "rejected",
        _rationale("witness_rejected"),
    )
    deferral = record_identity_decision(
        *paths(proposed[2]),
        scenario_root / "review",
        _authority(),
        "deferred",
        _rationale("witness_deferred"),
    )
    projection = build_reconciled_identity_projection(
        *paths(proposed[0]),
        approval.receipt_path,
        scenario_root / "projection",
        clock=lambda: FIXED_CLOCK,
        source_run_roots=source_run_roots,
    )
    withdrawal_decision = record_identity_decision(
        *paths(proposed[0]),
        scenario_root / "review",
        _authority(),
        "rejected",
        IdentityDecisionRationale(
            reason_code="witness_withdrawal",
            summary="Human reviewer withdrew the previously approved projection.",
        ),
        prior_decision_path=approval.receipt_path,
    )
    status = record_projection_status(
        projection.projection_path,
        withdrawal_decision.receipt_path,
        scenario_root / "projection",
        clock=lambda: "2026-08-03T16:00:00Z",
    )
    return {
        "schema_version": WITNESS_SCHEMA_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "candidate_generation_tree": _tree_hashes(candidate_root),
        "review_tree": _tree_hashes(scenario_root / "review"),
        "projection_tree": _tree_hashes(scenario_root / "projection"),
        "scenario": {
            "candidate_count": len(candidates),
            "proposed_count": len(proposed),
            "conflicting_count": 1,
            "blocked_conflicting_approval": blocked_code,
            "approval_decision_id": approval.decision_id,
            "rejection_decision_id": rejection.decision_id,
            "deferral_decision_id": deferral.decision_id,
            "withdrawal_decision_id": withdrawal_decision.decision_id,
            "projection_id": projection.projection_id,
            "projection_lineage_id": projection.projection_lineage_id,
            "projection_effective_status": status.effective_status,
            "status_receipt_id": status.status_receipt_id,
            "source_records_mutated": False,
            "automatic_merge_performed": False,
        },
    }


def test_milestone_3_witness_is_exact_deterministic_and_reversible(
    candidate_run, tmp_path: Path
) -> None:
    result, source_runs = candidate_run
    source_before = {
        name: tree(source_runs[name]) for name in ("linkedin", "interaction")
    }
    source_run_roots = {
        "linkedin_connections_csv": source_runs["linkedin"],
        "interaction_event_export.v1": source_runs["interaction"],
    }
    first = build_witness(
        result.run_root, tmp_path / "scenario-one", source_run_roots
    )
    second = build_witness(
        result.run_root, tmp_path / "scenario-two", source_run_roots
    )
    expected = read_json(
        source_runs["repository"]
        / "tests/fixtures/identity_reconciliation/compatibility_witness_v1.json"
    )
    assert first == second == expected
    assert first["scenario"]["blocked_conflicting_approval"] == (
        "identity_conflicting_candidate_approval_prohibited"
    )
    assert first["scenario"]["projection_effective_status"] == "withdrawn"
    assert source_before == {
        name: tree(source_runs[name]) for name in ("linkedin", "interaction")
    }
