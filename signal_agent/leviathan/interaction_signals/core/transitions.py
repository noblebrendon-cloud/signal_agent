"""Transition matrix: per-actor 4x4 EMA update on prev->next mode."""
from __future__ import annotations
import copy
from .ema import ema

MODES = ["PERFORMANCE", "TRANSACTION", "COGNITIVE_HONESTY", "MIXED"]
_ALPHA = 0.3


def _init() -> dict[str, dict[str, float]]:
    return {s: {d: 0.25 for d in MODES} for s in MODES}


def update_transition_matrix(
    matrix: dict[str, dict[str, float]],
    from_mode: str,
    to_mode: str,
    alpha: float = _ALPHA,
) -> dict[str, dict[str, float]]:
    m = copy.deepcopy(matrix) if matrix else _init()
    if from_mode not in m:
        m[from_mode] = {d: 0.25 for d in MODES}
    for dst in MODES:
        obs = 1.0 if dst == to_mode else 0.0
        m[from_mode][dst] = ema(m[from_mode][dst], obs, alpha)
    return m


def row_normalize(
    matrix: dict[str, dict[str, float]]
) -> dict[str, dict[str, float]]:
    result = {}
    for src, row in matrix.items():
        total = sum(row.values())
        if total > 0:
            result[src] = {d: v / total for d, v in row.items()}
        else:
            result[src] = {d: 0.25 for d in MODES}
    return result
