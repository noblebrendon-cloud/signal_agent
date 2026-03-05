"""Actor and thread state update rules."""
from __future__ import annotations
import copy
from .types import Features, Signal, ActorState, ThreadState
from .ema import ema, clamp01
from .transitions import update_transition_matrix

EMA_FAST = 0.2
EMA_MED  = 0.3
MODES    = ["PERFORMANCE", "TRANSACTION", "COGNITIVE_HONESTY", "MIXED"]


def _onehot(mode: str) -> dict[str, float]:
    return {m: (1.0 if m == mode else 0.0) for m in MODES}


def update_actor(actor: ActorState, features: Features, signal: Signal) -> ActorState:
    a = copy.deepcopy(actor)
    f = features.f
    mode = signal.mode
    conf = signal.confidence
    prev_mode = a.last_mode

    # Mode tracking
    a.last_n_modes = (a.last_n_modes + [mode])[-10:]

    # mode_histogram_30 EMA over one-hot
    oh = _onehot(mode)
    for m in MODES:
        a.mode_histogram_30[m] = ema(a.mode_histogram_30.get(m, 0.25), oh[m], EMA_FAST)

    # mode_volatility_30
    changed = 1.0 if (prev_mode is not None and prev_mode != mode) else 0.0
    a.mode_volatility_30 = ema(a.mode_volatility_30, changed, EMA_FAST)

    # transaction_pressure EMA
    ext = float(f.get("extraction_ratio", 0.0))
    a.transaction_pressure = ema(a.transaction_pressure, ext, EMA_FAST)

    # trust_score (slow, bounded)
    eg   = 1.0 if f.get("example_given") else 0.0
    d_t  = 0.0
    if mode == "COGNITIVE_HONESTY":
        d_t += 0.03 * conf
    d_t += 0.02 * eg * conf
    if mode == "TRANSACTION":
        d_t -= 0.04 * conf
    if a.mode_volatility_30 > 0.6:
        d_t -= 0.03
    a.trust_score = clamp01(a.trust_score + d_t)

    # integrity_index
    ch_hist = a.mode_histogram_30.get("COGNITIVE_HONESTY", 0.0)
    a.integrity_index = clamp01((1.0 - a.mode_volatility_30) * max(ch_hist, 0.05))

    # collab_readiness
    a.collab_readiness = clamp01(
        0.45 * a.trust_score + 0.35 * a.integrity_index - 0.25 * a.transaction_pressure
    )

    # pressure_integrity (rapport gate)
    if mode == "TRANSACTION":
        gate = 1.0 if a.trust_score > 0.6 else 0.0
        a.pressure_integrity = clamp01(ema(a.pressure_integrity, ext * gate, EMA_MED))

    # extraction_after_trust
    if mode == "TRANSACTION" and actor.trust_score > 0.5:
        a.extraction_after_trust = clamp01(ema(a.extraction_after_trust, ext, EMA_FAST))

    # evasion_rate_30: TRANSACTION with no evidence
    proof  = 1.0 if f.get("proof_move") else 0.0
    evasion = 1.0 if (mode == "TRANSACTION" and proof == 0.0 and eg == 0.0) else 0.0
    a.evasion_rate_30 = ema(a.evasion_rate_30, evasion, EMA_FAST)

    # shipping_rate_30
    a.shipping_rate_30 = ema(a.shipping_rate_30, max(eg, proof), EMA_FAST)

    # transition matrix
    if prev_mode is not None:
        a.transition_matrix = update_transition_matrix(a.transition_matrix, prev_mode, mode)

    # cooldown drain (1 event per counter; clamped at 0)
    a.cooldown_dm  = max(0, a.cooldown_dm  - 1)
    a.cooldown_off = max(0, a.cooldown_off - 1)

    a.last_mode = mode
    return a


def update_thread(thread: ThreadState, features: Features, signal: Signal) -> ThreadState:
    t = copy.deepcopy(thread)
    f = features.f
    mode = signal.mode

    eg        = 1.0 if f.get("example_given") else 0.0
    proof     = 1.0 if f.get("proof_move") else 0.0
    promo     = float(f.get("promo_density", 0.0))
    causal    = float(f.get("causal_ratio", 0.0))
    integ     = float(f.get("integration_ratio", 0.0))
    challenge = 1.0 if f.get("challenge_present") else 0.0
    repair    = 1.0 if f.get("repair_attempt") else 0.0
    q_ratio   = float(f.get("q_ratio", 0.0))

    t.shipping_evidence_score = clamp01(ema(t.shipping_evidence_score, max(eg, proof), EMA_FAST))
    t.drift_score             = clamp01(ema(t.drift_score, promo, EMA_FAST))
    t.convergence_rate        = clamp01(ema(t.convergence_rate, float(eg and causal > 0.05), EMA_FAST))
    t.disagreement_productivity = clamp01(ema(t.disagreement_productivity, float(bool(challenge) and bool(repair)), EMA_FAST))
    t.coordination_cost       = clamp01(ema(t.coordination_cost, float(q_ratio > 0.3 and causal < 0.05), EMA_FAST))
    t.artifact_probability    = clamp01(ema(t.artifact_probability, float(bool(proof) or bool(eg)), EMA_FAST))
    lev = clamp01(1.0 - promo) if mode in ("PERFORMANCE", "COGNITIVE_HONESTY") else 0.0
    t.leverage_score          = clamp01(ema(t.leverage_score, lev, EMA_FAST))
    t.working_node_score      = clamp01(ema(t.working_node_score, clamp01((integ + causal) / 2.0), EMA_FAST))
    return t
