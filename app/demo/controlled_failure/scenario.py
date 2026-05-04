from __future__ import annotations

from typing import Any

from .state import DemoState, advance_state, append_trace, create_initial_state


WORKFLOW_ID = "packing_slip_reconciliation"
ORDER_ID = "ORDER-2048"
PACKING_SLIP_RAW = """Packing Slip
Order ID: ORDER-2048
Items:
- SKU-RED-01 | Red Widget | qty=2
- SKU-BLUE-02 | Blue Widget | qty=1
- SKU-GREEN-03 | Green Widget | qty=4
"""
EXPECTED_ORDER = {
    "SKU-RED-01": 2,
    "SKU-BLUE-02": 1,
    "SKU-GREEN-03": 4,
}

_VERIFY_REQUIRED_FIELDS = ("expected_order",)


def build_initial_state() -> DemoState:
    return create_initial_state(
        workflow_id=WORKFLOW_ID,
        order_id=ORDER_ID,
        packing_slip_raw=PACKING_SLIP_RAW,
        expected_order=EXPECTED_ORDER,
    )


def extract_items(state: DemoState) -> DemoState:
    items: list[dict[str, Any]] = []
    for raw_line in state.packing_slip_raw.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        sku, description, qty_part = [part.strip() for part in line[2:].split("|")]
        items.append(
            {
                "sku": sku,
                "description": description,
                "quantity": int(qty_part.removeprefix("qty=")),
            }
        )
    return advance_state(
        state,
        extract_result=items,
        trace=append_trace(state, step="extract", status="success"),
    )


def transform_items(state: DemoState) -> DemoState:
    assert state.extract_result is not None
    normalized = {
        item["sku"]: int(item["quantity"])
        for item in state.extract_result
    }
    return advance_state(
        state,
        transformed_result=normalized,
        trace=append_trace(state, step="transform", status="success"),
    )


def inject_expected_order_failure(state: DemoState) -> DemoState:
    return advance_state(state, expected_order=None)


def verify_inventory(state: DemoState) -> DemoState:
    assert state.transformed_result is not None
    verification_result = {
        "status": "success",
        "message": "Inventory verified; no discrepancies found.",
        "expected_order_present": state.expected_order is not None,
    }
    return advance_state(
        state,
        verification_result=verification_result,
        trace=append_trace(state, step="verify", status="success"),
    )


def missing_verification_fields(state: DemoState) -> list[str]:
    missing = [
        field_name
        for field_name in _VERIFY_REQUIRED_FIELDS
        if getattr(state, field_name) is None
    ]
    return sorted(missing)


def block_verification(
    state: DemoState,
    *,
    reason_code: str,
    missing_fields: list[str],
) -> DemoState:
    verification_result = {
        "status": "fail_closed",
        "reason_code": reason_code,
        "failed_step": "verify_inventory",
        "missing_fields": list(missing_fields),
    }
    return advance_state(
        state,
        verification_result=verification_result,
        trace=append_trace(state, step="verify", status="blocked"),
    )
