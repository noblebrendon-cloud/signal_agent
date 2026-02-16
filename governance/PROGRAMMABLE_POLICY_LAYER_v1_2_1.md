# Programmable Policy Layer v1.2.1

## 1. Formal Definitions

The Programmable Policy Layer (PPL) enforces deterministic constraints on agent behavior through a rigorous evaluation pipeline.

### 1.1 Core Models

**Constraint Rule** ($R$): A tuple $(id, scope, type, trigger, predicate, enforcement)$.
- **Scope**: `GLOBAL` | `DOMAIN` | `TASK` | `SESSION` | `EMERGENCY`
- **Type**: `DENY` | `LIMIT` | `REQUIRE_APPROVAL` | `ALLOW`
- **Trigger**: Filter condition based on `capability_id` or `risk_tier`.
- **Predicate**: DSL expression evaluating to `True` (violation/match) or `False`.

**Policy State** ($S_t$): The evaluation context at time $t$.
$$ S_t = \{ A_t, \Sigma_t, C_t \} $$
- $A_t$: Action proposed (Method, Args).
- $\Sigma_t$: System Snapshot (Metrics, Quotas, History).
- $C_t$: Context (User, Session, Emergency Flags).

**Evaluation Function** ($Eval$):
$$ Eval(S_t, \mathbb{P}) \to \{ \text{Decision}, \text{Reason}, \text{Effects} \} $$
Where $\mathbb{P}$ is the set of active Constraint Packs.

---

## 2. Policy Resolution State Machine

The PPL operates as a deterministic finite state machine (DFSM) for every action proposal.

### State Transitions

1.  **M1.1: Pack Activation**
    - Input: Context $C_t$, Registered Packs $\mathbb{P}_{all}$
    - Logic: Filter $\mathbb{P}_{active} = \{ p \in \mathbb{P}_{all} \mid p.\text{activation}(C_t) \text{ is True} \}$
    - Order: Sort by Scope Priority (GLOBAL > DOMAIN > ... > EMERGENCY).

2.  **M2.0: Rule Filtering**
    - Input: Action $A_t$, Active Packs $\mathbb{P}_{active}$
    - Logic: Filter rules where $R.trigger(A_t)$ matches.

3.  **M3.0: Predicate Evaluation**
    - Input: Filtered Rules, Snapshot $\Sigma_t$
    - Logic: Evaluate DSL $R.predicate(A_t, \Sigma_t)$.
    - **Fail-Closed**: Any DSL error results in `DENY`.

4.  **M4.0: Conflict Resolution (Lattice)**
    - **DENY** dominates all.
    - **EMERGENCY ALLOW** overrides DENY (if enabled).
    - **LIMIT** aggregates by `min(limit)`.
    - **REQUIRE_APPROVAL** checks if approval token exists.

5.  **M5.0: Enforcement**
    - Output: `EvalResult`.
    - Side Effects: Audit Log, Telemetry, Circuit Breaker State Update.

---

## 3. Resilience & Determinism Protocols

### 3.1 Entropy Sealing
To ensure reproducibility, all stochastic operations must be seeded contextually.
- **PRNG Seed**: $H( \text{RootSeed} || \text{TraceID} || \text{StepIndex} )$
- **Jitter**: Deterministic additive delay $\delta = (H(\text{RetryID}) \mod 1000) / 1000$.

### 3.2 Circuit Breaker (Verified)
- **State**: `CLOSED` (Normal) -> `OPEN` (Fail Fast) -> `HALF_OPEN` (Probe).
- **Trigger**: K consecutive failures or error rate > Threshold.
- **Reset**: Time-based or manual intervention.
- **Persistence**: State must be serializable to support process restarts.

### 3.3 Atomic Budgeting
- **Check-and-Reserve**: Budget must be checked and *tentatively reserved* before action execution.
- **Commit/Rollback**:
    - Success -> Commit reservation.
    - Failure -> Rollback (release) reservation.
- **Concurrency**: Optimistic locking or serialized access for budget counters.

---

## 4. Telemetry & Verification

### 4.1 Audit Schema
Every policy evaluation emits a structured log event:
```json
{
  "event_id": "uuid",
  "timestamp": "iso8601",
  "type": "POLICY_EVAL",
  "data": {
    "action_type": "...",
    "decision": "DENY",
    "reason": "LIMIT_EXCEEDED",
    "violating_rules": ["rule_id_1"],
    "effective_limits": {"cost": 5.0}
  },
  "context_hash": "sha256(S_t)"
}
```

### 4.2 Replay Harness
A verification tool must exist to:
1.  Load a sequence of Audit Logs.
2.  Re-construct $S_t$ (State) and $\mathbb{P}$ (Packs).
3.  Re-run $Eval(S_t, \mathbb{P})$.
4.  Assert $Output_{replay} == Output_{original}$.

---

## 5. Implementation Status

### Completed
- [x] **Policy Resolution Engine** (`app/utils/policy_engine.py`)
- [x] **Strict DSL Evaluator** (`app/utils/dsl.py`)
- [x] **Reprojection Integration** (`app/utils/reprojection.py`)
- [x] **Circuit Breaker** (`app/utils/resilience.py`)

### Pending
- [ ] **Entropy Sealing Integration** (in `app/agent.py`)
- [ ] **Atomic Budget Hooks** (in `app/agent.py` or `policy_engine.py`)
- [ ] **Telemetry Event Sourcing** (Standardized Logger)
