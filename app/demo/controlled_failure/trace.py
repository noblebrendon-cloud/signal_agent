from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state import DemoState


def default_trace_path() -> Path:
    return _repo_root() / "data" / "state" / "demo" / "demo_event_log.jsonl"


def visible_trace(state: DemoState) -> str:
    return ", ".join(f"{entry['step']}={entry['status']}" for entry in state.trace)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TraceWriter:
    path: Path
    clock: Callable[[], str] = _utc_now

    def record(
        self,
        *,
        runner_type: str,
        step_name: str,
        input_snapshot_id: str,
        output_status: str,
        transition_decision: str,
        reason_code: str | None = None,
    ) -> None:
        event = {
            "timestamp": self.clock(),
            "runner_type": runner_type,
            "step_name": step_name,
            "input_snapshot_id": input_snapshot_id,
            "output_status": output_status,
            "transition_decision": transition_decision,
        }
        if reason_code is not None:
            event["reason_code"] = reason_code
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
