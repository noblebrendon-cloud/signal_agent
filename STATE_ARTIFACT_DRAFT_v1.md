STATE_ARTIFACT_DRAFT_v1

------------------------------------------------------------
SECTION 1 — REPOSITORY IDENTITY
------------------------------------------------------------
1. Current semantic version tag (if exists): Tag is intended as `v0.4.0` for production hardening.
2. Presence of version constant in code: 
   - `__init__.py` and `app/__init__.py` explicitly set `__version__ = "0.4.0"`
   - `app/agents/meme_offload/schema.py` Line 15 (`SPEC_VERSION_CANONICAL = "meme_spec_v1"`)
   - `app/agents/social_offload/social_offload.py` Line 27 (`TEMPLATE_VERSION = "1.0.0"`)
3. Branch name reference: `main` (IMPLICIT ONLY based on checked out HEAD behavior).
4. Commit hash storage: NOT FOUND identically as hash log, though manual hash metadata lives textually inside `SYSTEM_FREEZE_v0.1.md`.
5. Existence of SYSTEM_STATE.md or state freeze files: `SYSTEM_STATE.md` and `SYSTEM_FREEZE_v0.1.md` exist in the repo root.

------------------------------------------------------------
SECTION 2 — COHERENCE KERNEL PARAMETERS
------------------------------------------------------------
File: `app/audit/coherence_kernel.py`
1. Exact definitions of Φ₁–Φ₅:
   - Φ₁: `1.0 - exp(-self.cfg.lambda1 * float(Vc))` (Line 174)
   - Φ₂: `clamp(Dctx / max(self.cfg.dmax, 1e-9), 0.0, 1.0)` (Line 155)
   - Φ₃: `clamp(Bopen, 0.0, 1.0)` (Line 158)
   - Φ₄: `clamp(Rrate / max(self.cfg.rmax, 1e-9), 0.0, 1.0)` where `Rrate = ret/req` (Line 184)
   - Φ₅: `sigmoid(self.cfg.k * (Tlast - self.cfg.t_target))` (Line 188)
2. All constants (KernelConfig class, Lines 27-75):
   - window_seconds = 60
   - tick_seconds = 5
   - lambda1 = 0.5
   - v_alpha = 4.0
   - dmax = 0.4
   - rmax = 3.0
   - k = 0.1
   - t_target = 300.0
   - w1 = 1.5, w2 = 1.0, w3 = 2.0, w4 = 1.0, w5 = 0.5, alpha = 0.2
   - epsilon = 0.05
   - dphi_ticks = 3
   - K = 1.0
3. Numeric thresholds:
   - STABLE: `stable_enter = 0.15`, `stable_exit = 0.20`
   - PRESSURE: `pressure_enter = 0.20`, `pressure_exit_low = 0.15`, `pressure_exit_high = 0.50`
   - UNSTABLE: `unstable_enter = 0.50`, `unstable_exit_low = 0.45`, `unstable_exit_high = 0.80`
   - FAILURE: `failure_enter = 0.80`
4. Exact SystemHalt trigger condition: `snap.regime == "FAILURE"` handled in `app/utils/resilience.py` Line 156.
5. Hysteresis bands explicitly implemented: YES. Implemented via overlapping thresholds in `_update_regime()` (Lines 226-251).
6. Persisted or transient: `E` is transient. It is computed actively per snapshot dynamically and stored in `KernelSnapshot` object (Lines 223, 280).

------------------------------------------------------------
SECTION 3 — ACTIVATION GOVERNOR BOUNDARY
------------------------------------------------------------
File: `app/governor/activation_governor.py`
1. Definition of enforcement toggle: `enforcement_enabled = state["enforcement_enabled"]` defined globally in state json dict (Line 201).
2. Lock expiration logic: `_parse_utc(lock_expires_raw) > _utc_now()` (Line 252).
3. baseline_fingerprint location: `baseline["fingerprint"]` (Line 203) dynamically loaded from JSON.
4. Files classified as critical internal state: Dynamic list mapped to `baseline["watch_roots"]` (Line 202).
5. Exact mutation denial logic: Blocks if `_is_mutating_scope(scope)` is True AND (`baseline_fingerprint != state_fingerprint` or lock inactive/expired, or scope not authorized) AND no valid override is present (Lines 220-302).
6. Hash drift detection: Automatic during every `enforce()` call via `compute_fingerprint(watch_roots)` (Lines 117-144). 

------------------------------------------------------------
SECTION 4 — CAPTURE LAYER INVARIANTS
------------------------------------------------------------
Directory: `app/hq/capture/`
1. Defined invariants:
   - Logs NEVER touch `artifact_registry.jsonl` (`capture.py` Line 5)
   - NO hashing, NO policy checks, NO constraint checks (`capture.py` Line 6)
   - Never deletes (`decay.py` Line 6)
2. Conflict resolution logic: Greedy deterministic clustering with bridge-doc defense (`promote.py` Line 255).
3. Bridge check implementation: Detected if overlap ratio >= 0.40 against >= 2 clusters with score variance < 0.05. Forces isolation to new cluster (`promote.py` Lines 285-309). 
4. Topic Spike Ratio formula: `ratio = today_count / baseline` where `baseline = (sum(baseline_days) / max(len(baseline_days), 1)) + 1e-9` excluding today (`instability.py` Lines 215-218).
5. Minimum cluster size defaults: `min_cluster_size = 2` (`promote.py` Line 396).
6. Clustering algorithm: Deterministic. Sorted raw file entry inputs, string-based tf-idf stable clustering logic and tie-breakers (`promote.py` Line 115). 

------------------------------------------------------------
SECTION 5 — PROVIDER RESILIENCE
------------------------------------------------------------
File: `app/utils/resilience.py` 
1. Circuit breaker implementation: `CircuitBreaker` dataclass tracking `failures`, `open_until`, and `_probe_allowed` states (Lines 16-70).
2. Retry strategy: Capped exponential backoff up to `max_attempts_per_model=3` (Line 112).
3. Half-open support: YES. Monitored via `get_state()` transitioning to `"HALF_OPEN"` if `now > open_until` (Lines 27-32) utilizing `_probe_allowed`.
4. Backoff parameters: `base_delay_s=0.5`, `max_delay_s=4.0`, `multiplier=2.0`. Deterministic jitter seeded via SHA256 hashing (Lines 370-388). 
5. 503 handling logic: Detects exceptions via `is_capacity_unavailable()` string mapping logic, triggering retries manually (`resilience.py` Lines 93-104).
6. call_with_resilience location: `app/utils/resilience.py` Line 107.
7. Persistence: Memory only. Instances of `CircuitBreaker` object variables.

------------------------------------------------------------
SECTION 6 — TEST COVERAGE SNAPSHOT
------------------------------------------------------------
Directory: `tests/`
1. Total test files: 16
2. Kernel coverage present: YES (`test_enforcement.py` and `sim_stability.py` import `CoherenceKernel`).
3. Governor coverage present: YES (`test_activation_governor.py`).
4. Capture layer coverage present: YES (`test_capture_layer.py`, `test_capture_adversarial.py`, `test_capture_falsification.py`).
5. Resilience layer coverage present: YES (`test_agent_resilience.py`).
6. Skipped tests: NOT FOUND explicit skipped annotations natively.
7. Failing tests marked xfail: NOT FOUND explicit xfail annotations natively.

------------------------------------------------------------
SECTION 7 — DATA STATE SNAPSHOT
------------------------------------------------------------
1. Number of raw intake artifacts: 398 internal items under `data/intake/` and 1 raw file in `data/capture/raw/`.
2. Number of bundled artifacts: 2 files located in `data/capture/promoted/`.
3. Number of spines: 3 spines mapped (`ai_stability_diagnostic`, `content_publishing`, `misc`) mapped locally in `config/spine_router.yaml` and `constraints/spines/`.
4. Largest spine artifact count: `ai_stability_diagnostic` containing 68 nodes inside the subdirectories.
5. Quarantine path: NOT FOUND natively named 'quarantine'. Replaced operationally by `expired_stage1` and `expired_stage2`.
6. Decay logic: Physically relocates files to stage 1 / stage 2 directories via `shutil.move()`; explicitly does NOT delete (`app/hq/capture/decay.py` Line 6).

------------------------------------------------------------
SECTION 8 — CONFIGURATION SURFACE
------------------------------------------------------------
1. Active model provider: NOT FOUND explicitly globally (root `config.yaml` only reads `:Hq_dev`).
2. Model pool configuration: NOT FOUND globally outside code parameters. 
3. Environment variable references: `SIGNAL_AGENT_ROOT`, `CAPTURE_DIR` mapped across capture layer modules bounds context overriding. 
4. Hard-coded secrets: NOT FOUND.
5. Override hierarchy: Environmental variables override physical paths (`os.environ.get("...")`) inside deterministic getters (`_get_root()`). 

------------------------------------------------------------
SECTION 9 — SYSTEM HALT FORENSICS
------------------------------------------------------------
1. Exact halt condition: `snap.regime == "FAILURE"` handled natively triggering `raise SystemHalt()` (`app/utils/resilience.py` Line 156-176).
2. Logging location: Written out to `data/state/panic.log` (`app/audit/coherence_kernel.py` Line 302).
3. Persistence of halt state: Appended reliably as atomic JSON strings during fatal exception trapping (`app/audit/coherence_kernel.py` Line 298). 
4. Recovery mechanism: Explicitly requires manual reset only (`app/audit/coherence_kernel.py` Line 231).

------------------------------------------------------------
SECTION 10 — LIMITATIONS
------------------------------------------------------------
1. **TODO:** `Hydrate snapshot from real usage state (e.g. Redis/DB)` (`app/agent.py` Line 104).
2. **Stub Providers:** `StubProvider` actively mocked (`app/agent.py` Line 17).
3. **Disabled features:** Frontend dashboard buttons hardcoded to state `disabled = true` (`app/hq/dashboard/index.html` Line 145/171). 
