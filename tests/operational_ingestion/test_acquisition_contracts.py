from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from signal_agent.operational_ingestion import (
    AcquisitionStateError,
    OperationalIngestionKernel,
    OperationalValidationError,
    resolve_current_checkpoint,
)

from .conftest import (
    FIXED_TIME,
    SECOND_TIME,
    FakeGovernedProcessor,
    attempt,
    fixed_clock,
    make_intent,
    observation,
    page,
    standard_history,
)


def test_duplicate_source_observation_has_one_semantic_effect_and_two_provenance_refs(
    tmp_path: Path,
) -> None:
    attempts, pages = standard_history()
    result = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed",
    )
    bounded = result.bounded_material.payload
    assert bounded["observation_count"] == 2
    duplicated = observation("record-2").observation_id
    assert len(result.boundary.payload["observation_capture_provenance"][duplicated]) == 2


def test_changed_content_for_stable_source_key_creates_distinct_observation_versions(
    tmp_path: Path,
) -> None:
    first = observation("record-1", 1)
    changed = observation("record-1", 2)
    attempts = (attempt(1, 1), attempt(2, 1))
    pages = (
        page(1, (first,), terminal=False),
        page(2, (changed,), terminal=True),
    )
    result = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed",
    )
    observations = result.bounded_material.payload["observations"]
    assert len(observations) == 2
    assert {item["protected_source_record_id"] for item in observations} == {"hmac:record-1"}
    assert len({item["content_hash"] for item in observations}) == 2
    assert len({item["observation_id"] for item in observations}) == 2


def test_terminal_page_is_required_before_any_operational_state_is_written(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    invalid = (pages[0], replace(pages[1], terminal=False))
    with pytest.raises(OperationalValidationError, match="terminal_capture_required"):
        OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=invalid,
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed",
        )
    assert not (tmp_path / "store").exists()


def test_repeated_nonterminal_continuation_is_rejected_as_cycle(tmp_path: Path) -> None:
    records = (observation("record-1"),)
    attempts = (attempt(1, 1), attempt(2, 1), attempt(3, 1))
    first = page(1, records, terminal=False)
    second = replace(
        page(2, records, terminal=False),
        next_continuation=first.next_continuation,
    )
    third = page(3, records, terminal=True)
    with pytest.raises(OperationalValidationError, match="pagination_continuation_cycle"):
        OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=(first, second, third),
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed",
        )
    assert not (tmp_path / "store").exists()


def test_stale_or_missing_prior_checkpoint_is_rejected(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    seed = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed-seed",
    )
    with pytest.raises(AcquisitionStateError, match="prior_checkpoint_not_current"):
        OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
            intent=make_intent(),
            session_started_at=SECOND_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed-stale",
        )
    current = resolve_current_checkpoint(seed.source_root)
    assert current.payload["checkpoint_id"] == seed.checkpoint_commit.payload["checkpoint_id"]


def test_second_committed_checkpoint_references_prior_observation_index(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock)
    first = kernel.run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed-first",
    )
    second = kernel.run_from_captured_pages(
        intent=make_intent(prior=first.checkpoint_commit),
        session_started_at=SECOND_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed-second",
    )
    prior_ref = second.observation_index.payload["prior_observation_index"]
    assert prior_ref["observation_index_id"] == first.observation_index.payload["observation_index_id"]
    assert prior_ref["observation_index_hash"] == first.observation_index.payload["artifact_hash"]
    assert "entries" not in second.checkpoint_commit.payload["observation_index"]
    current = resolve_current_checkpoint(second.source_root)
    assert current.payload["checkpoint_id"] == second.checkpoint_commit.payload["checkpoint_id"]
