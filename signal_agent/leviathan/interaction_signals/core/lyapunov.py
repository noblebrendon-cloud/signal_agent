"""Lyapunov scalar V(t) for (actor, thread) per event."""
from __future__ import annotations
from .types import Features, Signal, ActorState, ThreadState
from .ema import clamp01

# Actor component weights
W1, W2, W3, W4, W5, W6, W7 = 0.20, 0.15, 0.15, 0.15, 0.10, 0.15, 0.10
# Thread component weights
U1, U2, U3, U4 = 0.25, 0.25, 0.25, 0.25
# Blend: lambda * L_actor + (1-lambda) * L_thread
LAMBDA = 0.6


def compute_lyapunov(
    features: Features,
    signal: Signal,
    actor: ActorState,
    thread: ThreadState,
) -> tuple[float, dict]:
    f = features.f
    extraction  = float(f.get("extraction_ratio", 0.0))
    adversarial = float(f.get("adversarial_tone", 0.0))

    hist_max = max(actor.mode_histogram_30.values()) if actor.mode_histogram_30 else 0.25
    mode_spread = 1.0 - hist_max  # high spread = unsettled

    L_a = (
        W1 * (1.0 - actor.trust_score)
        + W2 * extraction
        + W3 * actor.mode_volatility_30
        + W4 * mode_spread
        + W5 * adversarial
        + W6 * actor.evasion_rate_30
        - W7 * actor.shipping_rate_30
    )
    L_tau = (
        U1 * thread.coordination_cost
        + U2 * (1.0 - thread.convergence_rate)
        + U3 * (1.0 - thread.disagreement_productivity)
        + U4 * (1.0 - thread.artifact_probability)
    )
    V_raw = LAMBDA * L_a + (1.0 - LAMBDA) * L_tau
    V     = clamp01(V_raw)

    return V, {
        "L_a": round(L_a, 6),
        "L_tau": round(L_tau, 6),
        "V_raw": round(V_raw, 6),
        "V": round(V, 6),
    }


def delta_v(v_prev: float | None, v_curr: float) -> float | None:
    return None if v_prev is None else round(v_curr - v_prev, 6)
