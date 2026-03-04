"""Append-only JSONL ledger for Interaction Signals."""
from __future__ import annotations
import dataclasses, json, os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from .types import (
    Event, Features, Signal, ActorState, ThreadState,
    ControllerParams, TuningMetrics,
)

if TYPE_CHECKING:
    from .policy import PolicyAction
    from .types import PhasePoint, PhaseVelocity, DyadState

_DEFAULT = Path(__file__).resolve().parent.parent / "ledger.jsonl"


def _ser(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return obj


def _round_floats(obj: Any, places: int = 6) -> Any:
    if isinstance(obj, float):
        return round(obj, places)
    if isinstance(obj, dict):
        return {k: _round_floats(v, places) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, places) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_round_floats(v, places) for v in obj)
    return obj


def append_ledger(
    event: Event,
    features: Features,
    signal: Signal,
    actor_before: ActorState,
    actor_after: ActorState,
    thread_before: ThreadState,
    thread_after: ThreadState,
    V: float,
    dV: float | None,
    lyapunov_components: dict,
    policy_action: "PolicyAction | None" = None,
    phase_point: "PhasePoint | None" = None,
    phase_velocity: "PhaseVelocity | None" = None,
    phase_region: str | None = None,
    dyad_after: "DyadState | None" = None,
    pipeline_version: str | None = None,
    pipeline_order: tuple[str, ...] | None = None,
    controller_params: ControllerParams | None = None,
    tuning_metrics: TuningMetrics | None = None,
    ledger_path: Path | None = None,
) -> None:
    path = ledger_path or _DEFAULT
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "wrote_utc":     event.timestamp,
        "event":         _ser(event),
        "features":      _ser(features),
        "signal":        _ser(signal),
        "actor_before":  _ser(actor_before),
        "actor_after":   _ser(actor_after),
        "thread_before": _ser(thread_before),
        "thread_after":  _ser(thread_after),
        "lyapunov":      {"V": round(V, 6), "dV": dV, **lyapunov_components},
        "policy_action": _ser(policy_action) if policy_action is not None else None,
        "phase_point":   _ser(phase_point) if phase_point is not None else None,
        "phase_velocity":_ser(phase_velocity) if phase_velocity is not None else None,
        "phase_region":  phase_region,
        "dyad_after":    _ser(dyad_after) if dyad_after is not None else None,
        "pipeline_version": pipeline_version,
        "pipeline_order": _ser(pipeline_order) if pipeline_order is not None else None,
        "controller_params": _round_floats(_ser(controller_params)) if controller_params is not None else None,
        "tuning_metrics": _round_floats(_ser(tuning_metrics)) if tuning_metrics is not None else None,
    }
    line = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
