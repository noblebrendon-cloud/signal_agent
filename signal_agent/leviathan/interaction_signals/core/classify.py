"""Heuristic classifier: softmax over mode scores with top-3 reason extraction."""
from __future__ import annotations
import math
from .types import Features, Signal
from .ema import clamp01

_MODES = ["PERFORMANCE", "TRANSACTION", "COGNITIVE_HONESTY", "MIXED"]

_W: dict[str, dict[str, float]] = {
    "PERFORMANCE": {
        "proof_move":        1.8,
        "example_given":     1.5,
        "causal_ratio":      1.2,
        "integration_ratio": 1.0,
        "synthesis_quality": 1.0,
        "novelty_injection": 0.8,
        "abstraction_ratio": 0.6,
        "promo_density":    -1.5,
        "adversarial_tone": -0.8,
        "extraction_ratio": -1.0,
        "_bias":             0.1,
    },
    "TRANSACTION": {
        "extraction_ratio":    2.0,
        "promo_density":       1.8,
        "contact_pull":        1.5,
        "authority_ref_ratio": 0.8,
        "self_ref_ratio":      0.5,
        "integration_ratio":  -1.2,
        "proof_move":         -0.5,
        "scope_control":      -0.6,
        "_bias":              -0.5,
    },
    "COGNITIVE_HONESTY": {
        "hedge_ratio":             1.8,
        "q_ratio":                 1.5,
        "repair_attempt":          1.5,
        "challenge_present":       1.2,
        "question_follow_through": 0.8,
        "causal_ratio":            0.8,
        "challenge_intensity":     0.7,
        "certainty_ratio":        -0.8,
        "adversarial_tone":       -1.2,
        "promo_density":          -1.5,
        "_bias":                   0.0,
    },
    "MIXED": {
        "integration_ratio": 0.8,
        "novelty_injection": 0.7,
        "hedge_ratio":       0.5,
        "causal_ratio":      0.5,
        "q_ratio":           0.3,
        "_bias":             0.4,
    },
}


def _fv(f: dict, key: str) -> float:
    v = f.get(key, 0.0)
    return 1.0 if v is True else 0.0 if v is False else float(v)


def _score_mode(f: dict, mode: str) -> tuple[float, dict[str, float]]:
    total = 0.0
    contribs: dict[str, float] = {}
    for feat, w in _W[mode].items():
        if feat == "_bias":
            total += w
            contribs["_bias"] = w
        else:
            v = _fv(f, feat)
            c = w * v
            total += c
            contribs[feat] = c
    return total, contribs


def _softmax(scores: list[float]) -> list[float]:
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    sm = sum(exps)
    return [e / sm for e in exps]


def classify(features: Features) -> Signal:
    f = features.f
    raw, all_c = [], []
    for mode in _MODES:
        sc, ct = _score_mode(f, mode)
        raw.append(sc)
        all_c.append(ct)

    probs = _softmax(raw)
    best  = probs.index(max(probs))
    mode  = _MODES[best]
    conf  = clamp01(probs[best])
    p     = {m: round(probs[i], 6) for i, m in enumerate(_MODES)}

    top3 = sorted(
        ((k, v) for k, v in all_c[best].items() if k != "_bias"),
        key=lambda kv: abs(kv[1]), reverse=True,
    )[:3]
    reasons = [
        f"{k}={_fv(f, k):.3f} (w={_W[mode].get(k, 0):+.1f})"
        for k, _ in top3
    ]
    return Signal(event_id=features.event_id, mode=mode, p=p,
                  confidence=conf, reasons=reasons)
