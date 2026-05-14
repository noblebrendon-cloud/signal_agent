# Governed Continuity Engine

**Status**: evidence-mapped from live repo
**Classification**: each section is marked **[IMPLEMENTED]**, **[EMERGING]**, or **[FUTURE]**

---

## 1. System Identity

**[IMPLEMENTED]**

Signal Agent is a deterministic transformation engine. All observable outputs result from:

```
Stateₙ → constrained, validated transformation → Stateₙ₊₁
```

No direct mutation is permitted. The governing invariant is:

> **No state change without validated, observable, governed transition.**

This is codified in `GOVERNANCE_KERNEL.md` and enforced by the transition gate at `app/hq/governance/transition_gate.py`.

---

## 2. Transition Gate

**[IMPLEMENTED]**

The transition gate is the single canonical validation path for all state-changing operations.

| Component | Path | Role |
|---|---|---|
| Gate validator | `app/hq/governance/transition_gate.py` (17,970 bytes) | State machine lookup, forbidden transition check, TTL enforcement, policy evaluation |
| State machine graph | `config/state_machine.yaml` (7,834 bytes) | Canonical state graph with gates, forbidden transitions, TTL |
| Lane registry | `config/lanes.yaml` (5,443 bytes) | Lane definitions, policies, surfaces |

### Lifecycle Flow

```
captured → normalized → classified → constrained → promoted → routed → transformed → compiled → staged → emitted → audited
```

Control states: `held`, `failed`, `rejected`, `aborted`

### Enforcement Evidence

| Test | What it proves |
|---|---|
| `test_governance_unification.py` | Gate rejects unauthorized transitions |
| `test_operator_write_denial.py` | Write-mode denied without gate approval |
| `test_casts_closure.py` | Lifecycle closure — all states reach terminal or are time-bound |
| `tests/security/test_transition_bypass.py` | Bypass attempts are blocked |

---

## 3. Append-Only Observability

**[IMPLEMENTED]**

All mutations produce traceable output. The canonical write primitive is:

```python
app.utils.io_contract.append_jsonl_atomic(path, record)
```

This function provides:
- File locking (cross-platform: `msvcrt` on Windows, `fcntl` on Linux)
- `os.fsync` after every write
- Rollback-on-failure (truncate to pre-write position on error)
- Atomic rename for non-append writes (`atomic_write_text`)

### Hash-Chained Records

The retention subsystem extends this with hash-chained records:

```python
app.retention.jsonl_store.append_record(path, record)
```

Each record includes:
- `prev_hash`: SHA-256 hash of the previous record (chain link)
- `record_hash`: SHA-256 hash of the current record (including `prev_hash`)
- `recorded_at`: UTC timestamp

This creates a tamper-evident append-only ledger where any retroactive modification breaks the hash chain.

### Canonical Ledgers

See `SIGNAL_AGENT_SYSTEM_MAP.md §3` for the complete ledger inventory. Key ledgers:

| Ledger | Entries | Write authority |
|---|---|---|
| `data/state/transition_gate_events.jsonl` | 708,991 bytes | `transition_gate.emit_transition_event()` |
| `data/operator/runs/operator_runs.jsonl` | Operator runs | `OperatorRuntime._append_ledger_entry()` |
| `data/state/witness/witness_daily.jsonl` | Daily witness | `signal_agent/health/daily_check.py` |
| `data/state/contacts.jsonl` | Retention contacts | `app/retention/jsonl_store.py` |

---

## 4. Declared Mutation Contract

**[IMPLEMENTED]**

Every tool declares its read and write targets in `config/operator/tools.yaml`. Pre-dispatch enforcement prevents tools with non-empty `writes` from executing outside `mode: "write"` workflows.

Post-dispatch verification classifies behavior:

| Classification | Meaning |
|---|---|
| `observed_as_declared` | Tool wrote to declared paths |
| `declared_without_observation` | Tool declared writes but none observed |
| `no_effect_observed` | No filesystem changes detected |
| `undeclared_mutation` | **Violation** — wrote to undeclared path |
| `consistent_read_only` | Read-only tool, no mutations |

### Evidence

| Test | What it proves |
|---|---|
| `test_operator_write_contract.py` (35,298 bytes) | Mutating tool in non-write workflow → hard stop |
| `test_operator_write_intent_contract.py` | Tool declarations match behavior |
| `test_runtime_authority_invariants.py` | Authority paths verified |

---

## 5. Fail-Closed Default

**[IMPLEMENTED]**

If validation cannot be proven, the operation is rejected. No inference. No partial execution.

| Enforcement point | Mechanism |
|---|---|
| `shared/authority.py` | Default: `allowed = False`, `blocking_reason = "insufficient_authority"` |
| Operator runtime | Plan status ≠ `ready` → `unsupported` or `error` |
| Context assembly | Any exception → `EMPTY_CONTEXT` |
| Transition gate | Unknown current state → `allowed: False` |
| Write contract | Tool declares writes in non-write workflow → `contract_violation` |

---

## 6. Deterministic Transformation

**[IMPLEMENTED]**

All outputs are reproducible from identical inputs. No randomness in canonical paths.

| Mechanism | Evidence |
|---|---|
| SHA-256 run IDs | `signal_agent/operator/runtime.py:72-74` |
| SHA-256 transaction IDs | `signal_agent/operator/runtime.py:802-805` |
| Frozen dataclasses | `@dataclass(frozen=True)` on `ToolExecution`, `OperatorRunResult`, `ParsedIntent`, `ContextBundle` |
| Stable JSON serialization | `sort_keys=True, ensure_ascii=False` |
| No `uuid4()` in canonical path | Verified; all resolved per `GOVERNANCE_KERNEL.md §5` |

---

## 7. Daily Witness Node

**[IMPLEMENTED]**

The daily witness node is a 925-line structured health check that produces operator-readable reports.

| Component | Path |
|---|---|
| Main module | `signal_agent/health/daily_check.py` |
| Witness artifacts | `data/state/witness/` |
| Witness ledger | `data/state/witness/witness_daily.jsonl` |

### 5-Stage Check

| Stage | What it checks |
|---|---|
| `git_state` | Branch, revision, dirty file count |
| `verification` | Required authority paths exist; invariant checker passes |
| `targeted_tests` | Bounded pytest execution of governance-critical tests |
| `ledger_validation` | All canonical JSONL ledgers parse without errors |
| `runtime_health` | Reconciliation, coherence failures, blocked transitions |

### Status Classification

```
healthy → no hard failures or known drift warnings
degraded → review required, not emergency
failed → hard failure; intervene before trusting automation
unverified → visibility incomplete; rerun or inspect
```

### Safety Boundaries

The witness node is explicitly prohibited from:
- auto-commit, auto-push, auto-merge
- autonomous refactor
- unrestricted agent execution
- automatic repair
- production-state mutation
- external delivery

---

## 8. Coherence Kernel

**[IMPLEMENTED]** — lives in audit module, not in governance kernel boundary

The coherence kernel (`app/audit/coherence_kernel.py`, 324 lines) implements a quantitative risk scoring system:

| Signal | Metric | Range |
|---|---|---|
| Φ₁ | Constraint violations (windowed) | [0, 1] |
| Φ₂ | Context drift distance | [0, 1] |
| Φ₃ | Tool instability (breaker ratio) | [0, 1] |
| Φ₄ | Retry rate (windowed) | [0, 1] |
| Φ₅ | Staleness since last breaker reset | [0, 1] |

Aggregation: weighted average + worst-case blend → `Φ_risk` → `Coherence = 1 - Φ_risk`

### Regime Classification (hysteresis-based)

```
STABLE → PRESSURE → UNSTABLE → FAILURE
```

FAILURE requires manual reset. Hysteresis thresholds prevent oscillation between regimes.

> **Note:** This kernel operates as an audit/observation tool. It does not gate transitions or block execution. It is not inside the governance kernel boundary defined in `GOVERNANCE_KERNEL.md §4.1`.

---

## 9. Retention Continuity

**[IMPLEMENTED]**

The retention subsystem provides relationship continuity through governed contact lifecycle management:

```
add-contact → evaluate_transition → build_contact_snapshot → plan_dispatch → reconcile
```

All transitions are validated against a state machine (`suppressed`, `aware`, `subscribed`) with sticky suppression rules.

Key safety boundaries:
- Hash-chained records prevent undetected tampering
- Dispatch planning is local-only (no external delivery)
- Authorization requires explicit operator decision
- `external_actions_allowed: false` at every stage

---

## 10. Reconciliation

**[IMPLEMENTED]**

Multiple reconciliation paths exist:

| Reconciliation | Path | Scope |
|---|---|---|
| Artifact reconciliation | `shared/reconcile.py` | Registry vs. filesystem consistency |
| Retention reconciliation | `app/retention/reconcile.py` | Ledger integrity across contacts, events, transitions, dispatch |
| Runtime health | `shared/health.py` | Aggregated system health from events, coherence, transitions |
| Appointment reconciliation | `app/retention/appointments/` | Appointment lifecycle integrity |

---

## 11. Governance Design Specs (Conceptual Only)

**[FUTURE]** — no runtime enforcement

| Spec | Path | Relationship |
|---|---|---|
| Deterministic Constraint Engine | `governance/DETERMINISTIC_CONSTRAINT_ENGINE.md` | Would replace hardcoded policy validators in transition gate |
| Programmable Policy Layer | `governance/PROGRAMMABLE_POLICY_LAYER_v1_2.md` | Would add budget enforcement, circuit breakers, watchdogs |
| AI Execution Containment | `governance/AI_EXECUTION_CONTAINMENT_LAYER_v1.md` | Would add execution budgets, dependency isolation |
| Domain Constraint Packs | `governance/DOMAIN_CONSTRAINT_PACKS.md` | Would generalize domain-specific validation |

> Per `GOVERNANCE_KERNEL.md §8`: these require explicit phase transition to EXECUTION or EXPANSION. Not authorized under current CONSOLIDATION phase.
