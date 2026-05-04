# Controlled Failure Demo

This demo is a small proof artifact for deterministic governance.

It shows the same packing slip reconciliation workflow under two execution models:

- Standard execution continues after required verification context is lost and still returns success.
- Governed execution detects the missing context before verification and blocks the step fail-closed.

## What The Demo Proves

The demo proves one narrow point:

- A workflow can look successful even when a required verification input is missing.
- A governed runner can stop that false success by enforcing a precondition at the step boundary.

The workflow is fixed and deterministic:

`extract_items -> transform_items -> verify_inventory`

The failure is also fixed and deterministic:

- After `transform_items`, the demo removes `expected_order` from state.

## Why The Standard Runner Is Unsafe

The standard runner does not re-check that verification still has the context it needs.

It proceeds into `verify_inventory` after `expected_order` has already been removed from state. The final output still looks clean:

- `status: success`
- `message: Inventory verified; no discrepancies found.`

That is unsafe because the success message hides the fact that verification ran without the expected order.

## Why The Governed Runner Fails Closed

The governed runner checks for required verification fields before calling `verify_inventory`.

When `expected_order` is missing, it does not continue. It returns:

- `status: fail_closed`
- `reason_code: missing_verification_context`
- `failed_step: verify_inventory`

This is the deterministic governance behavior the demo is meant to show: missing verification context blocks the transition instead of being silently ignored.

## How To Run

From the repo root:

```powershell
py -3 -m app.demo.controlled_failure.cli run
```

## Expected Output

```text
=== STANDARD SYSTEM ===
status: success
message: Inventory verified; no discrepancies found.
hidden_problem: expected_order_present=false

=== GOVERNED SYSTEM ===
status: fail_closed
reason_code: missing_verification_context
failed_step: verify_inventory
missing_fields: ["expected_order"]
```

## Mapping To Deterministic Governance

This demo maps to deterministic governance in a minimal way:

- state is explicit
- the workflow steps are fixed
- the failure injection is fixed
- the governed decision is fixed
- the blocked reason is explicit and machine-readable

The trace log at `data/state/demo/demo_event_log.jsonl` records the visible transition behavior for each runner.

## What This Demo Does Not Prove

This demo does not prove:

- full production coverage
- correctness for every workflow
- correctness under external APIs, LLM calls, or concurrency
- complete architectural governance across the whole repo

It is only a deterministic proof that fail-closed verification is safer than success-shaped continuation when required verification context is missing.
