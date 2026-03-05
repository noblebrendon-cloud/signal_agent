"""dyads.py -- Dyadic state tracking and working_pair_score computation (v0.4).

Computes the compounding vs extractive nature of an exchange between two actors:
  W_{u,a}(t) = 0.25*μ_synth + 0.25*μ_ship + 0.20*μ_scope 
               + 0.15*h_their + 0.10*h_mine 
               - 0.20*A - 0.25*X

Pure functions operating on DyadState.
"""
from __future__ import annotations
import math
from typing import TYPE_CHECKING
import copy

from signal_agent.leviathan.interaction_signals.core.ema import clamped_ema, clamp01

if TYPE_CHECKING:
    from signal_agent.leviathan.interaction_signals.core.types import (
        DyadState, Event, Features, Signal, ActorState, ThreadState
    )


def update_dyad(
    prev: DyadState,
    event: Event,
    feats: Features,
    signal: Signal,
    actor_after: ActorState,
    thread_after: ThreadState,
    alpha: float = 0.2
) -> DyadState:
    """Compute the new DyadState integrating this event."""
    st = copy.copy(prev)
    f = feats.f

    # 1. Determine directionality
    is_mine = (event.actor_id == st.self_actor_id)
    
    # 2. Extract raw deterministic signals (0..1)
    synthesis = float(f.get("synthesis_quality", 0.0))
    shipping  = 1.0 if (f.get("proof_move") or f.get("example_given")) else 0.0
    scope     = float(f.get("scope_control", 0.0))
    novelty   = float(f.get("novelty_injection", 0.0))
    
    extraction_feat = float(f.get("extraction_ratio", 0.0))
    tx_pressure     = float(actor_after.transaction_pressure)
    extraction_raw  = max(extraction_feat, tx_pressure)

    honesty_raw     = 1.0 if signal.mode == "COGNITIVE_HONESTY" else 0.0

    contrib_raw = clamp01(0.40 * novelty + 0.35 * synthesis + 0.25 * shipping)

    # 3. Update EMAs
    st.mutual_synthesis   = clamped_ema(st.mutual_synthesis,   synthesis,      alpha)
    st.mutual_shipping    = clamped_ema(st.mutual_shipping,    shipping,       alpha)
    st.mutual_scope       = clamped_ema(st.mutual_scope,       scope,          alpha)
    st.extraction_penalty = clamped_ema(st.extraction_penalty, extraction_raw, alpha)
    
    if is_mine:
        st.my_honesty = clamped_ema(st.my_honesty, honesty_raw, alpha)
        st.my_contrib = clamped_ema(st.my_contrib, contrib_raw, alpha)
    else:
        st.their_honesty = clamped_ema(st.their_honesty, honesty_raw, alpha)
        st.their_contrib = clamped_ema(st.their_contrib, contrib_raw, alpha)

    # 4. Asymmetry computation
    total_contrib = st.my_contrib + st.their_contrib
    if total_contrib > 1e-9:
        st.asymmetry_penalty = abs(st.my_contrib - st.their_contrib) / total_contrib
    else:
        st.asymmetry_penalty = 0.0

    # 5. Final scalar W
    W_raw = (
        0.25 * st.mutual_synthesis
      + 0.25 * st.mutual_shipping
      + 0.20 * st.mutual_scope
      + 0.15 * st.their_honesty
      + 0.10 * st.my_honesty
      - 0.20 * st.asymmetry_penalty
      - 0.25 * st.extraction_penalty
    )
    st.working_pair_score = clamp01(W_raw)
    st.updated_ts = event.timestamp

    return st
