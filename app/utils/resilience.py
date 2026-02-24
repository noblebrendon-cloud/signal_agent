from __future__ import annotations

import hashlib
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, TYPE_CHECKING
from app.utils.exceptions import SystemHalt, LoadShed

if TYPE_CHECKING:
    from app.audit.coherence_kernel import CoherenceKernel, Regime, Priority


@dataclass
class CircuitBreaker:
    failures: int = 0
    open_until: float = 0.0  # using timestamp (time.time())
    # State tracking: 
    # If open_until > now => OPEN
    # If open_until <= now and open_until > 0 => HALF_OPEN (allows 1 probe)
    # If open_until == 0 => CLOSED
    
    _probe_allowed: bool = False

    def get_state(self, now: float) -> str:
        if self.open_until == 0.0:
            return "CLOSED"
        if now < self.open_until:
            return "OPEN"
        return "HALF_OPEN"
    
    def allow_request(self, now: float) -> bool:
        state = self.get_state(now)
        if state == "CLOSED":
            return True
        if state == "OPEN":
            return False
        # HALF_OPEN
        if self._probe_allowed:
            self._probe_allowed = False # Consume token
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self._probe_allowed = False

    def record_failure(self, now: float, *, open_after: int = 5, open_for_seconds: int = 600) -> None:
        if self.get_state(now) == "HALF_OPEN":
            # Probe failed, re-open immediately
            self.open_until = now + open_for_seconds
            self._probe_allowed = True # Reset for next expiration? No, wait until expiration again.
             # Wait, typical half-open logic: fail -> open again.
             # When open timer expires, we permit ONE probe.
             # If that probe fails, we go back to OPEN.
             # So we must set _probe_allowed = True ONLY when transitioning from OPEN -> HALF_OPEN.
             # Actually, logic in allow_request handles "transition".
             # If we are effectively HALF-OPEN, we consumed the token.
             # If we fail, we go back to OPEN.
            pass
        
        self.failures += 1
        if self.failures >= open_after:
            self.open_until = now + open_for_seconds
            # When we eventually wake up (now > open_until), we want 1 probe.
            self._probe_allowed = True


class AdaptiveSemaphore:
    def __init__(self, limit: int = 100):
        self._limit = limit
        self._active = 0

    def set_limit(self, limit: int) -> None:
        self._limit = limit

    def acquire(self) -> bool:
        if self._active >= self._limit:
            return False
        self._active += 1
        return True

    def release(self) -> None:
        if self._active > 0:
            self._active -= 1

_CONCURRENCY_GOVERNOR = AdaptiveSemaphore(limit=100)


def is_capacity_unavailable(exc: Exception) -> bool:
    """
    Detect provider-side capacity outages / transport unreachable.
    Keep it intentionally narrow (only retry what is likely transient).
    """
    msg = str(exc).lower()
    return (
        ("unavailable" in msg and "503" in msg)
        or ("no capacity available" in msg)
        or ("model api cannot be reached" in msg)
        or ("code 503" in msg)
    )


def call_with_resilience(
    call_model: Callable[[str], Any],
    models: Iterable[str],
    *,
    request_id: Optional[str] = None,
    max_attempts_per_model: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 4.0,
    multiplier: float = 2.0,
    breakers: Optional[dict[str, CircuitBreaker]] = None,
    log: Optional[Callable[[dict], None]] = None,
    time_fn: Optional[Callable[[], float]] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    kernel: Optional['CoherenceKernel'] = None,
    priority: Optional['Priority'] = None,
) -> Any:
    """
    Retries ONLY on transient capacity outages (503 / UNAVAILABLE).
    Falls back across model list.
    Circuit breakers block calls for a window after repeated failures.
    Deterministic backoff with jitter seeded by request_id.
    
    Coherence Kernel Enforcement:
    - FAILURE: SystemHalt
    - UNSTABLE: LoadShed (if priority < HIGH), Throttled
    - PRESSURE: Backoff Scaled
    """
    # 1. Initialization
    if time_fn is None:
        time_fn = time.monotonic
    if sleep_fn is None:
        sleep_fn = time.sleep

    call_chain_id = uuid.uuid4().hex
    working_request_id = request_id if request_id else call_chain_id
    last_exc: Optional[Exception] = None
    
    start_ts = time_fn()
    total_attempts = 0
    final_provider: Optional[str] = None
    terminal_state = "fatal_error"

    # Enforce Coherence Stability (Pre-Loop)
    regime_val = "STABLE"
    if kernel:
        # A) Kernel Snapshot & Regime Logic
        snap = kernel.snapshot()
        regime_val = snap.regime.value
        
        # 1. FAILURE -> HALT
        if snap.regime == "FAILURE":
            from app.audit.coherence_kernel import persist_panic_log
            # Summary of simple stats for log
            summary = {
                "phi1_violations": snap.phi1,
                "phi2_drift": snap.phi2,
                "phi3_breakers": snap.phi3,
                "phi4_retries": snap.phi4,
            }
            persist_panic_log(snap, request_id=working_request_id, events_summary=summary)
            if log:
                log({
                    "event": "coherence_collapse_halt",
                    "phi_risk": snap.phi_risk,
                    "E": snap.E,
                    "V_raw": getattr(snap, "V_raw", -1.0),
                    "V_report": getattr(snap, "V_report", -1.0),
                    "regime": "FAILURE"
                })
            raise SystemHalt()

        # 2. Priority Load Shedding
        # Priority default LOW if not provided
        prio_str = priority.value if priority else "LOW"
        if snap.regime == "UNSTABLE":
            if prio_str in ("LOW", "NORMAL"):
                if log:
                    log({
                        "event": "load_shed",
                        "reason": "unstable_regime_shed_low_priority",
                        "priority": prio_str,
                        "phi_risk": snap.phi_risk
                    })
                raise LoadShed()
        
        # 3. Adaptive Concurrency Limit
        # Base N=100 (hardcoded for now, could be config)
        base_N = 100
        limit = base_N
        if snap.regime == "PRESSURE":
            limit = int(base_N * 0.7)
        elif snap.regime == "UNSTABLE":
            limit = int(base_N * 0.3)
        elif snap.regime == "FAILURE":
            limit = 0
            
        _CONCURRENCY_GOVERNOR.set_limit(limit)

        # 4. Breaker Ratio Update
        if breakers:
            total_b = len(breakers)
            if total_b > 0:
                now_check = time_fn()
                open_count = sum(1 for b in breakers.values() if b.get_state(now_check) == "OPEN")
                ratio = float(open_count) / float(total_b)
                kernel.update_tool_instability_ratio(ratio)
        else:
             kernel.update_tool_instability_ratio(0.0)

    try:
        for model_key in models:
            # User requires provider_id:model_id keying. 
            parts = model_key.split(":", 1)
            provider_id = parts[0] if len(parts) > 1 else "unknown"
            model_id = parts[1] if len(parts) > 1 else model_key
            
            breaker = breakers.get(model_key) if breakers else None

            # Check circuit state
            if breaker:
                now = time_fn()
                state = breaker.get_state(now)
                
                if not breaker.allow_request(now):
                    # BLOCKED (OPEN or probe consumed)
                    if log:
                        log({
                            "event_v": 2,
                            "event": "circuit_short_circuit" if state == "OPEN" else "circuit_opened", 
                            "provider_id": provider_id,
                            "model_id": model_id,
                            "breaker_key": model_key,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    
                    # Fallback immediately
                    if log:
                         log({
                             "event_v": 2,
                             "event": "fallback_selected",
                             "provider_id": provider_id, # Source provider
                             "model_id": model_id,
                             "breaker_key": model_key,
                             "timestamp": datetime.now(timezone.utc).isoformat(),
                         })
                    continue
                
                # If we are allowing request in HALF_OPEN, that logic handled inside allow_request (consumes token)
                is_probe = (state == "HALF_OPEN")

            # Attempt loop
            for attempt_index in range(max_attempts_per_model):
                # Concurrency Check inside loop? Or outside? Outside seems better per call.
                # But we retry. Let's do it per physical call attempt to capture 'inflight'.
                if kernel:
                    if not _CONCURRENCY_GOVERNOR.acquire():
                         # Throttled
                         if log:
                             log({"event": "concurrency_throttled", "regime": regime_val})
                         # Treat as transient failure? Or fast fail?
                         # Fast fail this attempt/model, maybe backoff and retry?
                         # For now, let's treat as simple failure to acquire -> backoff
                         time.sleep(0.1) # Brief yield
                         continue 

                attempt_number = attempt_index + 1
                t0 = time_fn()

                if kernel:
                    kernel.record_request(retries=attempt_index)
                    # We do NOT re-check snapshot here to avoid thrashing mid-loop 
                    # consistent with "Decision per request" philosophy, 
                    # BUT strictly speaking we might want to check if we drifted into FAILURE mid-retry.
                    # For performance, we stick to the pre-loop check.
                
                try:
                    if log:
                        log({
                            "event_v": 2,
                            "event": "retry_attempt" if attempt_number > 1 else "call_start",
                            "provider_id": provider_id,
                            "model_id": model_id,
                            "breaker_key": model_key,
                            "attempt_index": attempt_number,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        
                    total_attempts += 1 # Increment actual invocation count
                    
                    out = call_model(model_key)
                    
                    if breaker:
                        if breaker.get_state(t0) == "HALF_OPEN": # Was probe
                             if log:
                                log({
                                    "event_v": 2,
                                    "event": "half_open_probe_success",
                                    "provider_id": provider_id,
                                    "model_id": model_id,
                                    "breaker_key": model_key,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                        breaker.record_success()
                        if kernel:
                            kernel.record_breaker_reset()
                    
                    terminal_state = "success"
                    final_provider = provider_id
                    return out

                except Exception as exc:
                    last_exc = exc

                    if not is_capacity_unavailable(exc):
                        # Non-retryable
                        raise
                    
                    # 503 / Unavailable
                    if log:
                        log({
                            "event_v": 2,
                            "event": "provider_unavailable",
                            "provider_id": provider_id,
                            "model_id": model_id,
                            "breaker_key": model_key,
                            "http_code": 503,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "error": str(exc),
                            "legacy_event": "MODEL_CALL_FAIL_503"
                        })

                    if breaker:
                        now_fail = time_fn()
                        was_half_open = (breaker.get_state(now_fail) == "HALF_OPEN") or (breaker.open_until > 0 and now_fail > breaker.open_until)
                        
                        breaker.record_failure(now_fail, open_after=5, open_for_seconds=600)
                        
                        if was_half_open:
                             if log:
                                 log({
                                    "event_v": 2,
                                    "event": "half_open_probe_failure",
                                    "provider_id": provider_id,
                                    "model_id": model_id,
                                    "breaker_key": model_key,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                 })

                        if breaker.get_state(now_fail) == "OPEN":
                            if log:
                                log({
                                    "event_v": 2,
                                    "event": "circuit_opened",
                                    "provider_id": provider_id,
                                    "model_id": model_id,
                                    "breaker_key": model_key,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "legacy_event": "CIRCUIT_OPENED"
                                })
                            break # Stop retrying this model, move to fallback

                    if attempt_number < max_attempts_per_model:
                        # Calculate deterministic backoff
                        base_backoff = min(max_delay_s, base_delay_s * (multiplier ** attempt_index))
                        
                        seed_str = f"{provider_id}:{model_id}:{working_request_id}:{attempt_index}"
                        
                        digest = hashlib.sha256(seed_str.encode()).digest()
                        seed_int = int.from_bytes(digest[:8], "big")
                        rng = random.Random(seed_int)
                        
                        jitter_factor = 0.5 + 0.5 * rng.random()
                        # Kernel Regime Scaling
                        scale = 1.0
                        if kernel:
                            if regime_val == "PRESSURE":
                                scale = 1.5
                            elif regime_val == "UNSTABLE":
                                scale = 2.5
                        
                        sleep_time = min(max_delay_s, base_backoff * jitter_factor * scale)

                        print(f"DEBUG_RES: seed_str='{seed_str}' jitter={jitter_factor} regime={regime_val} scale={scale} sleep={sleep_time}")

                        if log and scale > 1.0:
                             log({
                                 "event": "kernel_backoff_scale",
                                 "regime": regime_val,
                                 "base": min(max_delay_s, base_backoff * jitter_factor),
                                 "scaled": sleep_time
                             })

                        if log:
                            log({
                                "event_v": 2,
                                "event": "retry_attempt", 
                                "provider_id": provider_id,
                                "model_id": model_id,
                                "breaker_key": model_key,
                                "attempt_index": attempt_number,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        sleep_fn(sleep_time)
                finally:
                    if kernel:
                        _CONCURRENCY_GOVERNOR.release()
            
            # End of attempts for this model
            if log:
                 log({
                     "event_v": 2,
                     "event": "fallback_selected",
                     "provider_id": provider_id,
                     "model_id": model_id,
                     "breaker_key": model_key,
                     "timestamp": datetime.now(timezone.utc).isoformat(),
                     "reason": "attempts_exhausted",
                     "legacy_event": "MODEL_FALLBACK_NEXT"
                 })

        terminal_state = "exhausted"
        raise RuntimeError(f"All model fallbacks exhausted. Last error: {last_exc}")

    finally:
        if log:
            log({
                "event_v": 2,
                "event": "call_chain_completed",
                "call_chain_id": call_chain_id,
                "request_id": working_request_id,
                "start_ts": start_ts,
                "duration_ms": (time_fn() - start_ts) * 1000,
                "total_attempts": total_attempts,
                "final_provider": final_provider,
                "terminal_state": terminal_state
            })
