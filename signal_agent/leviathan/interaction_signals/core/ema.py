"""EMA and clamp helpers."""
from __future__ import annotations


def clamp01(x: float) -> float:
    """Clamp x to [0, 1]."""
    return max(0.0, min(1.0, x))


def ema(prev: float, x: float, alpha: float) -> float:
    """Exponential moving average (unclamped): alpha*x + (1-alpha)*prev."""
    return alpha * x + (1.0 - alpha) * prev


def clamped_ema(prev: float, x: float, alpha: float) -> float:
    """EMA clamped to [0, 1]."""
    return clamp01(ema(prev, x, alpha))
