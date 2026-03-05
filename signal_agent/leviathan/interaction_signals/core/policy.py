"""policy.py - deterministic DM/OFF gating and response posture policy."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .types import ControllerParams
from .transitions import row_normalize

if TYPE_CHECKING:
    from .engine import ProcessResult

_LOG4 = math.log(4)  # log |M| for 4 modes, used in entropy normalisation
POLICY_ACTION_VERSION = "0.3"
_DEFAULT_CONTROLLER_PARAMS = ControllerParams()


@dataclass(frozen=True)
class PolicyAction:
    """
    Deterministic output of the DM/OFF gating policy.

    Fields
    ------
    reply_depth       : "low" | "medium" | "high"
    dm_gate           : allow moving conversation to DMs
    off_platform_gate : allow moving conversation off-platform
    ask_for_artifact  : request concrete evidence / code / links
    pressure_protocol : enter de-escalation / scope-clamp posture
    notes             : human-readable audit trail for each decision
    policy_version    : schema version for machine consumers
    reasons           : machine-parseable reason enums
    metrics_snapshot  : minimal policy metrics for aggregation
    """

    reply_depth: str
    dm_gate: bool
    off_platform_gate: bool
    ask_for_artifact: bool
    pressure_protocol: bool
    notes: list[str]
    policy_version: str = POLICY_ACTION_VERSION
    reasons: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, float | int | str | None] = field(default_factory=dict)


def transition_prob(
    transition_matrix: dict[str, dict[str, float]],
    prev: str,
    nxt: str,
) -> float:
    """
    Return normalised P(mode_{t+1}=nxt | mode_t=prev).

    Normalisation is done on the raw EMA-accumulated row so the
    per-edge weights form a proper conditional distribution.
    """
    row = transition_matrix.get(prev)
    if not row:
        return 0.0
    norm = row_normalize({prev: row})
    return float(norm[prev].get(nxt, 0.0))


def mode_entropy_norm(histogram: dict[str, float], eps: float = 1e-9) -> float:
    """
    Normalised Shannon entropy of the actor mode histogram, in [0, 1].

    H_norm = H(p) / log(|M|)

    Uniform histogram -> H_norm near 1.0 (maximum volatility)
    Peaked histogram  -> H_norm near 0.0 (stable actor)
    """
    probs = [max(0.0, float(v)) for v in histogram.values()]
    s = sum(probs)
    if s <= eps:
        return 1.0
    probs = [p / s for p in probs]
    H = -sum(p * math.log(p + eps) for p in probs)
    return min(1.0, max(0.0, H / _LOG4))


def adaptive_flip_threshold(H_norm: float, base_threshold: float | None = None) -> float:
    """
    flip_threshold = flip_base_threshold + 0.20 * H_norm

    Defaults to ControllerParams.flip_base_threshold when base_threshold is None.
    """
    base = _DEFAULT_CONTROLLER_PARAMS.flip_base_threshold if base_threshold is None else float(base_threshold)
    return base + 0.20 * H_norm


def decide_actions(result: "ProcessResult") -> PolicyAction:
    """
    Deterministic policy for DM/OFF gating and response posture.

    Input: ProcessResult from engine.process_event()
    Output: frozen PolicyAction (no side effects)
    """
    notes: list[str] = []
    reason_set: set[str] = set()

    mode: str = result.mode
    V: float = float(result.V)
    dV = None if result.dV is None else float(result.dV)
    alert = result.alert

    actor = result.actor_after
    thread = result.thread_after
    feats = result.features.f

    collab = float(actor.collab_readiness)
    integrity = float(actor.integrity_index)
    tx_pressure = float(actor.transaction_pressure)
    pressure_integrity = float(actor.pressure_integrity)
    extraction_after_trust = float(actor.extraction_after_trust)
    evasion = float(actor.evasion_rate_30)
    shipping = float(actor.shipping_rate_30)
    cooldown_dm = int(actor.cooldown_dm)
    cooldown_off = int(actor.cooldown_off)

    leverage = float(thread.leverage_score)
    artifact_prob = float(thread.artifact_probability)
    coord_cost = float(thread.coordination_cost)
    convergence = float(thread.convergence_rate)

    challenge_present = bool(feats.get("challenge_present", False))
    adversarial_tone = float(feats.get("adversarial_tone", 0.0))
    pressure_event = challenge_present or adversarial_tone > 0.35

    controller = result.controller_params or _DEFAULT_CONTROLLER_PARAMS
    theta_v_escalate = float(controller.theta_v_escalate)
    off_platform_theta = max(0.0, theta_v_escalate - 0.05)

    H_norm = mode_entropy_norm(actor.mode_histogram_30)
    flip_thresh = adaptive_flip_threshold(H_norm, controller.flip_base_threshold)

    tm = actor.transition_matrix or {}
    p_h_to_t = transition_prob(tm, "COGNITIVE_HONESTY", "TRANSACTION") if tm else 0.0

    reply_depth = "medium"
    dm_gate = False
    off_platform_gate = False
    ask_for_artifact = False
    pressure_protocol = False

    if isinstance(alert, dict):
        kind = alert.get("kind")
        if kind == "v_spike":
            reason_set.add("ALERT_V_SPIKE")
            notes.append("v_spike: sudden divergence - constrain scope and request concrete artifact")
            reply_depth = "low"
            ask_for_artifact = True
        elif kind == "pressure_integrity":
            reason_set.add("ALERT_PRESSURE_INTEGRITY")
            notes.append("pressure_integrity alert: TRANSACTION + low integrity + high coord_cost")
            reply_depth = "low"
            ask_for_artifact = True

    if pressure_event and pressure_integrity < 0.45:
        reason_set.add("PRESSURE_PROTOCOL_TRIGGERED")
        notes.append(
            f"pressure_integrity={pressure_integrity:.2f} under adversarial pressure: enter pressure protocol"
        )
        pressure_protocol = True
        reply_depth = "low"
        ask_for_artifact = True

    if mode == "TRANSACTION" or tx_pressure > 0.65:
        reason_set.add("TRANSACTION_GUARDRAIL")
        notes.append("transaction mode/pressure - keep public, do not escalate, require artifacts")
        reply_depth = "low"
        dm_gate = False
        off_platform_gate = False
        ask_for_artifact = True

    if leverage > 0.65 and coord_cost < 0.55 and convergence > 0.55:
        reason_set.add("HIGH_LEVERAGE_THREAD")
        notes.append("thread high-leverage + low coord_cost + converging: deeper engagement OK")
        if reply_depth == "medium":
            reply_depth = "high"

    base_dm_ok = (
        collab > 0.65
        and integrity > 0.55
        and tx_pressure < 0.55
        and extraction_after_trust < 0.50
        and leverage > 0.60
    )

    if p_h_to_t > flip_thresh:
        reason_set.add("FLIP_RISK_BLOCK")
        notes.append(
            f"flip-risk P(HONESTY->TRANSACTION)={p_h_to_t:.2f} "
            f"> adaptive threshold={flip_thresh:.2f} (H_norm={H_norm:.2f}): "
            "delay DM - require proof-of-work first"
        )
        base_dm_ok = False
        ask_for_artifact = True

    dm_gate = base_dm_ok and (V < theta_v_escalate) and (not pressure_protocol)

    off_platform_gate = bool(
        dm_gate
        and shipping > 0.35
        and evasion < 0.35
        and artifact_prob > 0.65
        and V < off_platform_theta
    )

    if leverage > 0.60 and artifact_prob < 0.50:
        reason_set.add("EVIDENCE_GAP_BLOCK")
        notes.append(
            f"leverage={leverage:.2f} but artifact_prob={artifact_prob:.2f}: "
            "request artifact instead of escalating to DM"
        )
        ask_for_artifact = True
        dm_gate = False
        off_platform_gate = False

    if cooldown_dm > 0:
        reason_set.add("COOLDOWN_DM_ACTIVE")
        notes.append(f"cooldown_dm active ({cooldown_dm} events remaining): DM gate locked")
        dm_gate = False
        off_platform_gate = False

    if cooldown_off > 0 and off_platform_gate:
        reason_set.add("COOLDOWN_OFF_ACTIVE")
        notes.append(f"cooldown_off active ({cooldown_off} events remaining): off-platform gate locked")
        off_platform_gate = False

    if (dm_gate or off_platform_gate) and dV is not None and dV > 0.0:
        reason_set.add("DV_POSITIVE_ESCALATION_BLOCK")
        notes.append(f"escalation blocked: dV={dV:+.4f} > 0 (divergence risk)")
        dm_gate = False
        off_platform_gate = False

    if dV is not None:
        if dV < -0.04:
            reason_set.add("DV_STABILISING_TREND")
            notes.append(f"dV={dV:+.4f}: stabilising trend")
        elif dV > 0.04:
            reason_set.add("DV_DESTABILISING_TREND")
            notes.append(f"dV={dV:+.4f}: destabilising trend")

    metrics_snapshot: dict[str, float | int | str | None] = {
        "mode": mode,
        "V": round(V, 6),
        "dV": None if dV is None else round(dV, 6),
        "p_h_to_t": round(p_h_to_t, 6),
        "flip_threshold": round(flip_thresh, 6),
        "flip_base_threshold": round(float(controller.flip_base_threshold), 6),
        "theta_v_escalate": round(theta_v_escalate, 6),
        "off_platform_theta": round(off_platform_theta, 6),
        "delta_v_spike_threshold": round(float(controller.delta_v_spike_threshold), 6),
        "mode_entropy_norm": round(H_norm, 6),
        "collab_readiness": round(collab, 6),
        "integrity_index": round(integrity, 6),
        "transaction_pressure": round(tx_pressure, 6),
        "extraction_after_trust": round(extraction_after_trust, 6),
        "pressure_integrity": round(pressure_integrity, 6),
        "leverage_score": round(leverage, 6),
        "artifact_probability": round(artifact_prob, 6),
        "coordination_cost": round(coord_cost, 6),
        "convergence_rate": round(convergence, 6),
        "cooldown_dm": cooldown_dm,
        "cooldown_off": cooldown_off,
    }

    return PolicyAction(
        reply_depth=reply_depth,
        dm_gate=dm_gate,
        off_platform_gate=off_platform_gate,
        ask_for_artifact=ask_for_artifact,
        pressure_protocol=pressure_protocol,
        notes=notes,
        policy_version=POLICY_ACTION_VERSION,
        reasons=sorted(reason_set),
        metrics_snapshot=metrics_snapshot,
    )
