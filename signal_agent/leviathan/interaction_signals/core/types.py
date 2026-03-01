"""Core type definitions for Interaction Signals v0.1."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    PERFORMANCE       = "PERFORMANCE"
    TRANSACTION       = "TRANSACTION"
    COGNITIVE_HONESTY = "COGNITIVE_HONESTY"
    MIXED             = "MIXED"


MODES = [m.value for m in Mode]


@dataclass
class Event:
    event_id:  str
    actor_id:  str
    thread_id: str
    timestamp: str
    text:      str
    meta:      dict[str, Any] = field(default_factory=dict)


@dataclass
class Features:
    event_id: str
    f: dict[str, Any] = field(default_factory=dict)


@dataclass
class Signal:
    event_id:   str
    mode:       str
    p:          dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    reasons:    list[str] = field(default_factory=list)


@dataclass
class ActorState:
    actor_id:               str
    trust_score:            float = 0.5
    collab_readiness:       float = 0.5
    integrity_index:        float = 0.5
    transaction_pressure:   float = 0.0
    mode_histogram_30:      dict[str, float] = field(default_factory=lambda: {
        "PERFORMANCE": 0.25, "TRANSACTION": 0.25,
        "COGNITIVE_HONESTY": 0.25, "MIXED": 0.25,
    })
    mode_volatility_30:     float = 0.0
    last_n_modes:           list[str] = field(default_factory=list)
    pressure_integrity:     float = 0.5
    extraction_after_trust: float = 0.0
    evasion_rate_30:        float = 0.0
    shipping_rate_30:       float = 0.0
    last_mode:              str | None = None
    transition_matrix:      dict[str, dict[str, float]] = field(default_factory=dict)
    cooldown_dm:            int = 0   # events remaining before DM gate may re-open
    cooldown_off:           int = 0   # events remaining before off-platform gate may re-open


@dataclass
class ThreadState:
    thread_id:                 str
    working_node_score:        float = 0.5
    shipping_evidence_score:   float = 0.0
    drift_score:               float = 0.0
    leverage_score:            float = 0.5
    artifact_probability:      float = 0.5
    coordination_cost:         float = 0.5
    convergence_rate:          float = 0.5
    disagreement_productivity: float = 0.5


# ── v0.4 Additions ─────────────────────────────────────────────────────────

@dataclass
class PhasePoint:
    """Coordinate in the (T, Σ, V, Λ) phase space."""
    T: float   # trust_score
    Σ: float   # pressure_integrity
    V: float   # Lyapunov scalar
    Λ: float   # leverage_score


@dataclass
class PhaseVelocity:
    """Change in phase space coordinates."""
    dT: float
    dΣ: float
    dV: float
    dΛ: float
    norm_l2: float


@dataclass
class ControllerParams:
    """Adaptive control thresholds used by policy and alerting."""
    theta_v_escalate: float = 0.45
    delta_v_spike_threshold: float = 0.14
    flip_base_threshold: float = 0.30


@dataclass
class TuningMetrics:
    """Internal deterministic EMA metrics for controller adaptation."""
    drift_rate: float = 0.0
    mean_v: float = 0.0
    mean_abs_dv: float = 0.0
    previous_phase_region: str | None = None


# Used as key in StateStore
DyadKey = tuple[str, str]  # (self_actor_id, other_actor_id)


@dataclass
class DyadState:
    """Tracks the collaborative history of a working pair."""
    self_actor_id: str
    other_actor_id: str
    
    # EMAs
    mutual_synthesis:   float = 0.0
    mutual_shipping:    float = 0.0
    mutual_scope:       float = 0.0
    
    my_honesty:         float = 0.0
    their_honesty:      float = 0.0
    
    my_contrib:         float = 0.0
    their_contrib:      float = 0.0
    
    asymmetry_penalty:  float = 0.0
    extraction_penalty: float = 0.0
    
    # Final scalar W ∈ [0, 1]
    working_pair_score: float = 0.0
    
    updated_ts:         str = ""
