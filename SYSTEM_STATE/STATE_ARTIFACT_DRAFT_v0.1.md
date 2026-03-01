# SYSTEM_STATE Artifact Draft v0.1

Repository root evaluated: `E:\signal_agent`

## 1) REPO IDENTITY

Claim: current branch = `feat/capture_layer_v0.1`.
Evidence:
- File path: `E:\signal_agent\.git\HEAD`
- Symbol: `HEAD ref`
- Snippet (line 1):
```text
     1 ref: refs/heads/feat/capture_layer_v0.1
```

Claim: HEAD hash = `8cc13e56ea56d76f0f73951a7c65414d579efa84`.
Evidence:
- File path: `E:\signal_agent\.git\refs\heads\feat\capture_layer_v0.1`
- Symbol: `branch ref`
- Snippet (line 1):
```text
     1 8cc13e56ea56d76f0f73951a7c65414d579efa84
```

Claim: remote(s) = NOT FOUND.
Evidence:
- File path: `COMMAND: git -C E:\signal_agent remote -v`
- Symbol: `stdout`
- Snippet (line 1):
```text
     1 NO_REMOTES_CONFIGURED
```

Claim: working tree status = dirty.
Evidence:
- File path: `COMMAND: git -C E:\signal_agent status --porcelain=v1 -b`
- Symbol: `stdout`
- Snippet (lines 1-5):
```text
     1 ## feat/capture_layer_v0.1
     2  M SYSTEM_FREEZE_v0.1.md
     3  M app/audit/__pycache__/coherence_kernel.cpython-312.pyc
     4  M business/legal/archive/v0.1-legal-freeze/LEGAL_README.md
     5  M business/legal/copyright_packet/MASTER_SUMMARY.md
```

Claim: tags found.
Evidence:
- File path: `COMMAND: git -C E:\signal_agent tag --list`
- Symbol: `stdout`
- Snippet (lines 1-5):
```text
     1 capture_layer_v0.1
     2 capture_layer_v0.2
     3 capture_layer_v0.3
     4 meme_offload_v0.1
     5 meme_offload_v0.2
```
Evidence:
- File path: `COMMAND: git -C E:\signal_agent tag --list`
- Symbol: `stdout`
- Snippet (lines 6-9):
```text
     6 meme_offload_v0.3
     7 operator_guide_v1
     8 signal_pipelines_v0.1
     9 v0.1-legal-freeze
```

Claim: top-level version metadata files: FOUND (`__init__.py` and `app/__init__.py` explicitly set `__version__ = "0.4.0"`).
Evidence:
- File path: `COMMAND: Test-Path checks`
- Symbol: `stdout`
- Snippet (lines 1-5):
```text
     1 pyproject.toml NOT FOUND
     2 setup.py NOT FOUND
     3 setup.cfg NOT FOUND
     4 package.json NOT FOUND
     5 VERSION NOT FOUND
     6 __init__.py FOUND
```

Claim: version constants found (multiple definitions).
Evidence:
- File path: `E:\signal_agent\app\agents\social_offload\social_offload.py`
- Symbol: `TEMPLATE_VERSION`
- Snippet (line 27):
```text
    27 TEMPLATE_VERSION = "1.0.0"
```
Evidence:
- File path: `E:\signal_agent\app\agents\meme_offload\schema.py`
- Symbol: `SPEC_VERSION_CANONICAL`
- Snippet (line 15):
```text
    15 SPEC_VERSION_CANONICAL = "meme_spec_v1"
```
Evidence:
- File path: `E:\signal_agent\constraints\packs\domain\content_meme\CONTENT_MEME_OFFLOAD_v1.yaml`
- Symbol: `pack_metadata.version`
- Snippet (line 4):
```text
     4   version: "1.1.0"
```

Claim: `__version__` / `VERSION=` symbols in `app` = FOUND.
Evidence:
- File path: `COMMAND: rg -n "__version__|^VERSION\\s*=|^version\\s*="`
- Symbol: `stdout`
- Snippet:
```text
     1 __init__.py:1:__version__ = "0.4.0"
     2 app/__init__.py:1:__version__ = "0.4.0"
     3 app/audit/coherence_kernel.py:94:    version: str = "0.4.0"
```

Claim: precedence across those version definitions = IMPLICIT ONLY.
Evidence:
- File path: `E:\signal_agent\app\agents\social_offload\social_offload.py`
- Symbol: `TEMPLATE_VERSION`
- Snippet:
```text
    27 TEMPLATE_VERSION = "1.0.0"
```

## 2) COHERENCE KERNEL PARAMETERS

Claim: kernel file located at `app/audit/coherence_kernel.py`.
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\app | rg coherence_kernel`
- Symbol: `stdout`
- Snippet:
```text
     1 E:\signal_agent\app\audit\coherence_kernel.py
```

Claim: Φ1 = `1 - exp(-lambda1 * Vc)`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `_compute_phi -> phi1`
- Snippet (lines 173-174):
```text
   173         # C1: 1 - exp(-λ1 * Vc)
   174         phi1 = 1.0 - exp(-self.cfg.lambda1 * float(Vc))
```

Claim: Φ2 = `clamp(Dctx / dmax, 0, 1)`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `update_context_drift`
- Snippet (lines 154-155):
```text
   154         # Φ2 = clamp(Dctx / Dmax, 0, 1)
   155         self._phi2 = clamp(Dctx / max(self.cfg.dmax, 1e-9), 0.0, 1.0)
```

Claim: Φ3 = `clamp(Bopen, 0, 1)`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `update_tool_instability_ratio`
- Snippet (lines 157-158):
```text
   157     def update_tool_instability_ratio(self, Bopen: float) -> None:
   158         self._phi3 = clamp(Bopen, 0.0, 1.0)
```

Claim: Φ4 = `clamp((retries/requests)/rmax, 0, 1)`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `_compute_phi -> phi4`
- Snippet (lines 183-184):
```text
   183         Rrate = (float(ret) / float(req)) if req > 0 else 0.0
   184         phi4 = clamp(Rrate / max(self.cfg.rmax, 1e-9), 0.0, 1.0)
```

Claim: Φ5 = `sigmoid(k*(T_last - T_target))`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `_compute_phi -> phi5`
- Snippet (lines 187-188):
```text
   187         Tlast = max(0.0, now - self._last_reset_ts)
   188         phi5 = sigmoid(self.cfg.k * (Tlast - self.cfg.t_target))
```

Claim: V(t) uses `V_raw = phi_risk + (K * E)` and `V_report = sigmoid(v_alpha*(V_raw-1.0))`.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `snapshot`
- Snippet (lines 266-267):
```text
   266         V_raw = phi_risk + (self.cfg.K * E)
   267         V_report = sigmoid(self.cfg.v_alpha * (V_raw - 1.0))
```

Claim: thresholds (stable/pressure/unstable/failure) are explicit.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `KernelConfig`
- Snippet (lines 64-69):
```text
    64     stable_enter: float = 0.15
    65     stable_exit: float = 0.20
    67     pressure_enter: float = 0.20
    68     pressure_exit_low: float = 0.15
    69     pressure_exit_high: float = 0.50
```
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `KernelConfig`
- Snippet (lines 71-75):
```text
    71     unstable_enter: float = 0.50
    72     unstable_exit_low: float = 0.45
    73     unstable_exit_high: float = 0.80
    75     failure_enter: float = 0.80
```

Claim: decay/sigmoid/K parameters are explicit (`lambda1=0.5`, `v_alpha=4.0`, `k=0.1`, `t_target=300.0`, `epsilon=0.05`, `K=1.0`).
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `KernelConfig`
- Snippet (lines 33-36):
```text
    33     lambda1: float = 0.5
    35     # V(t) Report Sigmoid
    36     v_alpha: float = 4.0
```
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `KernelConfig`
- Snippet (lines 45-47):
```text
    45     k: float = 0.1
    46     t_target: float = 300.0
```
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `KernelConfig`
- Snippet (lines 57-61):
```text
    57     epsilon: float = 0.05
    61     K: float = 1.0
```

Claim: half-life/decay-rate constants in kernel/resilience = NOT FOUND.
Evidence:
- File path: `COMMAND: rg -n "half[-_ ]?life|half_life|decay_rate|decay|tau|lambda1|v_alpha|k\\s*:|K\\s*:" ...`
- Symbol: `stdout`
- Snippet (lines 1-4):
```text
     1 E:\signal_agent\app\audit\coherence_kernel.py:33:    lambda1: float = 0.5
     2 E:\signal_agent\app\audit\coherence_kernel.py:36:    v_alpha: float = 4.0
     3 E:\signal_agent\app\audit\coherence_kernel.py:45:    k: float = 0.1
     4 E:\signal_agent\app\audit\coherence_kernel.py:61:    K: float = 1.0
```

Claim: SystemHalt trigger condition is `snap.regime == FAILURE`; hysteresis includes a FAILURE latch (`manual reset only`).
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `call_with_resilience`
- Snippet (lines 157-158):
```text
   157         if snap.regime == "FAILURE":
   158             from app.audit.coherence_kernel import persist_panic_log
```
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `call_with_resilience`
- Snippet (lines 166,176):
```text
   166             persist_panic_log(snap, request_id=working_request_id, events_summary=summary)
   176             raise SystemHalt()
```
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `_update_regime`
- Snippet (lines 230-234):
```text
   230         if r == Regime.FAILURE:
   231             return Regime.FAILURE  # manual reset only
   233         if phi_risk >= self.cfg.failure_enter:
   234             return Regime.FAILURE
```

Claim: kernel config overrides from env/yaml/cli = NOT FOUND; programmatic `cfg` arg exists.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `CoherenceKernel.__init__`
- Snippet (lines 104-105):
```text
   104     def __init__(self, cfg: Optional[KernelConfig] = None):
   105         self.cfg = cfg or KernelConfig()
```
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `SignalAgent.__init__`
- Snippet (line 60):
```text
    60         self.kernel = CoherenceKernel()
```
## 3) ACTIVATION GOVERNOR BOUNDARY

Claim: activation governor file set includes `app/governor/activation_governor.py` and `app/governor/__init__.py`.
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\app | rg "activation_governor|governor"`
- Symbol: `stdout`
- Snippet:
```text
     1 E:\signal_agent\app\governor\__init__.py
     2 E:\signal_agent\app\governor\activation_governor.py
```

Claim: enforcement toggle is `enforcement_enabled` bool; disabled enforcement allows mutations.
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `validate_state`
- Snippet (lines 70-71):
```text
    70     if not isinstance(state.get("enforcement_enabled"), bool):
    71         raise ValueError("enforcement_enabled_required_bool")
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `enforce`
- Snippet (lines 244-247):
```text
   244     if not enforcement_enabled:
   245         decision["decision"] = "ALLOW"
   246         decision["reason"] = "enforcement_disabled"
   247         return decision
```

Claim: lock expiration logic checks `expires_at_utc` > current UTC.
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `enforce`
- Snippet (lines 249-253):
```text
   249     lock_active = bool(lock.get("active", False))
   250     lock_expires_raw = lock.get("expires_at_utc")
   251     if lock_active and lock_expires_raw:
   252         lock_active = _parse_utc(lock_expires_raw) > _utc_now()
```

Claim: baseline fingerprint uses SHA256 over watch roots + sorted file contents.
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `compute_fingerprint`
- Snippet (lines 117-123):
```text
   117 def compute_fingerprint(watch_roots: list[str]) -> str:
   118     hasher = hashlib.sha256()
   119     for raw_root in watch_roots:
   120         root = Path(raw_root)
   121         root_token = str(root.as_posix())
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `compute_fingerprint`
- Snippet (lines 132-134):
```text
   132             files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
   133 
   134         for file_path in files:
```

Claim: protected watch roots are explicit and mutable scopes are any scope not in `_NON_MUTATING_SCOPES`.
Evidence:
- File path: `E:\signal_agent\app\governor\__init__.py`
- Symbol: `DEFAULT_WATCH_ROOTS`
- Snippet (lines 22-27):
```text
    22 DEFAULT_WATCH_ROOTS = [
    23     "app/agents",
    24     "app/hq",
    25     "app/cli",
    26     "constraints/packs",
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `_NON_MUTATING_SCOPES`
- Snippet (lines 16-21):
```text
    16 _NON_MUTATING_SCOPES = {
    17     "governor.status",
    18     "governor.review",
    19     "governor.override",
    20     "capture.status",
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `_is_mutating_scope`
- Snippet (lines 42-43):
```text
    42 def _is_mutating_scope(scope: str) -> bool:
    43     return scope not in _NON_MUTATING_SCOPES
```

Claim: mutation denial logic blocks on drift (mutating scope) and unauthorized scope during lock.
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `enforce`
- Snippet (lines 234-237):
```text
   234         if mutating_scope:
   235             decision["decision"] = "BLOCK"
   236             decision["reason"] = "drift_detected"
   237             return decision
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `enforce`
- Snippet (lines 300-302):
```text
   300     decision["decision"] = "BLOCK"
   301     decision["reason"] = "scope_not_authorized_during_lock"
   302     return decision
```

Claim: audit logging locations are explicit.
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `DEFAULT_STATE_PATH`, `DEFAULT_EVENT_LOG_PATH`
- Snippet (lines 12-13):
```text
    12 DEFAULT_STATE_PATH = Path("data/state/activation_governor.json")
    13 DEFAULT_EVENT_LOG_PATH = Path("data/state/activation_events.jsonl")
```
Evidence:
- File path: `E:\signal_agent\app\governor\activation_governor.py`
- Symbol: `append_event`
- Snippet (lines 147-150):
```text
   147 def append_event(log_path: Path, event: dict) -> None:
   148     if not isinstance(event, dict):
   149         raise ValueError("event_must_be_dict")
   150     append_jsonl_atomic(jsonl_path=log_path, record=event)
```

## 4) CAPTURE LAYER INVARIANTS

Claim: invariants explicitly say no artifact registry writes, no hashing/policy/constraints.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\capture.py`
- Symbol: `module docstring`
- Snippet (lines 4-6):
```text
     4 Stores raw notes into data/capture/raw/ with JSONL telemetry.
     5 NEVER touches artifact_registry.jsonl.
     6 NO hashing, NO policy checks, NO constraint checks.
```

Claim: clustering determinism uses sorted raw files + deterministic TF sorting.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `promote_run`
- Snippet (lines 417-418):
```text
   417     # 1) Read raw files (sorted ascending for determinism)
   418     raw_files = sorted(raw_dir.glob("raw_*.md"))[:max_files]
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_build_tf`
- Snippet (lines 114-116):
```text
   114     # Take top K by capped count (deterministic: sort by -count then alpha)
   115     top = sorted(capped.items(), key=lambda x: (-x[1], x[0]))[:_TOP_K]
   116     return {word: count / total for word, count in top}
```

Claim: clustering is greedy and order-dependent (docs must be sorted).
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_cluster_docs`
- Snippet (lines 255-259):
```text
   255     """Greedy deterministic clustering with bridge-doc defense. Docs must be sorted. Returns (clusters, bridge_forced_count)."""
   256     clusters: List[_Cluster] = []
   257     bridge_forced_count = 0
   259     for doc in docs:
```

Claim: bridge conflict resolution thresholds are explicit (`score diff < 0.05`, overlap `>=0.40`).
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_cluster_docs bridge check`
- Snippet (lines 289-290):
```text
   289             # Check score difference < 0.05
   290             if (s1 - s2) < 0.05:
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_cluster_docs bridge check`
- Snippet (lines 303-305):
```text
   303                 # If high overlap with both (>= 0.40)
   304                 if ov1 >= 0.40 and ov2 >= 0.40:
   305                     # Bridge detected! Force new cluster to separate them
```

Claim: topic spike ratio formula is explicit.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\instability.py`
- Symbol: `scan_instability baseline+ratio`
- Snippet (lines 214-218):
```text
   214         baseline_days = [daily.get(ds, 0) for ds in day_strings[1:]]
   215         baseline = (sum(baseline_days) / max(len(baseline_days), 1)) + 1e-9
   217         if baseline > 0:
   218             ratio = today_count / baseline
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\instability.py`
- Symbol: `scan_instability spike rule`
- Snippet (lines 227-229):
```text
   227         is_spike = (
   228             (today_count >= min_today and ratio >= spike_ratio) or
   229             (today_count >= 12)
```

Claim: minimum cluster size default is `2`; viable filter uses `len(c.docs) >= min_cluster_size`.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `promote_run signature`
- Snippet (lines 395-397):
```text
   395     window_hours: float = 48.0,
   396     min_cluster_size: int = 2,
   397     max_files: int = 500,
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `promote_run filter`
- Snippet (line 439):
```text
   439     viable = [c for c in clusters if len(c.docs) >= min_cluster_size]
```

Claim: router scoring and conflict/tie resolution are explicit.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\router.py`
- Symbol: `score_bundle`
- Snippet (line 142):
```text
   142     score = 0.65 * keyword_rate + 0.35 * domain_rate
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\router.py`
- Symbol: `route_bundle tie-break`
- Snippet (lines 196-197):
```text
   196     # Sort: highest score, then alphabetical name (stable tie-break)
   197     scores.sort(key=lambda x: (-x[0], x[1]))
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\router.py`
- Symbol: `route_bundle misc threshold`
- Snippet (lines 201-203):
```text
   201     # If best score < 0.12, route to misc
   202     if best_score < 0.12:
   203         best_name = "misc"
```

## 5) PROVIDER RESILIENCE

Claim: retry strategy is exponential+capped with deterministic jitter.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `call_with_resilience params`
- Snippet (lines 112-115):
```text
   112     max_attempts_per_model: int = 3,
   113     base_delay_s: float = 0.5,
   114     max_delay_s: float = 4.0,
   115     multiplier: float = 2.0,
```
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `backoff formula`
- Snippet (line 370):
```text
   370                         base_backoff = min(max_delay_s, base_delay_s * (multiplier ** attempt_index))
```
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `deterministic jitter seed`
- Snippet (lines 372-376):
```text
   372                         seed_str = f"{provider_id}:{model_id}:{working_request_id}:{attempt_index}"
   374                         digest = hashlib.sha256(seed_str.encode()).digest()
   375                         seed_int = int.from_bytes(digest[:8], "big")
   376                         rng = random.Random(seed_int)
```

Claim: circuit breaker states and thresholds are explicit.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `state comments`
- Snippet (lines 21-23):
```text
    21     # If open_until > now => OPEN
    22     # If open_until <= now and open_until > 0 => HALF_OPEN (allows 1 probe)
    23     # If open_until == 0 => CLOSED
```
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `record_failure`
- Snippet (lines 51,66-67):
```text
    51     def record_failure(self, now: float, *, open_after: int = 5, open_for_seconds: int = 600) -> None:
    66         if self.failures >= open_after:
    67             self.open_until = now + open_for_seconds
```

Claim: half-open behavior is implemented and emits probe success/failure events.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `allow_request`
- Snippet (lines 40-44):
```text
    40         # HALF_OPEN
    41         if self._probe_allowed:
    42             self._probe_allowed = False # Consume token
    43             return True
    44         return False
```
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `probe events`
- Snippet (lines 303,348):
```text
   303                                     "event": "half_open_probe_success",
   348                                     "event": "half_open_probe_failure",
```

Claim: breaker state persistence to disk = IMPLICIT ONLY (in-memory object creation visible; explicit disk persistence for breaker state NOT FOUND).
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `SignalAgent.__init__`
- Snippet (line 48):
```text
    48         self.breakers = {m: CircuitBreaker() for m in self.config.models}
```

Claim: 503 handling is explicit.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `provider_unavailable log`
- Snippet (lines 328-333):
```text
   328                             "event": "provider_unavailable",
   329                             "provider_id": provider_id,
   330                             "model_id": model_id,
   331                             "breaker_key": model_key,
   332                             "http_code": 503,
```
Evidence:
- File path: `E:\signal_agent\app\providers\fail503_provider.py`
- Symbol: `Fail503Provider.call`
- Snippet (line 3):
```text
     3         raise RuntimeError("UNAVAILABLE (code 503): No capacity available")
```
## 6) TEST COVERAGE SNAPSHOT

Claim: total tests = 19 files; 91 `def test_` functions.
Evidence:
- File path: `COMMAND: tests count scan`
- Symbol: `stdout`
- Snippet (lines 1-2):
```text
     1 test_file_count=19
     2 test_function_count=91
```

Claim: skips = 8; xfails = 0.
Evidence:
- File path: `COMMAND: tests count scan`
- Symbol: `stdout`
- Snippet (lines 3-4):
```text
     3 skip_markers=8
     4 xfail_markers=0
```

Claim: skip reasons include `Pack file not found` and `Pillow not installed`.
Evidence:
- File path: `COMMAND: skip marker scan`
- Symbol: `stdout`
- Snippet (lines 1-4):
```text
     1 E:\signal_agent\tests\test_meme_offload.py:120:            self.skipTest("Pack file not found")
     2 E:\signal_agent\tests\test_meme_offload.py:135:            self.skipTest("Pack file not found")
     3 E:\signal_agent\tests\test_meme_offload.py:169:            self.skipTest("Pillow not installed")
     4 E:\signal_agent\tests\test_meme_offload.py:196:            self.skipTest("Pillow not installed")
```

Claim: xfail markers are NOT FOUND.
Evidence:
- File path: `COMMAND: xfail scan`
- Symbol: `stdout`
- Snippet:
```text
     1 NO_XFAIL_MARKERS
```

Claim: key areas covered include kernel/governor/capture/resilience.
Evidence (kernel):
- File path: `E:\signal_agent\tests\sim_stability.py`
- Symbol: `test_v_raw_phases`
- Snippet (lines 6-8):
```text
     6 def test_v_raw_phases():
     7     cfg = KernelConfig(window_seconds=60, tick_seconds=5)
     8     k = CoherenceKernel(cfg)
```
Evidence (governor):
- File path: `E:\signal_agent\tests\test_activation_governor.py`
- Symbol: `test_lock_blocks_unauthorized_activation`
- Snippet (lines 56-57):
```text
    56     assert decision["decision"] == "BLOCK"
    57     assert decision["reason"] == "scope_not_authorized_during_lock"
```
Evidence (capture):
- File path: `E:\signal_agent\tests\test_capture_layer.py`
- Symbol: `test_similar_docs_cluster`
- Snippet (lines 155-158):
```text
   155         result = promote_run(
   156             threshold=0.1,
   157             min_cluster_size=2,
   158             capture_dir=self.capture_dir,
```
Evidence (resilience):
- File path: `E:\signal_agent\tests\test_enforcement.py`
- Symbol: `test_failure_halt_panic`
- Snippet (lines 14-15):
```text
    14     def test_failure_halt_panic(self):
    15         """Test that FAILURE regime raises SystemHalt and writes panic log."""
```

## 7) DATA STATE SNAPSHOT

Claim: data directories and counts snapshot.
Evidence:
- File path: `COMMAND: data inventory scan`
- Symbol: `stdout`
- Snippet (lines 1-6):
```text
     1 data_dirs=capture,docs,gtm,intake,logs,social_offload,state
     2 raw_capture_count=1
     3 promoted_bundle_count=2
     4 spine_dirs=ai_stability_diagnostic,content_publishing,misc
     5 spine_dir_count=3
```

Claim: intake artifacts snapshot = 336 text files and 376 JSONL rows.
Evidence:
- File path: `COMMAND: data inventory scan`
- Symbol: `stdout`
- Snippet (lines 8-9):
```text
     8 intake_text_file_count=336
     9 intake_jsonl_line_count=376
```

Claim: quarantine path exists = no.
Evidence:
- File path: `COMMAND: data inventory scan`
- Symbol: `stdout`
- Snippet (line 7):
```text
     7 quarantine_exists=no
```

Claim: `data/social_offload` has `logs` and `outputs`.
Evidence:
- File path: `COMMAND: social_offload dirs`
- Symbol: `stdout`
- Snippet:
```text
     1 data/social_offload dirs=logs,outputs
```

Claim: decay relocates files; does not delete.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\decay.py`
- Symbol: `module docstring`
- Snippet (lines 4-6):
```text
     4 Moves expired files to data/capture/expired_stage1/ (Stage 1).
     5 Moves stage1 files to data/capture/expired_stage2/ (Stage 2) after purge_days.
     6 Never deletes.
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\decay.py`
- Symbol: `decay_run`
- Snippet (lines 168,195):
```text
   168                             shutil.move(str(rf), str(dest))
   195                         shutil.move(str(sf), str(dest))
```

## 8) CONFIGURATION SURFACE

Claim: config files found include `config/spine_router.yaml`; root `config.yaml` exists and currently contains `:Hq_dev`.
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\config`
- Symbol: `stdout`
- Snippet:
```text
     1 E:\signal_agent\config\spine_router.yaml
```
Evidence:
- File path: `E:\signal_agent\config.yaml`
- Symbol: `file content`
- Snippet:
```text
     1 :Hq_dev
```

Claim: active provider selection order is explicit in `AgentConfig.models`; provider map has one explicit high-tier mapping and default fallback.
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `AgentConfig.models`
- Snippet (line 24):
```text
    24     models: tuple[str, ...] = ("google:gemini-3-pro-high", "google:gemini-3-pro", "google:gemini-3-flash")
```
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `providers + default`
- Snippet (lines 53-57):
```text
    53         self.providers: Dict[str, Provider] = {
    54             "google:gemini-3-pro-high": Fail503Provider(),  # Simulate 503 on high tier
    55         }
    56         # Default fallback for others
    57         self._default_provider = StubProvider()
```

Claim: override hierarchy evidence.
Evidence (env > default for capture paths):
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_get_root`, `_get_capture_dir`
- Snippet (lines 54-57):
```text
    54     override = os.environ.get("SIGNAL_AGENT_ROOT")
    55     if override:
    56         return Path(override)
    57     return Path(__file__).resolve().parents[3]
```
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `_get_capture_dir`
- Snippet (lines 61-64):
```text
    61     override = os.environ.get("CAPTURE_DIR")
    62     if override:
    63         return Path(override)
    64     return _get_root() / "data" / "capture"
```
Evidence (arg > default config file):
- File path: `E:\signal_agent\app\hq\capture\router.py`
- Symbol: `_load_spine_config`
- Snippet (lines 87-88):
```text
    87     if config_path is None:
    88         config_path = _get_root() / "config" / "spine_router.yaml"
```
Evidence (CLI arg surface):
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `governor.review parser`
- Snippet (lines 197-202):
```text
   197         parser.add_argument("--allow", action="append", default=[])
   198         parser.add_argument("--watch-root", action="append", default=[])
   199         parser.add_argument("--primary-scope", default="capture_pipeline")
   200         parser.add_argument("--selection-rule", default="manual")
   201         parser.add_argument("--selection-score", type=float, default=1.0)
```
Evidence (function defaults):
- File path: `E:\signal_agent\app\governor\__init__.py`
- Symbol: `governor_review`
- Snippet (lines 99-100):
```text
    99     scopes = authorized_scopes or DEFAULT_AUTHORIZED_SCOPES
   100     roots = watch_roots or DEFAULT_WATCH_ROOTS
```

Claim: hard-coded secrets check result = no secret values found (env-var name references only).
Evidence:
- File path: `COMMAND: secret-pattern scan`
- Symbol: `stdout`
- Snippet (lines 7-8):
```text
     7 E:\signal_agent\app\hq\exporter.py:19:        sensitive_vars = ["GOOGLE_CREDENTIALS", "OPENAI_API_KEY", "SIGNAL_SECRET", "GMAIL_CREDENTIALS"]
     8 E:\signal_agent\app\hq\token_export.py:19:        sensitive_vars = ["GOOGLE_CREDENTIALS", "OPENAI_API_KEY", "SIGNAL_SECRET", "GMAIL_CREDENTIALS"]
```
Evidence:
- File path: `E:\signal_agent\app\hq\exporter.py`
- Symbol: `TokenExporter.export_bundle docstring`
- Snippet (lines 9-10):
```text
     9         Creates a REDACTED bundle of configuration/env state.
    10         NEVER exports actual secrets.
```
## 9) SYSTEM HALT FORENSICS

Claim: exact halt trigger is `snap.regime == "FAILURE"` in resilience path.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `call_with_resilience`
- Snippet (lines 156-158):
```text
   156         # 1. FAILURE -> HALT
   157         if snap.regime == "FAILURE":
   158             from app.audit.coherence_kernel import persist_panic_log
```

Claim: halt path persists panic log and then raises `SystemHalt`.
Evidence:
- File path: `E:\signal_agent\app\utils\resilience.py`
- Symbol: `call_with_resilience`
- Snippet (lines 166,176):
```text
   166             persist_panic_log(snap, request_id=working_request_id, events_summary=summary)
   176             raise SystemHalt()
```

Claim: panic log path and append logic are explicit.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `persist_panic_log`
- Snippet (lines 302-303):
```text
   302         path = Path("data/state/panic.log")
   303         path.parent.mkdir(parents=True, exist_ok=True)
```
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `persist_panic_log`
- Snippet (lines 317-318):
```text
   317         with path.open("a", encoding="utf-8") as f:
   318             f.write(json.dumps(record) + "\n")
```

Claim: current panic log file = NOT FOUND.
Evidence:
- File path: `COMMAND: Test-Path E:\signal_agent\data\state\panic.log`
- Symbol: `stdout`
- Snippet:
```text
     1 panic_log_exists=no
```

Claim: recovery mechanism in kernel is manual-reset-only FAILURE latch.
Evidence:
- File path: `E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `_update_regime`
- Snippet (lines 230-231):
```text
   230         if r == Regime.FAILURE:
   231             return Regime.FAILURE  # manual reset only
```

Claim: explicit regime reset API = NOT FOUND.
Evidence:
- File path: `COMMAND: rg -n "def .*reset|set_regime|clear_failure|recover|failure" E:\signal_agent\app\audit\coherence_kernel.py`
- Symbol: `stdout`
- Snippet:
```text
75:    failure_enter: float = 0.80
160:    def record_breaker_reset(self) -> None:
233:        if phi_risk >= self.cfg.failure_enter:
```

Claim: `emergency` path exists separately in policy engine and can return `EMERGENCY_OVERRIDE`.
Evidence:
- File path: `E:\signal_agent\app\utils\policy_engine.py`
- Symbol: `emergency gate`
- Snippet (lines 79-81):
```text
    79             if pack_scope == "EMERGENCY":
    80                 if not context.get("emergency_override_enabled", False):
    81                     continue
```
Evidence:
- File path: `E:\signal_agent\app\utils\policy_engine.py`
- Symbol: `EMERGENCY_OVERRIDE`
- Snippet (lines 142-146):
```text
   142     if emergency_allow:
   143         return EvalResult(
   144             decision="ALLOW",
   145             reason="EMERGENCY_OVERRIDE",
   146             matched_constraints=[],
```

## 10) LIMITATIONS

Claim: TODO and placeholder logic exists in agent pre-flight path.
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `generate preflight`
- Snippet (lines 104-108):
```text
   104         # TODO: Hydrate snapshot from real usage state (e.g. Redis/DB)
   105         # For now, minimal snapshot to check GLOBAL constants
   106         pre_flight_snapshot = {
   107             "metrics": {"session_cost_usd": 0.0}, # Placeholder
   108             "context": {"user_id": "test_user"}
```

Claim: simulated provider wiring and stub provider are present.
Evidence:
- File path: `E:\signal_agent\app\agent.py`
- Symbol: `provider wiring comment`
- Snippet (lines 51-54):
```text
    51         # Wiring providers (simulating configuration or dependency injection)
    52         # Mapping fully qualified keys to provider instances
    53         self.providers: Dict[str, Provider] = {
    54             "google:gemini-3-pro-high": Fail503Provider(),  # Simulate 503 on high tier
```
Evidence:
- File path: `E:\signal_agent\app\providers\stub_provider.py`
- Symbol: `StubProvider.call`
- Snippet (lines 1-3):
```text
     1 class StubProvider:
     2     def call(self, model: str, prompt: str) -> str:
     3         return f"[ok:{model}] {prompt[:60]}"
```

Claim: capture curate handoff is disabled.
Evidence:
- File path: `E:\signal_agent\app\hq\capture\promote.py`
- Symbol: `promote_run`
- Snippet (lines 479-482):
```text
   479         # Curate handoff (DISABLED for Capture Layer Invariant Compliance)
   480         # curated, curated_ref = _try_curate(bundle_path)
   481         curated = False
   482         curated_ref = None
```

Claim: curation wrapper stub uses `pass`.
Evidence:
- File path: `E:\signal_agent\app\hq\curation\brn_cmds.py`
- Symbol: `brn_curate_intake_downloads`
- Snippet (line 19):
```text
    19     pass # Managed via backfill for now
```

Claim: provider expansion is disabled by default and gated by pack predicate.
Evidence:
- File path: `E:\signal_agent\app\agents\meme_offload\meme_offload.py`
- Symbol: `_is_expansion_allowed docstring`
- Snippet (lines 132-135):
```text
   132     Default: disabled. Only activates if an ALLOW rule for
   133     'provider_expansion' evaluates to true.
   135     If the predicate is absent or evaluates to false → disabled.
```
Evidence:
- File path: `E:\signal_agent\constraints\packs\domain\content_meme\CONTENT_MEME_OFFLOAD_v1.yaml`
- Symbol: `MEME_ALLOW_PROVIDER_EXPANSION`
- Snippet (lines 99-104):
```text
    99     intent: "Gate optional LLM caption expansion (disabled by default)"
   100     rule_type: "ALLOW"
   103       risk_tier: "MEDIUM"
   104     predicate: "false"
```

Claim: placeholder literal exists in constraints.
Evidence:
- File path: `E:\signal_agent\constraints\packs\global_v1.yaml`
- Symbol: `disallowed_phrases`
- Snippet (line 6):
```text
     6   - "placeholder_text"
```

## NOT FOUND / IMPLICIT ONLY SUMMARY

- Remotes: NOT FOUND.
- Top-level package metadata (`pyproject.toml`, `setup.py`): NOT FOUND (replaced with `__init__.py` semantic version root).
- `__version__`/`VERSION=` symbols: FOUND.
- Kernel env/yaml/cli overrides: NOT FOUND.
- Kernel/resilience half-life/decay-rate constants: NOT FOUND.
- Breaker disk persistence: IMPLICIT ONLY.
- `data/quarantine`: NOT FOUND.
- `.env` files: NOT FOUND (true strictly, but environment variables `SIGNAL_AGENT_ROOT`, `CAPTURE_DIR` verified strictly read via `os.environ.get`).
- `xfail` markers: NOT FOUND.
- `data/state/panic.log`: NOT FOUND.
- Explicit FAILURE reset API: NOT FOUND.
- Cross-subsystem version precedence: IMPLICIT ONLY.

## Commands executed

```powershell
git -C E:\signal_agent rev-parse --abbrev-ref HEAD
git -C E:\signal_agent rev-parse HEAD
git -C E:\signal_agent remote -v
git -C E:\signal_agent status --porcelain=v1 -b
git -C E:\signal_agent tag --list
rg --files E:\signal_agent\app | rg coherence_kernel
rg --files E:\signal_agent\app | rg "activation_governor|governor"
rg --files E:\signal_agent\app\hq\capture -g "*.py"
rg --files E:\signal_agent\app\providers -g "*.py"
rg --files E:\signal_agent\app\utils -g "*.py" | rg "resilience|exceptions"
rg --files E:\signal_agent\tests -g "*.py"
rg -n "^\s*def test_" E:\signal_agent\tests -g "*.py"
rg -n "skipTest\(|@pytest\.mark\.skip|@unittest\.skip|@pytest\.mark\.xfail|xfail" E:\signal_agent\tests -g "*.py"
rg -n "__version__|^VERSION\s*=|^version\s*=" E:\signal_agent\app E:\signal_agent\config E:\signal_agent\tests -g "*.py" -g "*.yaml" -g "*.yml"
rg -n "SystemHalt|halt|panic|emergency|FAILURE|stable_enter|pressure_enter|unstable_enter|failure_enter|V_raw|V_report|phi1|phi2|phi3|phi4|phi5|sigmoid|K\s*=|enforcement_enabled|expires_at_utc|baseline_fingerprint|lock_active|_NON_MUTATING_SCOPES|drift_detected|scope_not_authorized_during_lock|min_cluster_size|spike_ratio|ratio\s*=|keyword_rate|domain_rate|open_after|open_for_seconds|HALF_OPEN|503|TODO|FIXME|placeholder|simulat|disable" E:\signal_agent\app E:\signal_agent\tests E:\signal_agent\constraints -g "*.py" -g "*.yaml" -g "*.yml"
rg -n "quarantine|delete|move|stage1|stage2|Never deletes" E:\signal_agent\app\hq\capture -g "*.py"
rg --files E:\signal_agent\config
rg --files E:\signal_agent -g ".env" -g ".env.*"
rg -n -g "*.py" -g "*.yaml" -g "*.yml" -g "*.env" -g "*.json" "(API_KEY|SECRET_KEY|PASSWORD|TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|-----BEGIN|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{20,})" E:\signal_agent\app E:\signal_agent\config E:\signal_agent\constraints E:\signal_agent\data E:\signal_agent\tests
rg -n "def .*reset|set_regime|clear_failure|recover|failure" E:\signal_agent\app\audit\coherence_kernel.py
```

## 6) TEST COVERAGE SNAPSHOT (Supplemental File List Evidence)

Claim: test file list (19 files) from `tests/` scan.
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\tests -g "*.py" | Sort-Object`
- Symbol: `stdout`
- Snippet (lines 1-5):
```text
     1 E:\signal_agent\tests\__init__.py
     2 E:\signal_agent\tests\conftest.py
     3 E:\signal_agent\tests\integration\test_social_offload_concurrency.py
     4 E:\signal_agent\tests\integration\test_social_offload_regression.py
     5 E:\signal_agent\tests\integration\verify_social_offload_contract.py
```
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\tests -g "*.py" | Sort-Object`
- Symbol: `stdout`
- Snippet (lines 6-10):
```text
     6 E:\signal_agent\tests\manual_reprojection_verification.py
     7 E:\signal_agent\tests\sim_stability.py
     8 E:\signal_agent\tests\test_activation_governor.py
     9 E:\signal_agent\tests\test_agent_resilience.py
    10 E:\signal_agent\tests\test_capture_adversarial.py
```
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\tests -g "*.py" | Sort-Object`
- Symbol: `stdout`
- Snippet (lines 11-15):
```text
    11 E:\signal_agent\tests\test_capture_falsification.py
    12 E:\signal_agent\tests\test_capture_layer.py
    13 E:\signal_agent\tests\test_dsl.py
    14 E:\signal_agent\tests\test_enforcement.py
    15 E:\signal_agent\tests\test_meme_offload.py
```
Evidence:
- File path: `COMMAND: rg --files E:\signal_agent\tests -g "*.py" | Sort-Object`
- Symbol: `stdout`
- Snippet (lines 16-19):
```text
    16 E:\signal_agent\tests\test_pack_hash.py
    17 E:\signal_agent\tests\test_policy_engine.py
    18 E:\signal_agent\tests\test_reprojection.py
    19 E:\signal_agent\tests\test_reprojection_v2.py
```

## Commands executed (final)

```powershell
git -C E:\signal_agent rev-parse --abbrev-ref HEAD
git -C E:\signal_agent rev-parse HEAD
git -C E:\signal_agent remote -v
git -C E:\signal_agent status --porcelain=v1 -b
git -C E:\signal_agent tag --list
rg --files E:\signal_agent\app | rg coherence_kernel
rg --files E:\signal_agent\app | rg "activation_governor|governor"
rg --files E:\signal_agent\app\hq\capture -g "*.py"
rg --files E:\signal_agent\app\providers -g "*.py"
rg --files E:\signal_agent\app\utils -g "*.py" | rg "resilience|exceptions"
rg --files E:\signal_agent\tests -g "*.py" | Sort-Object
rg -n "^\s*def test_" E:\signal_agent\tests -g "*.py"
rg -n "skipTest\(|@pytest\.mark\.skip|@unittest\.skip|@pytest\.mark\.xfail|xfail" E:\signal_agent\tests -g "*.py"
rg -n "__version__|^VERSION\s*=|^version\s*=" E:\signal_agent\app E:\signal_agent\config E:\signal_agent\tests -g "*.py" -g "*.yaml" -g "*.yml"
rg -n "SystemHalt|halt|panic|emergency|FAILURE|stable_enter|pressure_enter|unstable_enter|failure_enter|V_raw|V_report|phi1|phi2|phi3|phi4|phi5|sigmoid|K\s*=|enforcement_enabled|expires_at_utc|baseline_fingerprint|lock_active|_NON_MUTATING_SCOPES|drift_detected|scope_not_authorized_during_lock|min_cluster_size|spike_ratio|ratio\s*=|keyword_rate|domain_rate|open_after|open_for_seconds|HALF_OPEN|503|TODO|FIXME|placeholder|simulat|disable" E:\signal_agent\app E:\signal_agent\tests E:\signal_agent\constraints -g "*.py" -g "*.yaml" -g "*.yml"
rg -n "quarantine|delete|move|stage1|stage2|Never deletes" E:\signal_agent\app\hq\capture -g "*.py"
rg --files E:\signal_agent\config
rg --files E:\signal_agent -g ".env" -g ".env.*"
rg -n -g "*.py" -g "*.yaml" -g "*.yml" -g "*.env" -g "*.json" "(API_KEY|SECRET_KEY|PASSWORD|TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|-----BEGIN|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{20,})" E:\signal_agent\app E:\signal_agent\config E:\signal_agent\constraints E:\signal_agent\data E:\signal_agent\tests
rg -n "def .*reset|set_regime|clear_failure|recover|failure" E:\signal_agent\app\audit\coherence_kernel.py
```


