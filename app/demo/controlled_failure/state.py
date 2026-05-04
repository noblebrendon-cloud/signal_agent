from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any


TraceEntry = dict[str, str]


@dataclass(frozen=True)
class DemoState:
    workflow_id: str
    order_id: str
    state_version: int
    packing_slip_raw: str
    expected_order: dict[str, int] | None
    extract_result: list[dict[str, Any]] | None
    transformed_result: dict[str, int] | None
    verification_result: dict[str, Any] | None
    previous_snapshot_id: str | None
    snapshot_id: str
    trace: tuple[TraceEntry, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "order_id": self.order_id,
            "state_version": self.state_version,
            "packing_slip_raw": self.packing_slip_raw,
            "expected_order": self.expected_order,
            "extract_result": self.extract_result,
            "transformed_result": self.transformed_result,
            "verification_result": self.verification_result,
            "previous_snapshot_id": self.previous_snapshot_id,
            "snapshot_id": self.snapshot_id,
            "trace": list(self.trace),
        }


def create_initial_state(
    *,
    workflow_id: str,
    order_id: str,
    packing_slip_raw: str,
    expected_order: dict[str, int],
) -> DemoState:
    state = DemoState(
        workflow_id=workflow_id,
        order_id=order_id,
        state_version=1,
        packing_slip_raw=packing_slip_raw,
        expected_order=dict(expected_order),
        extract_result=None,
        transformed_result=None,
        verification_result=None,
        previous_snapshot_id=None,
        snapshot_id="",
        trace=(),
    )
    return finalize_state(state)


def advance_state(state: DemoState, **changes: Any) -> DemoState:
    evolved = replace(
        state,
        state_version=state.state_version + 1,
        previous_snapshot_id=state.snapshot_id,
        snapshot_id="",
        **changes,
    )
    return finalize_state(evolved)


def append_trace(
    state: DemoState,
    *,
    step: str,
    status: str,
) -> tuple[TraceEntry, ...]:
    return state.trace + ({"step": step, "status": status},)


def finalize_state(state: DemoState) -> DemoState:
    return replace(state, snapshot_id=compute_snapshot_id(state))


def compute_snapshot_id(state: DemoState) -> str:
    material = state.to_payload()
    material.pop("snapshot_id", None)
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"snap_{digest[:16]}"
