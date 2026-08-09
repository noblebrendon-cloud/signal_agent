from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_agent.operational_ingestion import (
    InjectedOperationalFailure,
    OperationalIngestionKernel,
    resolve_current_checkpoint,
    resolve_ingestion_state,
)

from .conftest import (
    FIXED_TIME,
    SECOND_TIME,
    FakeGovernedProcessor,
    fixed_clock,
    make_intent,
    standard_history,
)


INJECTED_STAGES = (
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
    "before_preservation",
    "after_preservation",
    "after_normalization",
    "after_output_before_manifest",
)


def seed_checkpoint(tmp_path: Path):
    attempts, pages = standard_history()
    return OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed-seed",
    )


@pytest.mark.parametrize("injected_stage", INJECTED_STAGES)
def test_prior_checkpoint_remains_current_after_every_kernel_failure(
    tmp_path: Path, injected_stage: str
) -> None:
    seed = seed_checkpoint(tmp_path)
    attempts, pages = standard_history()

    def fail(stage: str) -> None:
        if stage == injected_stage:
            raise InjectedOperationalFailure(f"injected:{stage}")

    kernel = OperationalIngestionKernel(
        tmp_path / "store",
        clock=fixed_clock,
        failure_injector=fail,
    )
    with pytest.raises(InjectedOperationalFailure, match=injected_stage):
        kernel.run_from_captured_pages(
            intent=make_intent(prior=seed.checkpoint_commit),
            session_started_at=SECOND_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / f"governed-{injected_stage}",
        )
    current = resolve_current_checkpoint(seed.source_root)
    assert current is not None
    assert current.payload["checkpoint_id"] == seed.checkpoint_commit.payload["checkpoint_id"]
    successor_slot = seed.source_root / f"checkpoints/from-{seed.checkpoint_commit.payload['checkpoint_id']}"
    assert not (successor_slot / "checkpoint-commit.json").exists()


@pytest.mark.parametrize("processor_stage", PROCESSOR_FAILURE_STAGES)
def test_prior_checkpoint_remains_current_after_governed_processor_failure(
    tmp_path: Path, processor_stage: str
) -> None:
    seed = seed_checkpoint(tmp_path)
    attempts, pages = standard_history()
    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock)
    with pytest.raises(RuntimeError, match="fake_"):
        kernel.run_from_captured_pages(
            intent=make_intent(prior=seed.checkpoint_commit),
            session_started_at=SECOND_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(fail_stage=processor_stage),
            governed_run_root=tmp_path / f"governed-{processor_stage}",
        )
    current = resolve_current_checkpoint(seed.source_root)
    assert current is not None
    assert current.payload["checkpoint_id"] == seed.checkpoint_commit.payload["checkpoint_id"]


def test_failure_receipt_is_schema_valid_and_contains_no_exception_detail(
    tmp_path: Path, repository_root: Path
) -> None:
    attempts, pages = standard_history()

    def fail(stage: str) -> None:
        if stage == "after_boundary":
            raise RuntimeError("Bearer secret-value-must-never-persist")

    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock, failure_injector=fail)
    with pytest.raises(RuntimeError, match="secret-value"):
        kernel.run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed",
        )
    receipts = list((tmp_path / "store").rglob("*.failure.json"))
    assert len(receipts) == 1
    raw = receipts[0].read_text(encoding="utf-8")
    assert "secret-value" not in raw
    assert "Bearer" not in raw
    payload = json.loads(raw)
    assert payload["error_detail_persisted"] is False
    schema = json.loads(
        (
            repository_root
            / "schemas/operational_ingestion/ingestion_failure_receipt.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)


def test_state_resolution_reports_uncommitted_capture_without_advancing_checkpoint(
    tmp_path: Path
) -> None:
    attempts, pages = standard_history()

    def fail(stage: str) -> None:
        if stage == "after_boundary":
            raise InjectedOperationalFailure(stage)

    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock, failure_injector=fail)
    with pytest.raises(InjectedOperationalFailure):
        kernel.run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed",
        )
    source_root = next((tmp_path / "store").glob("osi_*"))
    session = json.loads(next(source_root.rglob("session_descriptor.json")).read_text(encoding="utf-8"))
    state = resolve_ingestion_state(source_root, session["session_id"])
    assert state.stage == "capture_sealed"
    assert state.current_checkpoint_id is None
