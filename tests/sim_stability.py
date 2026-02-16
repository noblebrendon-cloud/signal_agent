# tests/sim_stability.py
import time
from app.audit.coherence_kernel import CoherenceKernel, KernelConfig, Regime

def test_regime_transitions_linear_injection():
    cfg = KernelConfig(window_seconds=60, tick_seconds=5)
    k = CoherenceKernel(cfg)

    start = time.time()

    # Simulate ticks: increase constraint violations and tool instability
    states = []
    for t in range(0, 300, cfg.tick_seconds):  # 5 min sim
        now = start + t
        k.tick(now) # Important: advance window

        # inject requests/retries
        retries = 0
        if t > 180:
             retries = 5 # Force max retries (C4 -> 1.0)
        k.record_request(retries=retries)

        # ramp violations starts at t=30
        if t > 30:
            k.record_constraint_violation(count=1 + (t // 60))

        # ramp breaker open ratio starts at t=60
        bopen = min(1.0, max(0.0, (t - 60) / 180.0))
        k.update_tool_instability_ratio(bopen)
        
        # ramp context drift (C2) at t=120
        dctx = min(1.0, max(0.0, (t - 120) / 60.0))
        k.update_context_drift(dctx)

        snap = k.snapshot(now)
        states.append(snap.regime)
        print(f"Tick {t}: V={k._violations[k._idx]} B={bopen:.2f} PhiR={snap.phi_risk:.2f} E={snap.E:.2f} State={snap.regime}")

    # Verify we hit all regimes
    assert Regime.STABLE in states, "Should start STABLE"
    assert Regime.PRESSURE in states, "Should transition to PRESSURE"
    assert Regime.UNSTABLE in states, "Should transition to UNSTABLE"
    assert Regime.FAILURE in states, "Should eventually hit FAILURE"

if __name__ == "__main__":
    try:
        test_regime_transitions_linear_injection()
        print("SIMULATION SUCCESS: Transited STABLE -> PRESSURE -> UNSTABLE -> FAILURE")
    except AssertionError as e:
        print(f"SIMULATION FAILED: {e}")
        exit(1)
