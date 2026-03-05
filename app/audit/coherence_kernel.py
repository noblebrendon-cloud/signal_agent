# app/audit/coherence_kernel.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from math import exp
from typing import Optional, Dict, Any
import time


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def sigmoid(x: float) -> float:
    # σ(x) = 1/(1+e^-x)
    return 1.0 / (1.0 + exp(-x))


class Regime(str, Enum):
    STABLE = "STABLE"
    PRESSURE = "PRESSURE"
    UNSTABLE = "UNSTABLE"
    FAILURE = "FAILURE"


@dataclass
class KernelConfig:
    # Windowing
    window_seconds: int = 60
    tick_seconds: int = 5

    # C1
    lambda1: float = 0.5

    # V(t) Report Sigmoid
    v_alpha: float = 4.0

    # C2
    dmax: float = 0.4

    # C4
    rmax: float = 3.0

    # C5
    k: float = 0.1
    t_target: float = 300.0

    # Aggregation
    w1: float = 1.5
    w2: float = 1.0
    w3: float = 2.0
    w4: float = 1.0
    w5: float = 0.5
    alpha: float = 0.2

    # Escalation
    epsilon: float = 0.05
    dphi_ticks: int = 3  # ΔΦ over last N ticks

    # Stability
    K: float = 1.0

    # Hysteresis thresholds (Φrisk)
    stable_enter: float = 0.15
    stable_exit: float = 0.20

    pressure_enter: float = 0.20
    pressure_exit_low: float = 0.15
    pressure_exit_high: float = 0.50

    unstable_enter: float = 0.50
    unstable_exit_low: float = 0.45
    unstable_exit_high: float = 0.80

    failure_enter: float = 0.80


@dataclass
class KernelSnapshot:
    ts: float
    phi1: float
    phi2: float
    phi3: float
    phi4: float
    phi5: float
    phi_risk: float
    coherence: float
    A: float
    R: float
    E: float
    regime: Regime
    V_raw: float = 0.0
    V_report: float = 0.0
    version: str = "0.4.0"


class CoherenceKernel:
    """
    Polarity-consistent kernel:
    - Φi are risk signals in [0,1] (0 good, 1 bad)
    - Φrisk bounded in [0,1]
    - C = 1 - Φrisk
    """

    def __init__(self, cfg: Optional[KernelConfig] = None):
        self.cfg = cfg or KernelConfig()

        # Ring buffers (windowed counters)
        self._slots = max(1, self.cfg.window_seconds // self.cfg.tick_seconds)
        self._idx = 0
        self._tick_ts = time.time()

        self._violations = [0] * self._slots        # C1 numerator
        self._requests = [0] * self._slots          # C4 denominator
        self._retries = [0] * self._slots           # C4 numerator

        # State
        self._phi2: float = 0.0                     # context drift risk
        self._phi3: float = 0.0                     # tool instability risk
        self._last_reset_ts: float = time.time()    # for C5 staleness
        self._regime: Regime = Regime.STABLE

        # For dΦ/dt
        self._phi_hist = []  # list[(ts, phi_risk)]

    # ------------------------
    # Event ingestion (cheap)
    # ------------------------

    def tick(self, now: Optional[float] = None) -> None:
        """
        Advance the window slot if tick_seconds elapsed.
        Call this once per request (or on a timer), before computing stability.
        """
        now = now or time.time()
        if now - self._tick_ts < self.cfg.tick_seconds:
            return

        steps = int((now - self._tick_ts) // self.cfg.tick_seconds)
        for _ in range(steps):
            self._idx = (self._idx + 1) % self._slots
            self._violations[self._idx] = 0
            self._requests[self._idx] = 0
            self._retries[self._idx] = 0
            self._tick_ts += self.cfg.tick_seconds

    def record_request(self, retries: int = 0) -> None:
        self._requests[self._idx] += 1
        self._retries[self._idx] += max(0, int(retries))

    def record_constraint_violation(self, count: int = 1) -> None:
        self._violations[self._idx] += max(0, int(count))

    def update_context_drift(self, Dctx: float) -> None:
        # Φ2 = clamp(Dctx / Dmax, 0, 1)
        self._phi2 = clamp(Dctx / max(self.cfg.dmax, 1e-9), 0.0, 1.0)

    def update_tool_instability_ratio(self, Bopen: float) -> None:
        self._phi3 = clamp(Bopen, 0.0, 1.0)

    def record_breaker_reset(self) -> None:
        # successful HALF_OPEN -> CLOSED transition
        self._last_reset_ts = time.time()

    # ------------------------
    # Metric computation
    # ------------------------

    def _compute_phi(self, now: float) -> Dict[str, float]:
        Vc = sum(self._violations)
        req = sum(self._requests)
        ret = sum(self._retries)

        # C1: 1 - exp(-λ1 * Vc)
        phi1 = 1.0 - exp(-self.cfg.lambda1 * float(Vc))

        # C2: already stored as risk
        phi2 = self._phi2

        # C3: already stored as risk
        phi3 = self._phi3

        # C4: clamp((retries/requests)/Rmax, 0, 1)
        Rrate = (float(ret) / float(req)) if req > 0 else 0.0
        phi4 = clamp(Rrate / max(self.cfg.rmax, 1e-9), 0.0, 1.0)

        # C5: sigmoid(k*(T_last - T_target))
        Tlast = max(0.0, now - self._last_reset_ts)
        phi5 = sigmoid(self.cfg.k * (Tlast - self.cfg.t_target))

        return {"phi1": phi1, "phi2": phi2, "phi3": phi3, "phi4": phi4, "phi5": phi5}

    def _aggregate(self, phi: Dict[str, float]) -> float:
        wsum = self.cfg.w1 + self.cfg.w2 + self.cfg.w3 + self.cfg.w4 + self.cfg.w5
        wavg = (
            self.cfg.w1 * phi["phi1"]
            + self.cfg.w2 * phi["phi2"]
            + self.cfg.w3 * phi["phi3"]
            + self.cfg.w4 * phi["phi4"]
            + self.cfg.w5 * phi["phi5"]
        ) / max(wsum, 1e-9)

        worst = max(phi["phi1"], phi["phi2"], phi["phi3"], phi["phi4"], phi["phi5"])
        phi_risk = (1.0 - self.cfg.alpha) * wavg + self.cfg.alpha * worst
        return clamp(phi_risk, 0.0, 1.0)

    def _compute_escalation(self, now: float, phi_risk: float) -> Dict[str, float]:
        # Maintain history (bounded)
        self._phi_hist.append((now, phi_risk))
        if len(self._phi_hist) > max(20, self.cfg.dphi_ticks + 2):
            self._phi_hist = self._phi_hist[-max(20, self.cfg.dphi_ticks + 2):]

        # A = max(0, dΦ/dt) using ΔΦ over last N ticks
        A = 0.0
        if len(self._phi_hist) >= (self.cfg.dphi_ticks + 1):
            t0, p0 = self._phi_hist[-(self.cfg.dphi_ticks + 1)]
            t1, p1 = self._phi_hist[-1]
            dt = max(1e-9, t1 - t0)
            A = max(0.0, (p1 - p0) / dt)

        # R = 1 - Φ3
        R = 1.0 - self._phi3

        E = A / (R + self.cfg.epsilon)
        return {"A": A, "R": R, "E": E}

    def _update_regime(self, phi_risk: float) -> Regime:
        # Hysteresis-based transitions
        r = self._regime

        if r == Regime.FAILURE:
            return Regime.FAILURE  # manual reset only

        if phi_risk >= self.cfg.failure_enter:
            return Regime.FAILURE

        if r == Regime.UNSTABLE:
            if phi_risk < self.cfg.unstable_exit_low:
                return Regime.PRESSURE
            return Regime.UNSTABLE

        if r == Regime.PRESSURE:
            if phi_risk >= self.cfg.unstable_enter:
                return Regime.UNSTABLE
            if phi_risk < self.cfg.pressure_exit_low:
                return Regime.STABLE
            return Regime.PRESSURE

        # STABLE
        if phi_risk >= self.cfg.pressure_enter:
            return Regime.PRESSURE
        return Regime.STABLE

    def snapshot(self, now: Optional[float] = None) -> KernelSnapshot:
        now = now or time.time()
        self.tick(now)

        phi = self._compute_phi(now)
        phi_risk = self._aggregate(phi)
        coherence = 1.0 - phi_risk

        esc = self._compute_escalation(now, phi_risk)
        A, R, E = esc["A"], esc["R"], esc["E"]

        self._regime = self._update_regime(phi_risk)

        V_raw = phi_risk + (self.cfg.K * E)
        V_report = sigmoid(self.cfg.v_alpha * (V_raw - 1.0))

        return KernelSnapshot(
            ts=now,
            phi1=phi["phi1"],
            phi2=phi["phi2"],
            phi3=phi["phi3"],
            phi4=phi["phi4"],
            phi5=phi["phi5"],
            phi_risk=phi_risk,
            coherence=coherence,
            A=A,
            R=R,
            E=E,
            V_raw=V_raw,
            V_report=V_report,
            regime=self._regime,
        )

    def is_unstable_by_condition(self, snap: KernelSnapshot) -> bool:
        # Stability condition: V_raw <= 1.0 (stable) else unstable
        return snap.V_raw > 1.0


class Priority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


def persist_panic_log(snap: KernelSnapshot, request_id: Optional[str] = None, events_summary: Optional[Dict] = None) -> None:
    try:
        import json
        from pathlib import Path
        path = Path("data/state/panic.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        
        record = {
            "ts": snap.ts,
            "phi_risk": snap.phi_risk,
            "E": snap.E,
            "V_raw": snap.V_raw,
            "V_report": snap.V_report,
            "regime": snap.regime.value,
            "request_id": request_id,
            "events_summary": events_summary or {},
            "version": snap.version,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(snap.ts))
        }
        
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # Halt must proceed even if logging fails
        pass
