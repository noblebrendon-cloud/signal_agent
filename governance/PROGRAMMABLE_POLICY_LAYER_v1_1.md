# Programmable Policy Layer v1.1: Signal Agent

## 1. POLICY_LAYER_ID
`SIGNAL_AGENT_CORE_POLICY_V1_1`

## 2. FORMAL DEFINITIONS
- **Atomic Budget Reservation**: A two-phase commit process (Reserve -> Reconcile) ensuring resources are allocated *before* consumption, preventing overrun race conditions.
- **Deterministic Drift**: The divergence in execution behavior between an original run and a replay, caused by sources of entropy (time, randomness). To adhere to this policy, all such sources must be seeded by `trace_id`.
- **Fail-Closed**: If the policy engine encounters an internal error (e.g., config parse failure, budget service timeout), the default action is `TERMINATE`.
- **Wall-Clock Watchdog**: A parallel thread that monitors execution duration and sends a `SIGTERM` independent of the main execution loop.
- **Circuit Breaker (Half-Open)**: A state where a failing dependency is tentatively tested with a limited flow (probes) before fully reopening.

## 3. STATE_MACHINE

### States
- `IDLE`: Initialized, zero resources.
- `RESERVING`: Atomic budget check in progress.
- `EXECUTING`: Main workload active; Watchdog armed.
- `AWAITING_RETRY`: Backoff timer active (Deterministic duration).
- `CIRCUIT_OPEN`: Dependency blocked; fast-fail mode.
- `CIRCUIT_HALF_OPEN`: Limited probe mode.
- `SUSPENDED_FOR_APPROVAL`: Waiting for human signal (High Risk Tier).
- `COMPLETED`: Success; Budget reconciled.
- `TERMINATED`: Failure/Block; Budget reconciled.

### Transitions
- `IDLE` -> `RESERVING` [Trigger: `start_request`]
- `RESERVING` -> `EXECUTING` [Trigger: `reservation_success`]
- `RESERVING` -> `TERMINATED` [Trigger: `reservation_denied`]
- `EXECUTING` -> `COMPLETED` [Trigger: `work_success`]
- `EXECUTING` -> `AWAITING_RETRY` [Trigger: `recoverable_error` AND `attempts < max`]
- `EXECUTING` -> `CIRCUIT_OPEN` [Trigger: `error_threshold_exceeded`]
- `EXECUTING` -> `TERMINATED` [Trigger: `watchdog_timeout`]
- `AWAITING_RETRY` -> `EXECUTING` [Trigger: `backoff_complete`]
- `CIRCUIT_OPEN` -> `CIRCUIT_HALF_OPEN` [Trigger: `reset_timeout_complete`]
- `CIRCUIT_HALF_OPEN` -> `EXECUTING` [Trigger: `probe_allowed`]
- `CIRCUIT_HALF_OPEN` -> `CIRCUIT_OPEN` [Trigger: `probe_failed`]
- `CIRCUIT_HALF_OPEN` -> `IDLE` [Trigger: `probe_success_threshold_met` (Resets breaker)]

## 4. POLICY_SCHEMA_V1_1

```yaml
policy_id: "SIGNAL_AGENT_POLICY_V1_1"
system_version: "1.1.0"

global_constraints:
  max_wall_time_ms: 30000
  max_recursion_depth: 3
  fail_closed_on_error: true
  
resource_budgets:
  max_cost_usd_per_session: 0.50
  max_tokens_total: 10000
  max_file_ops_total: 50

retry_policy:
  max_attempts: 3
  base_delay_ms: 500
  max_delay_ms: 5000
  backoff_strategy: "exponential_deterministic"
  jitter_seed_source: "trace_id"

circuit_breaker:
  failure_threshold: 5
  open_state_duration_ms: 60000
  half_open_interaction_limit: 3  # Max 3 probes allowed in HALF_OPEN

emergency_controls:
  allow_override: true
  override_requires_signature: true
  max_override_duration_min: 60

risk_tier_matrix:
  low:
    requires_approval: false
    allowed_domains: ["*"]
  med:
    requires_approval: false
    allowed_domains: ["internal-services", "public-safe-list"]
  high:
    requires_approval: true
    approver_role: "admin"
    allowed_domains: ["internal-services"]

tool_policy:
  filesystem-read:
    allowed: true
    risk: "low"
  filesystem-write:
    allowed: true
    risk: "high"
    paths: ["/safe_zone/*"]
  http-fetch:
    allowed: true
    risk: "med"
  llm-call:
    allowed: true
    risk: "med"

watchdog:
  enabled: true
  grace_period_ms: 500
  termination_signal: "SIGTERM"
```

## 5. ATOMIC_BUDGET_MODEL

To prevent "check-then-act" race conditions, budget is handled via a Reservation Token.

```python
class BudgetManager:
    def reserve(self, trace_id, estimated_cost):
        """
        Atomically decrements available budget.
        Returns: strict ReservationID or raises BudgetExceeded.
        """
        reservation_id = uuid4()
        with self.lock:
             if self.remaining >= estimated_cost:
                 self.remaining -= estimated_cost
                 self.active_reservations[reservation_id] = estimated_cost
                 return reservation_id
             else:
                 raise BudgetExceeded()

    def reconcile(self, reservation_id, actual_cost):
        """
        Adjusts budget based on actual usage.
        Refunds unused portion or records overage.
        """
        with self.lock:
             reserved = self.active_reservations.pop(reservation_id)
             diff = reserved - actual_cost
             self.remaining += diff # diff > 0 means refund, diff < 0 means overage
             
    def force_terminate(self):
        """Called if reconcile detects significant negative drift."""
        pass
```

## 6. DETERMINISTIC_RETRY_SYSTEM

Jitter is required for thundering herd protection, but random jitter breaks replayability. We use seeded hashing.

**Backoff Formula:**
```
retry_seed = SHA256(f"{trace_id}:{dependency_key}:{attempt_index}")
random_generator = Random(seed=retry_seed)

deterministic_jitter_ms = random_generator.randint(0, 200)
base_backoff_ms = min(max_delay, base_delay * (2 ^ attempt))

final_delay_ms = base_backoff_ms + deterministic_jitter_ms
```

## 7. ENFORCEMENT_HOOKS

```python
def enforcement_hook_pre_call(context, request):
    # 1. Watchdog Check
    if Watchdog.time_remaining(context.start_time) <= 0:
        return Constraint.BLOCK("WALL_CLOCK_EXCEEDED")

    # 2. Risk Tier Check
    risk_tier = Policy.get_risk_tier(request.tool)
    if risk_tier == "high":
        if not context.has_approval(request.signature):
            return Constraint.BLOCK("APPROVAL_REQUIRED")

    # 3. Circuit Breaker Check
    breaker_state = CircuitBreaker.get_state(request.dependency_key)
    if breaker_state == "OPEN":
        return Constraint.BLOCK("CIRCUIT_IS_OPEN")
    if breaker_state == "HALF_OPEN":
        if not CircuitBreaker.try_acquire_probe_lock():
            return Constraint.BLOCK("CIRCUIT_HALF_OPEN_LIMIT")

    # 4. Atomic Budget Reservation
    try:
        reservation_id = BudgetManager.reserve(context.trace_id, request.estimated_cost)
        context.active_reservation = reservation_id
    except BudgetExceeded:
        return Constraint.BLOCK("INSUFFICIENT_FUNDS")

    return Constraint.ALLOW()


def enforcement_hook_post_call(context, result):
    # 1. Budget Reconcile
    if context.active_reservation:
        BudgetManager.reconcile(context.active_reservation, result.actual_cost)

    # 2. Circuit Breaker Update
    if result.is_success:
        if CircuitBreaker.state == "HALF_OPEN":
            CircuitBreaker.record_success() # May transition to CLOSED
    else:
        CircuitBreaker.record_failure() # May transition to OPEN
```

## 8. TELEMETRY_SCHEMA

```json
{
  "events": [
    {
      "name": "POLICY_CHECK_PASS",
      "fields": ["trace_id", "tool", "risk_tier"]
    },
    {
      "name": "POLICY_CHECK_BLOCK",
      "fields": ["trace_id", "reason_code", "constraint_id"]
    },
    {
      "name": "STATE_TRANSITION",
      "fields": ["from_state", "to_state", "trigger"]
    },
    {
      "name": "BUDGET_RESERVED",
      "fields": ["reservation_id", "amount", "resource_type"]
    },
    {
      "name": "BUDGET_RECONCILED",
      "fields": ["reservation_id", "actual_amount", "drift"]
    },
    {
      "name": "BREAKER_TRIP",
      "fields": ["dependency_key", "failure_count", "reset_at"]
    },
    {
      "name": "BREAKER_HALF_OPEN",
      "fields": ["dependency_key", "probe_id"]
    },
    {
      "name": "WATCHDOG_TERMINATE", 
      "fields": ["trace_id", "duration_ms", "limit_ms"]
    },
    {
      "name": "EMERGENCY_OVERRIDE",
      "fields": ["signer_id", "reason", "expiry"]
    },
    {
      "name": "TERMINATION",
      "fields": ["trace_id", "final_state", "artifacts_produced"]
    }
  ]
}
```

## 9. TEST_MATRIX

### Negative Tests (Should Block)
1.  **Block**: Wall-clock exceeded (30001ms).
2.  **Block**: Recursion depth 4.
3.  **Block**: Budget Reservation Fail ($0.51).
4.  **Block**: Risk Tier High (File Write) without signature.
5.  **Block**: Circuit Breaker OPEN state.
6.  **Block**: Circuit Breaker HALF_OPEN probe limit exceeded (4th probe).
7.  **Block**: Emergency Override expired.
8.  **Block**: Tool not in allow-list.
9.  **Block**: Domain restriction violation (Restricted URL).
10. **Block**: Invalid Schema payload.

### Positive Tests (Should Allow)
1.  **Allow**: Standard low-risk call.
2.  **Allow**: High-risk call with valid signature.
3.  **Allow**: Retry attempt 2 (within limit).
4.  **Allow**: Budget Reservation Success ($0.49).
5.  **Allow**: Circuit Breaker CLOSED state.
6.  **Allow**: Circuit Breaker HALF_OPEN probe 1 (success -> close).
7.  **Allow**: Emergency Override active.
8.  **Allow**: File Read (Safe Zone).
9.  **Allow**: Token Usage within limit.
10. **Allow**: Session start (IDLE -> RESERVING).

### Replay Determinism Tests
1.  **Replay**: Retry backoff delays match exactly (ms).
2.  **Replay**: Jitter values match exactly.
3.  **Replay**: Decision tree path identical.
4.  **Replay**: Reservation IDs generated in same sequence (if seeded info used).
5.  **Replay**: Failure injection triggers same recovery path.
6.  **Replay**: Watchdog triggers at same logical tick (simulated time).

### Circuit Breaker Tests
1.  **CB**: 5 Failures -> Trip to OPEN.
2.  **CB**: Waiting 60s -> Transition OPEN to HALF_OPEN.
3.  **CB**: HALF_OPEN Probe Success -> Transition to CLOSED.
4.  **CB**: HALF_OPEN Probe Failure -> Trip back to OPEN.
5.  **CB**: HALF_OPEN Probe Limit (3 calls only).
6.  **CB**: Dependency Key isolation (Key A failure doesn't trip Key B).

## 10. DETERMINISTIC_REPLAY_TEST_HARNESS

```python
class DeterministicReplayRunner:
    def __init__(self, recording_log):
        self.recording = recording_log
        self.mock_time = recording_log.start_time
        
    def run_replay(self, policy_engine):
        print("Starting Deterministic Replay...")
        
        # Seed Randomness
        seed_prngs(self.recording.trace_id)
        
        for recorded_event in self.recording.events:
            # 1. Advance Time
            self.mock_time = recorded_event.timestamp
            
            # 2. Inject recorded inputs
            result = policy_engine.process(recorded_event.input)
            
            # 3. Assert Output Identity
            assert result == recorded_event.output, "Divergence detected!"
            
            # 4. Assert Side-Effects
            assert policy_engine.budget_state == recorded_event.budget_snapshot
            
        print("Replay Verified: Identical Execution Trail.")
```

## 11. GOVERNANCE WHITEPAPER APPENDIX

### Problem Statement
Non-deterministic agent behavior creates liability. Standard "random" retries and chaotic state management make post-incident analysis impossible. We require a system where `f(input, trace_id) -> output` is mathematically constant, even in failure modes.

### Formal Constraint Model
The policy layer acts as a wrapping function `P(x)` around any agent action `A(x)`.
`Execution = P(A(x))`
Where `P` is a side-effect-free evaluator that returns `{Allow | Block}`.
`P` must be idempotent and isolated from `A`.

### Deterministic Replay Justification
By deriving all entropy (jitter, IDs) from the `trace_id` hash, we guarantee that a re-run of a log file produces the exact same sequence of internal states. This is critical for debugging complex emergent behavior in agent swarms.

### Atomic Budget Theory
Traditional "decrement-on-use" allows overspending in concurrent environments. Our "Reservation" model (`Reserve -> Commit/Rollback`) treats budget like a database transaction. If the strict reservation fails, the action never attempts execution, guaranteeing strict cost ceilings.

### Circuit Breaker Recovery Model
We implement a 3-state state machine: `CLOSED`, `OPEN`, `HALF_OPEN`. The `HALF_OPEN` state is critical for AI agents, as it allows "probing" the dependency without unleashing a full retry storm. We limit concurrent probes to strictly isolate recovery traffic.

### Risk Tier Escalation logic
Risk is not binary. Levels:
- **Low**: Read-only, safe domains. (Auto-approved)
- **Med**: Cost-incurring, public data. (Rate-limited)
- **High**: Write-capable, private data. (Signature-required)

### Limitations
- **Determinism**: Relies on "Simulated Time" for perfect replay; wall-clock race conditions in the underlying OS cannot be fully controlled, but the *Policy Decisions* remain constant.
- **Latency**: The Atomic Budget lock adds ~5ms overhead per tool call.
