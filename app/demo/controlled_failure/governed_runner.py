from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .scenario import (
    block_verification,
    build_initial_state,
    extract_items,
    inject_expected_order_failure,
    missing_verification_fields,
    transform_items,
    verify_inventory,
)
from .trace import TraceWriter, default_trace_path, visible_trace


def run_governed_demo(
    *,
    trace_path: Path | None = None,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    writer = TraceWriter(path=trace_path or default_trace_path(), clock=clock or TraceWriter.clock)

    state = build_initial_state()

    input_snapshot_id = state.snapshot_id
    state = extract_items(state)
    writer.record(
        runner_type="governed",
        step_name="extract_items",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )

    input_snapshot_id = state.snapshot_id
    state = transform_items(state)
    writer.record(
        runner_type="governed",
        step_name="transform_items",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )

    state = inject_expected_order_failure(state)
    missing_fields = missing_verification_fields(state)

    if missing_fields:
        input_snapshot_id = state.snapshot_id
        state = block_verification(
            state,
            reason_code="missing_verification_context",
            missing_fields=missing_fields,
        )
        writer.record(
            runner_type="governed",
            step_name="verify_inventory",
            input_snapshot_id=input_snapshot_id,
            output_status="blocked",
            transition_decision="block",
            reason_code="missing_verification_context",
        )
        return {
            "status": "fail_closed",
            "reason_code": "missing_verification_context",
            "failed_step": "verify_inventory",
            "missing_fields": missing_fields,
            "visible_trace": visible_trace(state),
            "final_state": state,
        }

    input_snapshot_id = state.snapshot_id
    state = verify_inventory(state)
    writer.record(
        runner_type="governed",
        step_name="verify_inventory",
        input_snapshot_id=input_snapshot_id,
        output_status="success",
        transition_decision="advance",
    )
    return {
        "status": "success",
        "message": "Inventory verified; no discrepancies found.",
        "visible_trace": visible_trace(state),
        "final_state": state,
    }
