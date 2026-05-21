# State Machine

Status: canonical Path 2 state graph
Last updated: 2026-03-14

## Canonical State Graph

Nominal flow:

`captured -> normalized -> classified -> constrained -> promoted -> routed -> transformed -> compiled -> staged -> emitted -> audited`

Control states:

- `held`
- `rejected`
- `failed`
- `aborted`

This graph is canonical for Path 2 even where runtime enforcement is still partial. The committed foundation is the canonical graph in `config/state_machine.yaml`, the transition validator in `app/hq/governance/transition_gate.py`, its lane and policy inputs, and direct transition-gate tests. Other state integrations are dependent hardening work so later modules have one authority to target.

## State Definitions

| State | Meaning | Terminal | Recoverable |
| --- | --- | --- | --- |
| `captured` | The system has persisted an inbound signal or source input and recorded it in an intake or capture surface. | No | Yes |
| `normalized` | The signal has been converted into canonical text or structure suitable for downstream logic. | No | Yes |
| `classified` | The object has an explicit routing or processing class. | No | Yes |
| `constrained` | Governance checks, locks, and policy conditions have been evaluated for the next transition. | No | Yes |
| `promoted` | One or more inputs have been grouped into a routable bundle. | No | Yes |
| `routed` | The bundle or governed object has been assigned to a lane/spine destination. | No | Yes |
| `transformed` | A lane-specific transform has produced a derivative governed output. | No | Yes |
| `compiled` | One or more transformed outputs have been assembled into a package or durable deliverable set. | No | Yes |
| `staged` | The compiled or transformed output is ready for emission and has required packaging support metadata. | No | Yes |
| `emitted` | The staged output has been delivered to its intended output surface. | No | Yes |
| `audited` | The resulting run or object has enough evidence to verify lineage and outcome. | Yes | No |
| `held` | Progress is paused pending policy release, review, missing prerequisites, or manual decision. | No | Yes |
| `rejected` | Governance denied continuation. Work must restart as a new run or new object if retried. | Yes | No |
| `failed` | Execution could not continue because of an operational or integrity error, but recovery is possible. | No | Yes |
| `aborted` | Execution was intentionally terminated by an operator or control path. | Yes | No |

## Allowed Transitions

| From | To | Gate | Notes |
| --- | --- | --- | --- |
| `captured` | `normalized` | `intake_policy` | Required when the lane expects canonicalized text or structured payloads. |
| `normalized` | `classified` | `intake_policy` | Classification requires normalized payloads or equivalent structured input. |
| `classified` | `constrained` | governance gate | Route and action eligibility are checked here. |
| `constrained` | `promoted` | `promotion_policy` | Promotion should only advance after policy conditions are satisfied. |
| `promoted` | `routed` | `routing_policy` | Routing must produce a logged lane/spine destination. |
| `routed` | `transformed` | lane gate | Lane-specific transforms begin only after routing is explicit. |
| `transformed` | `compiled` | artifact gate | Compilation requires durable transform outputs and provenance continuity. |
| `compiled` | `staged` | publication gate | Staging requires package completeness and emission metadata. |
| `staged` | `emitted` | `publication_policy` | Emission is allowed only from a ready staged state. |
| `emitted` | `audited` | audit gate | Audit verifies lineage and outcome completeness. |
| any non-terminal working state | `held` | governance gate | Use when review, approval, prerequisites, or explicit pause is required. |
| any non-terminal working state | `rejected` | governance gate | Use when policy denies continuation. |
| any non-terminal working state | `failed` | execution/integrity gate | Use when a recoverable operational failure occurs. |
| any non-terminal working state | `aborted` | operator/system abort gate | Use for explicit termination. |
| `held` | previous non-control state | gate release | Resume only after a recorded release decision. |
| `failed` | previous safe working state | remediation gate | Resume only after the cause is corrected and recorded. |
| `failed` | `aborted` | operator/system abort gate | Use when recovery is not attempted. |
| `held` | `rejected` | governance gate | Use when a paused item is later denied. |
| `held` | `aborted` | operator/system abort gate | Use when a paused item is intentionally terminated. |

## Forbidden Transitions

The following transitions are forbidden by the canonical model:

- Direct movement from `captured`, `normalized`, `classified`, `promoted`, or `routed` to `emitted`.
- Direct movement from `captured`, `normalized`, `classified`, `promoted`, or `routed` to `audited`.
- Direct movement from `captured` to `compiled` or `staged`.
- Direct movement from `promoted` to `compiled` without routing and lane-specific transform.
- Direct movement from `held` to `emitted` without resuming the previous working state.
- Direct movement from `failed` to `emitted` without remediation and re-entry.
- Any transition out of `rejected`.
- Any transition out of `aborted`.
- Any silent reuse of an `audited` terminal object without opening a new run or version.

## Hold, Reject, Fail, and Abort Semantics

`held`

- Meaning: policy or prerequisites are incomplete, but the object remains eligible to continue later.
- Expected evidence: hold reason, responsible gate or policy, timestamp, and release criteria.
- Resume rule: resume to the previous non-control state only after a recorded release decision.

`rejected`

- Meaning: governance denied continuation for the current run or object.
- Expected evidence: rejection reason, rejecting policy or operator, and affected object references.
- Resume rule: none in-place. Retry requires a new run or new artifact version.

`failed`

- Meaning: execution or integrity failed, but recovery is still possible.
- Expected evidence: failure category, failing component, timestamp, and remediation note.
- Resume rule: only to the previous safe working state after remediation is recorded.

`aborted`

- Meaning: execution was intentionally stopped, not merely failed.
- Expected evidence: abort actor, reason, and timestamp.
- Resume rule: none in-place. Continuing work requires a new run.

## Where Governance Gates Apply

Governance gates apply before any transition that changes operational meaning or mutates durable state:

- before normalization when intake quality or payload validity is in question
- before promotion when captured or classified inputs are incomplete or disallowed
- before routing when lane assignment would mutate queue or incoming state
- before durable artifact registration during transform or compile steps
- before staging when package completeness, provenance, or required sidecars are missing
- before emission when output readiness, policy eligibility, or human approval is required
- before resuming from `held` or `failed`
- before operator overrides, aborts, or rejections

## Current Foundation Evidence

The committed transition-governance foundation currently proves:

- the canonical state graph loads from `config/state_machine.yaml`
- lane registration loads from `config/lanes.yaml`
- the intake, promotion, routing, and publication policy declarations load from `config/policies/`
- `validate_transition()` allows configured transitions, rejects forbidden skips, fails closed on missing promotion context, and enforces control-state TTL expiry in direct tests

Capture, intake, curation, activation-governor, registry reconciliation, and operator/security integrations are dependent work around this foundation. Their presence in the architecture model is not a claim that every integration has landed in the foundation commit.
