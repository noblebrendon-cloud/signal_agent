"""engine.py -- single stable API entrypoint for Interaction Signals v0.5.

Usage (programmatic):
    from signal_agent.leviathan.interaction_signals.core.engine import (
        StateStore, process_event, ProcessResult,
    )
    store  = StateStore()
    result = process_event(event, store)   # no ledger
    result = process_event(event, store, ledger_path=Path("my.jsonl"))
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from .types import (
    Event, Features, Signal, ActorState, ThreadState,
    PhasePoint, PhaseVelocity, DyadKey, DyadState,
    ControllerParams, TuningMetrics,
)
from .ema import clamp01, ema, clamped_ema
from .features import compute_features
from .classify import classify
from .state_update import update_actor, update_thread
from .transitions import row_normalize  # just for architectural order validation
from .lyapunov import compute_lyapunov, delta_v
from .phase_space import phase_point, phase_velocity, region_tag
from .dyads import update_dyad
from .policy import PolicyAction, decide_actions
from .ledger import append_ledger

PIPELINE_ORDER = (
    "compute_features",
    "classify",
    "state_update",
    "transitions",
    "compute_lyapunov",
    "phase_space",
    "dyads",
    "decide_actions",
    "append_ledger",
)
PIPELINE_VERSION = "v0.6"


@dataclasses.dataclass
class ProcessResult:
    """Everything produced by one process_event() call."""
    event:          Event
    features:       Features
    signal:         Signal
    actor_before:   ActorState
    actor_after:    ActorState
    thread_before:  ThreadState
    thread_after:   ThreadState
    V:              float
    dV:             float | None
    lyapunov_components: dict[str, Any]
    controller_params: ControllerParams | None = None
    tuning_metrics: TuningMetrics | None = None
    policy_action:  PolicyAction | None = None  # set after full pipeline
    
    # ── v0.4 additions ─────────────────────────────────────────────────────
    phase_point:    PhasePoint | None = None
    phase_velocity: PhaseVelocity | None = None
    phase_region:   str | None = None
    dyad_after:     DyadState | None = None

    # ── v0.5 additions ─────────────────────────────────────────────────────
    pipeline_version: str = PIPELINE_VERSION
    pipeline_order: tuple[str, ...] = PIPELINE_ORDER

    # ── convenience accessors ──────────────────────────────────────────────
    @property
    def mode(self) -> str:
        return self.signal.mode

    @property
    def confidence(self) -> float:
        return self.signal.confidence

    @property
    def alert(self) -> dict | None:
        """Return a pressure-integrity alert dict if threshold breached, else None."""
        return _make_alert(self)


def _make_alert(r: ProcessResult) -> dict | None:
    """
    Pressure integrity alert: fired when:
      - mode is TRANSACTION AND
      - actor pressure_integrity < 0.35 AND
      - thread coordination_cost > 0.55
    OR:
      - V increased from previous event by > adaptive threshold (sudden divergence)
    """
    params = r.controller_params or ControllerParams()
    dv_spike = r.dV is not None and r.dV > params.delta_v_spike_threshold
    pressure_breach = (
        r.signal.mode == "TRANSACTION"
        and r.actor_after.pressure_integrity < 0.35
        and r.thread_after.coordination_cost > 0.55
    )
    if not (dv_spike or pressure_breach):
        return None
    return {
        "kind":  "pressure_integrity" if pressure_breach else "v_spike",
        "event_id":   r.event.event_id,
        "actor_id":   r.event.actor_id,
        "thread_id":  r.event.thread_id,
        "V":          r.V,
        "dV":         r.dV,
        "mode":       r.signal.mode,
        "confidence": r.signal.confidence,
        "pressure_integrity":  r.actor_after.pressure_integrity,
        "coordination_cost":   r.thread_after.coordination_cost,
    }


def _lerp(low: float, high: float, t: float) -> float:
    return low + (high - low) * t


def _bounded_clamped_ema(prev: float, target: float, alpha: float, lo: float, hi: float) -> float:
    """EMA in [0, 1], then clamped to explicit operational bounds."""
    v = clamped_ema(prev, target, alpha)
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


class StateStore:
    """
    In-memory mutable store for actor and thread states.
    One instance per session / conversation group.
    Thread-safe only if accessed from a single thread.
    """

    def __init__(self, self_actor_id: str = "self") -> None:
        self.self_actor_id = self_actor_id
        self._actors:  dict[str, ActorState]  = {}
        self._threads: dict[str, ThreadState] = {}
        self._last_v:  dict[str, float]       = {}   # keyed by "actor_id|thread_id"
        self.system_params = ControllerParams()
        self.system_metrics = TuningMetrics()
        
        # v0.4
        self._last_phase: dict[str, PhasePoint] = {} # keyed by "actor_id|thread_id"
        self._dyads: dict[DyadKey, DyadState] = {}
        self._last_actor_per_thread: dict[str, str] = {}

    # ── actor state ───────────────────────────────────────────────────────
    def get_actor(self, actor_id: str) -> ActorState:
        if actor_id not in self._actors:
            self._actors[actor_id] = ActorState(actor_id=actor_id)
        return self._actors[actor_id]

    def set_actor(self, state: ActorState) -> None:
        self._actors[state.actor_id] = state

    # ── thread state ──────────────────────────────────────────────────────
    def get_thread(self, thread_id: str) -> ThreadState:
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadState(thread_id=thread_id)
        return self._threads[thread_id]

    def set_thread(self, state: ThreadState) -> None:
        self._threads[state.thread_id] = state

    # ── Lyapunov history ──────────────────────────────────────────────────
    def get_last_v(self, actor_id: str, thread_id: str) -> float | None:
        return self._last_v.get(f"{actor_id}|{thread_id}")

    def set_last_v(self, actor_id: str, thread_id: str, v: float) -> None:
        self._last_v[f"{actor_id}|{thread_id}"] = v

    # ── snapshot helpers ──────────────────────────────────────────────────
    @property
    def actor_ids(self) -> list[str]:
        return list(self._actors)

    @property
    def thread_ids(self) -> list[str]:
        return list(self._threads)

    # ── v0.4 helpers ──────────────────────────────────────────────────────
    def get_last_phase(self, actor_id: str, thread_id: str) -> PhasePoint | None:
        return self._last_phase.get(f"{actor_id}|{thread_id}")

    def set_last_phase(self, actor_id: str, thread_id: str, pt: PhasePoint) -> None:
        self._last_phase[f"{actor_id}|{thread_id}"] = pt

    def get_last_actor_in_thread(self, thread_id: str) -> str | None:
        return self._last_actor_per_thread.get(thread_id)

    def set_last_actor_in_thread(self, thread_id: str, actor_id: str) -> None:
        self._last_actor_per_thread[thread_id] = actor_id

    def get_dyad(self, self_id: str, other_id: str) -> DyadState:
        k = (self_id, other_id)
        if k not in self._dyads:
            self._dyads[k] = DyadState(self_actor_id=self_id, other_actor_id=other_id)
        return self._dyads[k]

    def set_dyad(self, state: DyadState) -> None:
        self._dyads[(state.self_actor_id, state.other_actor_id)] = state


def process_event(
    event: Event,
    store: StateStore,
    ledger_path: Path | None = None,
) -> ProcessResult:
    """
    Process one Event through the full pipeline:
      features → classify → state update → Lyapunov → ledger

    Mutates *store* in-place.
    Optionally appends a ledger record to *ledger_path*.

    Returns a ProcessResult with all intermediate and final values.
    """
    actor_before  = store.get_actor(event.actor_id)
    thread_before = store.get_thread(event.thread_id)

    features      = compute_features(event)
    signal        = classify(features)
    actor_after   = update_actor(actor_before, features, signal)
    thread_after  = update_thread(thread_before, features, signal)

    V, components = compute_lyapunov(features, signal, actor_after, thread_after)
    dV            = delta_v(store.get_last_v(event.actor_id, event.thread_id), V)

    store.set_actor(actor_after)
    store.set_thread(thread_after)
    store.set_last_v(event.actor_id, event.thread_id, V)

    # Build the result first (policy needs .alert which is a property on result)
    result = ProcessResult(
        event=event,
        features=features,
        signal=signal,
        actor_before=actor_before,
        actor_after=actor_after,
        thread_before=thread_before,
        thread_after=thread_after,
        V=V,
        dV=dV,
        lyapunov_components=components,
    )
    # ── v0.4 Phase Space ───────────────────────────────────────────────────
    pt = phase_point(actor_after, thread_after, V)
    prev_pt = store.get_last_phase(event.actor_id, event.thread_id)
    vel = phase_velocity(prev_pt, pt)
    region = region_tag(pt)
    store.set_last_phase(event.actor_id, event.thread_id, pt)
    
    result.phase_point = pt
    result.phase_velocity = vel
    result.phase_region = region

    # ── v0.6 Adaptive Lyapunov-Governed Controller ────────────────────────
    # Deterministic update using only prior state and current ProcessResult.
    metrics = store.system_metrics
    prev_region = metrics.previous_phase_region
    did_drift = prev_region is not None and region != prev_region

    alpha = 0.05
    metrics.drift_rate = ema(metrics.drift_rate, 1.0 if did_drift else 0.0, alpha)
    metrics.mean_v = ema(metrics.mean_v, float(V), alpha)
    metrics.mean_abs_dv = ema(metrics.mean_abs_dv, abs(float(dV)) if dV is not None else 0.0, alpha)
    metrics.previous_phase_region = region

    instability_index = clamp01(
        0.5 * metrics.drift_rate
        + 0.3 * float(V)
        + 0.2 * metrics.mean_abs_dv
    )

    params = store.system_params
    theta_target = _lerp(0.55, 0.40, instability_index)
    # Higher instability raises spike threshold to reduce noisy v_spike alerts,
    # while escalation safety remains enforced by the dV > 0 invariant.
    spike_target = _lerp(0.10, 0.18, instability_index)
    flip_target = _lerp(0.25, 0.40, instability_index)

    params.theta_v_escalate = _bounded_clamped_ema(
        params.theta_v_escalate, theta_target, alpha, 0.35, 0.65
    )
    params.delta_v_spike_threshold = _bounded_clamped_ema(
        params.delta_v_spike_threshold, spike_target, alpha, 0.05, 0.30
    )
    params.flip_base_threshold = _bounded_clamped_ema(
        params.flip_base_threshold, flip_target, alpha, 0.10, 0.60
    )

    # Snapshot values for this event to keep replay and ledger output stable.
    result.controller_params = dataclasses.replace(params)
    result.tuning_metrics = dataclasses.replace(metrics)
    
    # ── v0.4 Dyadic Tracking ───────────────────────────────────────────────
    other_actor_id = None
    if event.actor_id != store.self_actor_id:
        other_actor_id = event.actor_id
    else:
        last_actor = store.get_last_actor_in_thread(event.thread_id)
        if last_actor and last_actor != store.self_actor_id:
            other_actor_id = last_actor

    if other_actor_id is not None:
        prev_dyad = store.get_dyad(store.self_actor_id, other_actor_id)
        new_dyad = update_dyad(prev_dyad, event, features, signal, actor_after, thread_after)
        store.set_dyad(new_dyad)
        result.dyad_after = new_dyad
        
    store.set_last_actor_in_thread(event.thread_id, event.actor_id)

    # ── Precedence lock (v0.5) ─────────────────────────────────────────────
    assert result.phase_point is not None, "Precedence violation: phase_space must run before decide_actions"

    # ── v0.2/v0.3 Policy Action ────────────────────────────────────────────
    result.policy_action = decide_actions(result)

    # ── Cooldown hysteresis write-back ─────────────────────────────────────
    pa = result.policy_action
    alert = result.alert
    needs_cooldown = (
        (isinstance(alert, dict) and alert.get("kind") == "v_spike")
        or pa.pressure_protocol
    )
    if needs_cooldown:
        import copy as _copy
        actor_after = _copy.copy(actor_after)
        actor_after.cooldown_dm  = max(actor_after.cooldown_dm,  3)
        actor_after.cooldown_off = max(actor_after.cooldown_off, 5)
        result.actor_after = actor_after
        store.set_actor(actor_after)

    if ledger_path is not None:
        append_ledger(
            event, features, signal,
            actor_before, actor_after,
            thread_before, thread_after,
            V, dV, components,
            policy_action=result.policy_action,
            controller_params=result.controller_params,
            tuning_metrics=result.tuning_metrics,
            ledger_path=ledger_path,
        )

    return result
