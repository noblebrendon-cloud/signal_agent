# tests/sim_stability.py
import time
import statistics
from app.audit.coherence_kernel import CoherenceKernel, KernelConfig, Regime

def test_v_raw_phases():
    cfg = KernelConfig(window_seconds=60, tick_seconds=5)
    k = CoherenceKernel(cfg)

    start = time.time()
    
    stable_v = []
    pressure_v = []
    recovery_v = []
    
    # Phase 1: STABLE (0-60s)
    for t in range(0, 60, cfg.tick_seconds):
        now = start + t
        k.tick(now)
        k.record_request(retries=0)
        snap = k.snapshot(now)
        stable_v.append(snap.V_raw)
        
    # Phase 2: PRESSURE (60-240s)
    for t in range(60, 240, cfg.tick_seconds):
        now = start + t
        k.tick(now)
        
        # Inject constraint violations and tool instability
        if t > 90:
            k.record_constraint_violation(count=2)
            k.record_request(retries=1)
            k.update_tool_instability_ratio(0.4)
            k.update_context_drift(0.3)
        
        snap = k.snapshot(now)
        pressure_v.append(snap.V_raw)
        
    # Phase 3: RECOVERY / CONTAINMENT (240-360s)
    # Stop injecting errors; the rolling window should eventually clear out the violations
    for t in range(240, 360, cfg.tick_seconds):
        now = start + t
        k.tick(now)
        k.record_request(retries=0)
        k.update_tool_instability_ratio(0.0)
        k.update_context_drift(0.0)
        
        snap = k.snapshot(now)
        recovery_v.append(snap.V_raw)

    print(f"STABLE max V_raw: {max(stable_v):.3f}")
    assert max(stable_v) <= 1.0, "V_raw must stay bounded in STABLE phase"
    
    # Slope for PRESSURE phase
    p_slope = pressure_v[-1] - pressure_v[0]
    print(f"PRESSURE overall ΔV_raw (slope): {p_slope:.5f}")
    assert p_slope > 0, "V_raw must increase overall in PRESSURE phase"
    
    # Range of RECOVERY
    print(f"RECOVERY V_raw start -> end: {recovery_v[0]:.3f} -> {recovery_v[-1]:.3f}")
    # Slope for RECOVERY phase
    r_slope = recovery_v[-1] - recovery_v[0]
    print(f"RECOVERY overall ΔV_raw (slope): {r_slope:.5f}")
    assert r_slope <= 0, "V_raw must decrease or stay flat overall in RECOVERY phase"


if __name__ == "__main__":
    try:
        test_v_raw_phases()
        print("SIMULATION SUCCESS: V(t) behavior validated across phases.")
    except AssertionError as e:
        print(f"SIMULATION FAILED: {e}")
        exit(1)
