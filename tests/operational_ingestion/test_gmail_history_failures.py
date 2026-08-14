from __future__ import annotations

import json

import pytest

from signal_agent.operational_ingestion import InjectedOperationalFailure
from signal_agent.operational_ingestion.checkpoints import resolve_current_checkpoint

from .gmail_test_support import SECOND_TIME, projection_path, run_case


KERNEL_FAILURE_STAGES = (
    "after_session",
    "after_attempts",
    "after_captures",
    "after_bounded_material",
    "after_boundary",
    "after_processor",
    "after_manifest_verification",
    "after_observation_index",
    "after_checkpoint_candidate",
    "after_completion_authority",
    "before_checkpoint_commit",
)

PROCESSOR_FAILURE_STAGES = (
    "preservation_failure",
    "after_preservation_failure",
    "normalization_failure",
    "downstream_processing_failure",
    "generic_manifest_promotion_failure",
    "after_downstream_output_before_completed_manifest",
    "operational_manifest_write_failure",
    "manifest_verification_failure",
)


def _seed(case_root):
    governed = case_root / "seed-governed"
    result = run_case(
        case_root,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    return result, governed


def _assert_seed_is_current(seed) -> None:
    current = resolve_current_checkpoint(seed.result.execution.source_root)
    assert current is not None
    assert current.payload == seed.result.execution.checkpoint_commit.payload


@pytest.mark.parametrize("stage", KERNEL_FAILURE_STAGES)
def test_every_kernel_failure_leaves_prior_checkpoint_current(tmp_path, stage):
    seed, governed = _seed(tmp_path)

    def fail(observed: str) -> None:
        if observed == stage:
            raise InjectedOperationalFailure(f"gmail-injected:{stage}")

    failed_governed = tmp_path / f"failed-{stage}"
    with pytest.raises(InjectedOperationalFailure, match=stage):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=seed.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(governed),
            governed_run_root=failed_governed,
            kernel_failure_injector=fail,
        )
    _assert_seed_is_current(seed)
    assert list(seed.result.execution.source_root.rglob("*.failure.json"))
    if stage in {
        "after_session",
        "after_attempts",
        "after_captures",
        "after_bounded_material",
        "after_boundary",
    }:
        assert not (
            failed_governed
            / "05_receipts/gmail_operational_completed_manifest.json"
        ).exists()


@pytest.mark.parametrize("stage", PROCESSOR_FAILURE_STAGES)
def test_every_governed_processor_failure_leaves_prior_checkpoint_current(
    tmp_path, stage
):
    seed, governed = _seed(tmp_path)
    failed_governed = tmp_path / f"failed-{stage}"
    with pytest.raises(Exception):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=seed.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(governed),
            governed_run_root=failed_governed,
            processor_failure_stage=stage,
        )
    _assert_seed_is_current(seed)
    failures = list(seed.result.execution.source_root.rglob("*.failure.json"))
    assert failures
    for path in failures:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["error_detail_persisted"] is False


def test_completed_manifest_is_required_before_checkpoint_advance(tmp_path):
    seed, governed = _seed(tmp_path)
    with pytest.raises(RuntimeError, match="gmail_completed_manifest_not_promoted"):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=seed.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(governed),
            governed_run_root=tmp_path / "missing-manifest",
            processor_failure_stage="operational_manifest_write_failure",
        )
    _assert_seed_is_current(seed)
    assert not (
        tmp_path
        / "missing-manifest/05_receipts/gmail_operational_completed_manifest.json"
    ).exists()


def test_manifest_corruption_is_rejected_before_checkpoint_advance(tmp_path):
    seed, governed = _seed(tmp_path)
    with pytest.raises(Exception):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=seed.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(governed),
            governed_run_root=tmp_path / "corrupt-manifest",
            processor_failure_stage="manifest_verification_failure",
        )
    _assert_seed_is_current(seed)


def test_failure_receipts_never_persist_exception_secrets(tmp_path):
    seed, governed = _seed(tmp_path)

    def fail(stage: str) -> None:
        if stage == "after_boundary":
            raise RuntimeError("Bearer m4c1-secret-value-123456")

    with pytest.raises(RuntimeError, match="secret-value"):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=seed.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(governed),
            governed_run_root=tmp_path / "secret-failure",
            kernel_failure_injector=fail,
        )
    receipts = list(seed.result.execution.source_root.rglob("*.failure.json"))
    assert receipts
    raw = "\n".join(path.read_text(encoding="utf-8") for path in receipts)
    assert "m4c1-secret-value" not in raw
    assert "Bearer" not in raw
    _assert_seed_is_current(seed)
