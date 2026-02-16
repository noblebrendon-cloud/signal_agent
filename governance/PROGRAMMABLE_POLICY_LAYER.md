# Programmable Policy Layer: Signal Agent

## 1. POLICY_LAYER_ID
`SIGNAL_AGENT_CORE_POLICY_V1`

## 2. POLICY_GOALS
- **Deterministic Containment**: Enforce strict, non-negotiable hard caps on all execution dimensions (time, cost, tokens, depth).
- **Failure Isolation**: Prevent cascading failures by isolating dependency states and enforcing circuit breakers.
- **Auditability**: Guarantee that every state transition and enforcement action is logged with a unique trace ID and reason code.
- **Resource Protection**: block any execution that exceeds pre-calculated budget or risk thresholds before side-effects occur.

## 3. DEFINITIONS
- **Execution Budget**: The aggregate set of resources (time, tokens, dollars, steps) allocated to a single logical request.
- **Dependency Key**: A unique identifier `provider:model` (e.g., `openai:gpt-4`) used to shard circuit breaker states.
- **Risk Tier**: A classification level (Low, Med, High) determining the strictness of the policy (e.g., High tier requires human-in-the-loop for file writes).
- **Tool Surface**: The allow-list of capabilities available to the agent for a given state.
- **Terminal State**: A final state (COMPLETED, FAILED, TIMED_OUT) from which no further transitions can occur.

## 4. STATE_MACHINE

### States
- `IDLE`: System is initialized, waiting for input. No resources consumed.
- `VALIDATING`: Policy layer checks request parameters against static allow-lists and budget availability.
- `EXECUTING`: Active processing. Resources are being actively consumed.
- `AWAITING_RETRY`: A transient failure occurred; waiting for backoff timer.
- `FAILOVER`: Primary dependency failed; system is attempting valid secondary path.
- `COMPLETED`: Execution finished successfully within bounds.
- `FAILED`: Execution terminated due to error, policy violation, or budget exhaustion.

### Transitions
- `IDLE` -> `VALIDATING` [Trigger: `start_request`]
- `VALIDATING` -> `EXECUTING` [Trigger: `policy_pass`]
- `VALIDATING` -> `FAILED` [Trigger: `policy_violation`]
- `EXECUTING` -> `COMPLETED` [Trigger: `success`]
- `EXECUTING` -> `AWAITING_RETRY` [Trigger: `recoverable_error` AND `attempts < max_attempts`]
- `EXECUTING` -> `FAILOVER` [Trigger: `provider_failure` AND `failover_enabled`]
- `EXECUTING` -> `FAILED` [Trigger: `hard_error` OR `budget_exceeded`]
- `AWAITING_RETRY` -> `EXECUTING` [Trigger: `backoff_complete`]
- `AWAITING_RETRY` -> `FAILED` [Trigger: `max_retries_exceeded`]
- `FAILOVER` -> `EXECUTING` [Trigger: `failover_ready`]

## 5. POLICY_SCHEMA

```yaml
policy_id: "SIGNAL_AGENT_CORE_POLICY_V1"
system_name: "Signal Agent"
risk_tier: "high"

global_constraints:
  max_wall_time_ms: 30000
  max_cost_usd: 0.50
  max_recursion_depth: 3
  allowed_domains:
    - "ai_execution"
    - "content_generation"
    - "stability_diagnostic"

resource_budgets:
  default:
    max_tokens_total: 8000
    max_tool_calls: 5
    max_retries_total: 3
  high_compute:
    max_tokens_total: 32000
    max_tool_calls: 15
    max_retries_total: 5

tool_policy:
  filesystem-write:
    allowed: true
    requires_approval: true
    path_restrictions: ["/safe_zone/*", "!/system/*"]
  filesystem-read:
    allowed: true
    path_restrictions: ["/data/*"]
  http-fetch:
    allowed: true
    domain_allowlist: ["api.openai.com", "api.anthropic.com", "internal-services"]
  implementation_exec:
    allowed: false  # strict ban on arbitrary code execution

circuit_breaker:
  failure_threshold: 5
  reset_timeout_ms: 60000
  open_state_behavior: "fast_fail"
```

## 6. ENFORCEMENT_HOOKS

```python
def enforcement_hook_pre_call(context, request):
    """
    Runs before any action is taken.
    Returns: (bool allowed, string reason)
    """
    # 1. Check Global State
    if SystemState.is_shutdown():
        return False, "SYSTEM_SHUTDOWN"

    # 2. Check Input Constraints
    if not Policy.validate_schema(request.payload):
        return False, "INVALID_SCHEMA"

    # 3. Check Budget Availability
    projected_cost = CostEstimator.estimate(request)
    if (context.current_spend + projected_cost) > Policy.max_cost_usd:
        return False, "INSUFFICIENT_BUDGET"

    # 4. Check Circuit Breaker
    dependency_key = f"{request.provider}:{request.model}"
    if CircuitBreaker.is_open(dependency_key):
        return False, "BREAKER_OPEN"

    # 5. Check Tool Permissions
    if request.tool_name and not Policy.is_tool_allowed(request.tool_name, context.user_role):
        return False, "TOOL_PERMISSION_DENIED"

    return True, "AUTHORIZED"


def enforcement_hook_post_call(context, result):
    """
    Runs after an action completes.
    Updates state and budgets.
    """
    # 1. Update Budgets
    context.current_spend += result.cost
    context.token_usage += result.tokens
    context.request_count += 1

    # 2. Check for Termination Conditions
    if context.current_spend >= Policy.max_cost_usd:
        return Signal.TERMINATE("COST_LIMIT_REACHED")
    
    # 3. Update Circuit Breaker Stats
    dependency_key = f"{context.provider}:{context.model}"
    if result.is_error:
        CircuitBreaker.record_failure(dependency_key)
    else:
        CircuitBreaker.record_success(dependency_key)


def enforcement_hook_on_error(context, error):
    """
    Determines next state on error.
    """
    if error.is_retryable and context.attempts < Policy.max_retries_total:
         return State.TRANSITION("AWAITING_RETRY")
    
    if Policy.failover_enabled and context.can_failover:
         return State.TRANSITION("FAILOVER")

    return State.TRANSITION("FAILED")
```

## 7. AUDIT_EVENTS

All events must emit a JSON log entry.

**Base Schema:**
```json
{
  "timestamp": "ISO8601",
  "policy_id": "SIGNAL_AGENT_CORE_POLICY_V1",
  "trace_id": "uuid",
  "event_type": "enum",
  "payload": {}
}
```

**Event Types:**

| Event Type | Trigger | Required Payload Fields |
| :--- | :--- | :--- |
| `POLICY_CHECK_PASS` | `pre_call` succeeds | `tool_name`, `provider`, `params_hash` |
| `POLICY_CHECK_BLOCK` | `pre_call` fails | `violation_code`, `limit_value`, `requested_value` |
| `STATE_TRANSITION` | Machine changes state | `from_state`, `to_state`, `trigger_event` |
| `BUDGET_UPDATE` | Resource consumed | `cost_delta`, `tokens_delta`, `remaining_budget` |
| `BREAKER_TRIP` | Circuit breaker opens | `dependency_key`, `failure_count`, `reset_time` |
| `TERMINATION` | System stops | `final_state`, `reason`, `total_runtime_ms` |

## 8. TEST_MATRIX

### Should Block (Negative Tests)
| Case ID | Scenario | Expected Outcome | Reason |
| :--- | :--- | :--- | :--- |
| `BLK-01` | Request implies usage > $0.50 | `POLICY_VIOLATION` | Exceeds `max_cost_usd` limit. |
| `BLK-02` | File write to `/system/config.ini` | `POLICY_VIOLATION` | Path matches `!/system/*` exclusion rule. |
| `BLK-03` | Recursion depth reaches 4 | `TERMINATION` | Exceeds `max_recursion_depth` (3). |
| `BLK-04` | Tool call `exec_shell` | `POLICY_VIOLATION` | Tool not in allow-list. |
| `BLK-05` | Call to `api.unknown-vendor.com` | `POLICY_VIOLATION` | Domain not in `http-fetch` allow-list. |
| `BLK-06` | Retry attempt #4 | `STATE_FAILED` | Exceeds `max_retries_total` (3). |

### Should Allow (Positive Tests)
| Case ID | Scenario | Expected Outcome | Reason |
| :--- | :--- | :--- | :--- |
| `ALW-01` | Request cost $0.05, depth 1 | `EXECUTING` | Within all budgets and constraints. |
| `ALW-02` | File read `/data/logs/error.log` | `EXECUTING` | Path matches `/data/*` allow-list. |
| `ALW-03` | Retry attempt #2 after 503 error | `AWAITING_RETRY` | Transient error within retry limit. |
| `ALW-04` | File write `/safe_zone/report.txt` | `EXECUTING` | Path allowed, user approval simulated. |
| `ALW-05` | HTTP fetch `api.openai.com` | `EXECUTING` | Domain on allow-list. |
| `ALW-06` | Max usage check (Tokens=7999) | `EXECUTING` | Strictly < `max_tokens_total` (8000). |

## 9. INTEGRATION_NOTES

1.  **Mounting**: Instantiate `PolicyEngine` at the root of the agent control loop.
2.  **Wrappers**: Wrap all side-effecting tools (FileSystem, HTTP, LLM) with the `enforcement_hook_pre_call` decorator.
3.  **State Persistence**: The ID of the policy engine instance must persist across async steps.
4.  **Fail-Close**: If the Policy Layer throws an internal exception, the entire agent process must terminate immediately (Fail-Safe), preventing unmonitored execution.
