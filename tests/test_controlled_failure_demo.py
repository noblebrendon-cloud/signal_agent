from __future__ import annotations

import json
from pathlib import Path

from app.demo.controlled_failure.governed_runner import run_governed_demo
from app.demo.controlled_failure.standard_runner import run_standard_demo


def _jsonl_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _without_timestamps(rows: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for row in rows:
        clone = dict(row)
        clone.pop("timestamp", None)
        normalized.append(clone)
    return normalized


def test_standard_runner_returns_success_even_when_expected_order_is_missing(tmp_path: Path) -> None:
    trace_path = tmp_path / "demo_event_log.jsonl"
    result = run_standard_demo(
        trace_path=trace_path,
        clock=lambda: "2026-05-03T12:00:00Z",
    )

    assert result["status"] == "success"
    assert result["message"] == "Inventory verified; no discrepancies found."
    assert result["hidden_problem"] == "expected_order_present=false"
    assert result["final_state"].expected_order is None
    assert result["final_state"].verification_result == {
        "status": "success",
        "message": "Inventory verified; no discrepancies found.",
        "expected_order_present": False,
    }


def test_governed_runner_fails_closed_when_expected_order_is_missing(tmp_path: Path) -> None:
    trace_path = tmp_path / "demo_event_log.jsonl"
    result = run_governed_demo(
        trace_path=trace_path,
        clock=lambda: "2026-05-03T12:00:00Z",
    )

    assert result["status"] == "fail_closed"
    assert result["reason_code"] == "missing_verification_context"
    assert result["failed_step"] == "verify_inventory"
    assert result["missing_fields"] == ["expected_order"]
    assert result["visible_trace"] == "extract=success, transform=success, verify=blocked"
    assert result["final_state"].expected_order is None


def test_governed_trace_records_verify_inventory_as_blocked(tmp_path: Path) -> None:
    trace_path = tmp_path / "demo_event_log.jsonl"
    run_governed_demo(
        trace_path=trace_path,
        clock=lambda: "2026-05-03T12:00:00Z",
    )

    rows = _jsonl_rows(trace_path)

    assert len(rows) == 3
    assert rows[-1]["runner_type"] == "governed"
    assert rows[-1]["step_name"] == "verify_inventory"
    assert rows[-1]["output_status"] == "blocked"
    assert rows[-1]["transition_decision"] == "block"
    assert rows[-1]["reason_code"] == "missing_verification_context"
    assert rows[-1]["input_snapshot_id"].startswith("snap_")


def test_repeated_runs_are_deterministic_except_for_timestamps(tmp_path: Path) -> None:
    standard_trace_a = tmp_path / "standard_a.jsonl"
    standard_trace_b = tmp_path / "standard_b.jsonl"
    governed_trace_a = tmp_path / "governed_a.jsonl"
    governed_trace_b = tmp_path / "governed_b.jsonl"

    standard_a = run_standard_demo(
        trace_path=standard_trace_a,
        clock=lambda: "2026-05-03T12:00:00Z",
    )
    standard_b = run_standard_demo(
        trace_path=standard_trace_b,
        clock=lambda: "2026-05-03T12:05:00Z",
    )
    governed_a = run_governed_demo(
        trace_path=governed_trace_a,
        clock=lambda: "2026-05-03T12:10:00Z",
    )
    governed_b = run_governed_demo(
        trace_path=governed_trace_b,
        clock=lambda: "2026-05-03T12:15:00Z",
    )

    assert standard_a == standard_b
    assert governed_a == governed_b
    assert _without_timestamps(_jsonl_rows(standard_trace_a)) == _without_timestamps(_jsonl_rows(standard_trace_b))
    assert _without_timestamps(_jsonl_rows(governed_trace_a)) == _without_timestamps(_jsonl_rows(governed_trace_b))
