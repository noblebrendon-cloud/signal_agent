from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .scenario import (
    build_initial_state,
    extract_items,
    inject_expected_order_failure,
    transform_items,
    verify_inventory,
)
from .trace import TraceWriter, default_trace_path


def run_standard_demo(
    *,
    trace_path: Path | None = None,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    writer = TraceWriter(path=trace_path or default_trace_path(), clock=clock or TraceWriter.clock)

    state = build_initial_state()

    input_snapshot_id = state.snapshot_id
    state = extract_items(state)
    writer.record(
        runner_type="standard",
        step_name="extract_items",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )

    input_snapshot_id = state.snapshot_id
    state = transform_items(state)
    writer.record(
        runner_type="standard",
        step_name="transform_items",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )

    state = inject_expected_order_failure(state)

    input_snapshot_id = state.snapshot_id
    state = verify_inventory(state)
    writer.record(
        runner_type="standard",
        step_name="verify_inventory",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )

    return {
        "status": "success",
        "message": "Inventory verified; no discrepancies found.",
        "hidden_problem": "expected_order_present=false",
        "final_state": state,
    }
