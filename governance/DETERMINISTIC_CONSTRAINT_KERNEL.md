# Deterministic Constraint Kernel — SIGNAL_AGENT_CONSTRAINT_KERNEL_V1

----------------------------------------------------------------
1. KERNEL_ID
----------------------------------------------------------------
`SIGNAL_AGENT_CONSTRAINT_KERNEL_V1`

----------------------------------------------------------------
2. ACTION_MODEL (SIGNAL_AGENT_ID_PROTOCOL_V1)
----------------------------------------------------------------
All identifiers MUST be derivable from deterministic inputs. `UUIDv4` is FORBIDDEN.

**ID Generation**:
1.  **trace_id**: `UUIDv5(NS_TRACE, trace_seed)`
    -   `trace_seed`: `SHA256(ingress_event_bytes)` or stable user seed.
    -   `NS_TRACE`: Fixed UUID Namespace Constant.
2.  **action_id**: `UUIDv5(NS_ACTION, action_fingerprint)`
    -   `action_fingerprint`: Canonical JSON of `{ trace_id, actor_id, name, category, parameters }`.

**Schema**:
```json
{
  "action_id": "UUIDv5",
  "trace_id": "UUIDv5",
  "actor_id": "String",
  "name": "String",
  "category": "String",
  "parameters": "Map<String, Any>",
  "cost_estimate": { "usd": "Decimal", "tokens": "Int", "latency_ms": "Int" }
}
```

----------------------------------------------------------------
3. POLICY_MODEL
----------------------------------------------------------------
The `EffectivePolicy` is the immutable runtime configuration.

```json
{
  "policy_id": "String",
  "policy_hash": "SHA256 (Canonical)",
  "strict_mode": "Boolean",
  "default_decision": "ALLOW | BLOCK",
  "constraints": "List<ConstraintRule>",
  "tool_surface": "Set<String> (Sorted)",
  "schema_version": "1.0.0",
  "kernel_id": "SIGNAL_AGENT_CONSTRAINT_KERNEL_V1"
}
```

**Context Model**:
-   `current_time`: Unix ms (Must be injected/deterministic).
-   `approvals`: Map<`approval_key`, Status>.
-   `budget_state`: AtomicBudgetStore Ref.
-   `safe_mode_active`: Boolean (Runtime only).

----------------------------------------------------------------
4. CONSTRAINT_RULE_SCHEMA (SIGNAL_AGENT_RULE_SCHEMA_V1)
----------------------------------------------------------------

**Canonical Structures**:

**ENUM Source**: `CORE | DOMAIN | TASK | SESSION | EMERGENCY`
**ENUM RuleType**: `DENY | REQUIRE_APPROVAL | LIMIT`

**STRUCT ConstraintRule**:
```yaml
id: string                          # Unique, stable. Recommended: /^[A-Z0-9_]+$/
source: Source                      # CORE/DOMAIN/TASK/SESSION/EMERGENCY
priority: int                       # 0 = highest precedence
scope: Scope                        # Fast prefilter; affects specificity()
predicate: DSLNode                  # Safe, depth-limited logic
rule_type: RuleType                 # DENY | REQUIRE_APPROVAL | LIMIT
message: string                     # Operator-facing reason
limit: LimitSpec?                   # Required iff rule_type == LIMIT
params: map<string, any>?           # Immutable at runtime; mutable via override
valid_until_ms: int?                # Optional expiry
audit_event: string                 # e.g. "POLICY_DENY"
```

**STRUCT Scope**:
```yaml
tool: string                        # exact ("fs:write") or "*" wildcard
action_fields: map<string, any>     # Prefilter matches against Action fields only.
```

**STRUCT LimitSpec**:
```yaml
limit_key: string                   # e.g. "session_cost_usd"
limit_value: float                  # Cap
window: string                      # e.g. "per_session"
```

**STRUCT DSLNode**:
```yaml
type: "expression"
oneOf:
  - { op: "AND" | "OR", args: [DSLNode, DSLNode] }
  - { op: "NOT", arg: DSLNode }
  - { op: "EQ" | "GT" | "LT" | "IN" | "MATCHES", left: Accessor, right: Accessor }
```

**STRUCT Accessor**:
```yaml
type: "FIELD" | "VALUE"
val: any                            # FIELD: string path, VALUE: literal
```

----------------------------------------------------------------
5. MERGE_ENGINE
----------------------------------------------------------------

```python
def merge_policies(layers: List[PolicyLayer], overrides: List[Override]) -> EffectivePolicy:
    """
    1. Stack Layers (Core -> Domain -> Task). Detect Duplicates.
    2. Apply Overrides (Mutation only).
    3. Sort Constraints: (Priority ASC, Specificity DESC, ID ASC).
    4. Compute Canonical Hash.
    """
    merged = []
    seen = set()
    
    for layer in layers:
        for rule in layer.constraints:
            if rule.id in seen: raise MergeError(f"Duplicate {rule.id}")
            merged.append(rule)
            seen.add(rule.id)
            
    for ov in overrides:
        validate_override(ov)
        target = find_rule(merged, ov.target_id)
        if target: apply_mutation(target, ov)
        
    merged.sort(key=lambda r: (r.priority, -specificity(r), r.id))
    
    policy = EffectivePolicy(
        constraints=merged,
        tool_surface=sorted(union(layers.surfaces)),
        ...
    )
    policy.hash = compute_policy_hash(policy)
    return policy
```

----------------------------------------------------------------
6. RUNTIME_EVALUATION (SIGNAL_AGENT_DECISION_LATTICE_V1)
----------------------------------------------------------------

**Dominance Lattice**: `DENY > REQUIRE_APPROVAL > LIMIT > ALLOW`

**Core Logic**:
```python
def evaluate(action, policy, context):
    try:
        # A) Safe/Strict Mode Checks (Fail-Closed)
        if context.safe_mode_active and action.unsafe: return BLOCK("SAFE_MODE")
        if policy.strict_mode and action.name not in policy.tool_surface: return BLOCK("UNKNOWN_ACTION")

        # B) Budget Reservation (Idempotent)
        res_id = sha256(f"{action.trace_id}:{action.action_id}:0") # attempt_index=0
        if not context.budget.reserve(res_id, action.cost): return BLOCK("BUDGET_EXCEEDED")

        # C) Evaluator Loop (Lattice Logic)
        decision = ALLOW
        pending_approvals = []
        caps = {} # limit_key -> min_cap

        for rule in policy.constraints:
             if not matches_scope(rule.scope, action): continue
             if not eval_dsl(rule.predicate, action, context): continue

             # 1. DENY (Short-Circuit)
             if rule.type == DENY:
                  context.budget.refund(res_id, action.cost)
                  return BLOCK(rule.id)

             # 2. REQUIRE_APPROVAL (Accumulate)
             if rule.type == REQUIRE_APPROVAL:
                  key = sha256(f"{policy.hash}:{action.action_id}:{rule.id}")
                  if context.approvals.get(key) != APPROVED:
                       pending_approvals.append(rule.id)
                       decision = REQUEST_APPROVAL 

             # 3. LIMIT (Aggregate)
             if rule.type == LIMIT:
                  current = caps.get(rule.limit_key, INF)
                  caps[rule.limit_key] = min(current, rule.limit_value)

        # D) Post-Loop Limit Check
        for key, cap in caps.items():
             used = context.get_usage(key)
             if used > cap:
                  context.budget.refund(res_id, action.cost)
                  return BLOCK("LIMIT_EXCEEDED", key)

        # E) Final Decision
        if pending_approvals:
             context.budget.refund(res_id, action.cost)
             return REQUEST_APPROVAL(pending_approvals)

        return ALLOW

    except Exception:
        return BLOCK("KERNEL_CRASH")
```

**Helper: matches_scope(scope, action)**:
1.  **Tool Match**: `scope.tool == "*"` OR `scope.tool == action.name`. Else False.
2.  **Field Match**: For each `(path, expected)` in `scope.action_fields`: `dot_get(action, path) == expected`. Else False.

**Helper: eval_dsl(node, action, context)**:
-   **Depth Check**: If depth > `MAX_DSL_DEPTH` -> Throw RecursionError (Fail Closed).
-   **Field Resolution**:
    -   Prefix `context.`: Read from safe view (time, safe_mode, approvals).
    -   Prefix `action.` or None: Read from `action`.
-   **Matches**: Enforce `REGEX_MAX_LEN` & `REGEX_TIMEOUT_MS`.
-   **Exception Handling**: Any error treats node as False (Fail Closed at caller level if critical, or skip rule).

----------------------------------------------------------------
7. SPECIFICITY_FUNCTION
----------------------------------------------------------------
**Formula**:
`specificity(scope) = (100 if scope.tool != "*" else 0) + (len(scope.action_fields) * 10)`

-   Exact tool match grants base score of 100.
-   Each explicit field refilter adds 10 points.
-   Higher score evaluates earlier (for same Priority).

----------------------------------------------------------------
8. OVERRIDE_SYSTEM
----------------------------------------------------------------
-   **Target**: Non-Core Only.
-   **Mutations**: Predicate, Params, Message, Expiry only.
-   **Signature**: Required (`signer_id`, `sig`).
-   **Application**: Before Hashing.

----------------------------------------------------------------
9. BUDGET_RESERVATION_PROTOCOL
----------------------------------------------------------------
**Concurrency**: CAS / Atomic.
**ID**: `reservation_id = SHA256(trace_id + ":" + action_id + ":" + attempt_index)`
**Flow**: Check -> Reserve -> Log -> Refund (if Block/Error).

----------------------------------------------------------------
10. POLICY_HASH_PROTOCOL (SIGNAL_AGENT_POLICY_HASH_V1)
----------------------------------------------------------------

**Definition**:
`policy_hash = SHA256( CanonicalJSON(EffectivePolicy) )`

**Canonicalization Rules**:
1.  **Keys**: Sorted recursively (Alphabetical).
2.  **Lists**: Preserve order unless Set (sorted lexicographically).
    -   `tool_surface`: Sorted.
    -   `constraints`: Sorted by (Priority, Specificity, ID).
3.  **Encoding**: UTF-8.
4.  **Separators**: `,` and `:` (No whitespace).

**Verification**:
On Load: `Compute(Policy) == StoredHash`.
Mismatch -> **SAFE MODE** (Strict Block).

----------------------------------------------------------------
11. SAFE_MODE_STATE_MACHINE
----------------------------------------------------------------
-   **Triggers**: Hash Mismatch, Merge Error, Schema Error, Kernel Crash.
-   **Behavior**: Block `WRITE`, `NETWORK`, `EXEC`, `ADMIN`. Allow `READ` (if Strict Mode permits).
-   **Reset**: Explicit Admin Command.

----------------------------------------------------------------
12. AUDIT_LOG_SCHEMA
----------------------------------------------------------------
```json
{
  "timestamp": "ISO8601",
  "policy_hash": "SHA256",
  "event_type": "DECISION",
  "payload": { "decision": "BLOCK", "rule_id": "..." }
}
```

----------------------------------------------------------------
13. FAILURE_CONDITIONS
----------------------------------------------------------------
-   **Recursion**: > 3.
-   **Budget**: Lock Timeout > 5ms.
-   **internal**: Exception -> BLOCK.

----------------------------------------------------------------
14. ENUMS + CONSTANTS
----------------------------------------------------------------
-   `NS_TRACE`: `UUID(...)`
-   `NS_ACTION`: `UUID(...)`
-   `MAX_DSL_DEPTH`: 3
-   `REGEX_TIMEOUT_MS`: 1
-   `REGEX_MAX_LEN`: 1000
-   `FAIL_CLOSED`: true
-   `LATTICE`: `DENY > APPROVAL > LIMIT > ALLOW`

----------------------------------------------------------------
15. MINIMAL CONFORMANCE TESTS
----------------------------------------------------------------
1.  **Lattice Dominance**: Deny(P0) > Approval(P1).
2.  **Appoval Stickiness**: Approval(P0) + Allow(P1) -> RequestApproval.
3.  **Limit Aggregation**: Limit(10) + Limit(5) -> Block at 6.
4.  **Hash Verification**: Mismatch enters Safe Mode.
5.  **ID Determinism**: `Replay(Action)` yields identical `action_id`.
6.  **Specificity Sort**: `tool:fs` (100) > `tool:*` (0).
