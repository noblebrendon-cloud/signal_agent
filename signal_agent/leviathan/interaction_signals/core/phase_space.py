"""phase_space.py -- Phase space mapping for interaction dynamics (v0.4).

Maps interaction state into a 4D coordinate system (T, Σ, V, Λ):
- T: Trust score
- Σ: Pressure integrity
- V: Lyapunov scalar
- Λ: Leverage score

Computes phase point, velocity (change vector), and categorical regions.
"""
from __future__ import annotations
import math
from typing import TYPE_CHECKING

from signal_agent.leviathan.interaction_signals.core.types import PhasePoint, PhaseVelocity

if TYPE_CHECKING:
    from signal_agent.leviathan.interaction_signals.core.types import ActorState, ThreadState


def phase_point(actor: ActorState, thread: ThreadState, V: float) -> PhasePoint:
    """Create a PhasePoint from current state scalars."""
    return PhasePoint(
        T=float(actor.trust_score),
        Σ=float(actor.pressure_integrity),
        V=float(V),
        Λ=float(thread.leverage_score),
    )


def phase_velocity(prev: PhasePoint | None, current: PhasePoint) -> PhaseVelocity:
    """Compute vector difference and L2 norm between consecutive points."""
    if prev is None:
        return PhaseVelocity(dT=0.0, dΣ=0.0, dV=0.0, dΛ=0.0, norm_l2=0.0)
    
    dT = current.T - prev.T
    dΣ = current.Σ - prev.Σ
    dV = current.V - prev.V
    dΛ = current.Λ - prev.Λ
    norm = math.sqrt(dT*dT + dΣ*dΣ + dV*dV + dΛ*dΛ)
    
    return PhaseVelocity(dT=dT, dΣ=dΣ, dV=dV, dΛ=dΛ, norm_l2=norm)


def region_tag(point: PhasePoint) -> str:
    """Categorise the phase point into stability/leverage attractors."""
    if point.V < 0.45:
        if point.Λ > 0.65:
            return "stable_high_leverage"
        else:
            return "stable_low_leverage"
    else:
        if point.Λ > 0.65:
            return "unstable_high_leverage"
        else:
            return "unstable_low_leverage"
