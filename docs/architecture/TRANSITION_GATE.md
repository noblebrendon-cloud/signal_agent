# Transition Gate

Status: bounded Path 2 runtime governance layer
Last updated: 2026-03-15

## What the Transition Gate Is

The transition gate is a small runtime enforcement layer that checks whether a requested lifecycle movement is allowed before a caller mutates durable state.

It does not replace capture, routing, curation, or operator logic. In the committed foundation it provides a validation and event-emission boundary that dependent modules can place before a relevant write or copy point:

- `validate_transition()` allows or rejects the requested lifecycle movement
- `emit_transition_event()` appends a canonical transition event when a caller records the attempt

## What It Reads

The gate reads the existing repo configuration directly:

- `config/state_machine.yaml` for allowed and forbidden lifecycle transitions
- the committed intake, promotion, routing, and publication policy YAML files under `config/policies/`
- `config/lanes.yaml` for lane registration and active versus reserved status

This keeps runtime governance aligned to the Path 2 architecture documents without introducing a new framework surface.

## How Transition Validation Works

`app/hq/governance/transition_gate.py` exposes `validate_transition(current_state, next_state, lane_id, context)`.

Validation occurs in five steps:

1. Load the canonical state machine and lane registry.
2. Fail closed when current or next state is outside the declared state space, except declared bootstrap transitions from a missing state.
3. Reject immediately if the transition is explicitly forbidden.
4. Confirm that the transition exists in the allowed transition list.
5. Evaluate the policy tied to that transition and confirm that the lane is operational.

The returned result includes:

- whether the transition is allowed
- the resolved current and attempted states
- lane id
- gate and policy id
- runtime policy checks
- rejection reason if blocked

## Policy Evaluation Model

The policy files remain declarative and human-readable. The gate does not try to interpret arbitrary prose conditions as executable logic.

Instead, it performs a small number of explicit runtime checks per policy:

- `intake_policy`: an inbound payload or file reference must be present
- `promotion_policy`: candidate members and bundle identity must be present
- `routing_policy`: bundle reference and router ruleset hash must be present
- `publication_policy`: durable identity, final path, and route key must be present
- lane registration and lane operational status are checked for all gated runtime transitions

The declared policy conditions from YAML are still attached to the returned policy result so the runtime event keeps the policy context visible.

## Canonical Ledger Events

When a caller records a transition attempt, `emit_transition_event()` appends canonical transition events to:

- `data/state/transition_gate_events.jsonl`

Each event contains:

- `run_id`
- `envelope_id` or artifact identifier when available
- `lane_id`
- `current_state`
- `attempted_state`
- `policy_result`
- `timestamp_utc`
- event status and reason

This does not replace existing ledgers like `promotion_log.jsonl`, `routing_log.jsonl`, or `artifact_registry.jsonl`. It adds a small canonical event stream that future ledger consolidation can build on.

## Dependent Runtime Integrations

The foundation commit establishes the gate and its configuration. Capture promotion, routing, curation, intake, activation-governor, shared lifecycle, and operator/security integration are separate dependent slices.

The architecture target for those dependent slices is to place the gate between intent and durable mutation at the relevant write or copy point, without turning the transition gate into a central orchestrator.

## Interaction with Lanes and Artifacts

The gate uses lane ids as the governance surface, not raw spine names alone.

- direct validation checks lane registration and active versus reserved status from `config/lanes.yaml`
- reserved spines in `config/lanes.yaml` are treated as configured but not operational
- route and spine helpers expose lane resolution for dependent callers

Lifecycle metadata helpers are available for dependent write paths. This foundation doc does not claim that promotion logs, routing logs, artifact registry entries, or state reconciliation are already migrated.

## Legacy State Inference

Not every dependent runtime path stores explicit lifecycle state before the gate runs. Any future integration that infers a prior state must preserve that distinction in emitted metadata rather than presenting an inference as explicit runtime truth.

## Current Limits

The gate is intentionally small:

- it does not unify all ledgers
- it does not introduce a central orchestrator
- it does not backfill historical state across existing artifacts
- it does not yet gate every transform or emission path in the repo

Its job is only to make the Path 2 lifecycle enforceable at key mutation points with minimal disruption.

The direct foundation proof for this layer lives in `tests/test_hq_transition_gate.py`.
