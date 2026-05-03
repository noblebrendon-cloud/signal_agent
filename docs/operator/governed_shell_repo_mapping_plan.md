# Governed Shell Repo Mapping Plan

## Decision

The governed shell module lives at `app/governed_shell/`.

This path is the best fit for the existing repository because:

- governed local modules already live under `app/`
- `app/retention/` is the closest precedent for a bounded, local-only, append-only governance surface
- `signal_agent/operator/` is a control facade, not the authoritative place for execution policy
- `app/hq/` is focused on capture and curation lane governance, not generic execution governance

## Boundary

The intended flow is:

`intent -> proposal -> schema validation -> policy evaluation -> sealed plan -> simulation -> audit/replay`

For Phase 1, only the documentation and schema contracts are implemented.

Not implemented in this phase:

- execution
- simulation runtime
- PowerShell runner behavior
- policy engine
- model integration
- registered script execution

## Existing Surfaces To Reuse Later

- `app/utils/io_contract.py`
  - shared atomic write and append-only JSONL helpers
- `app/retention/jsonl_store.py`
  - append-only hash-chain pattern for ledger records
- `app/retention/execution_dry_run.py`
  - local-only dry-run precedent
- `app/hq/governance/transition_gate.py`
  - canonical write-workflow admission surface when operator-mediated workflows are introduced later
- `signal_agent/operator/invariant_checker.py`
  - structural enforcement surface for module boundary rules
- `tools/verify_system.py`
  - repo-wide smoke verification surface

## Surfaces Explicitly Not Modified In Phase 1

- `app/agent.py`
- `app/hq/governance/transition_gate.py`
- `config/state_machine.yaml`
- `signal_agent/operator/runtime.py`

## Rejected Alternatives

### `app/hq/execution_shell/`

Rejected because it would classify shell governance as an HQ lane module instead of a general local governance module.

### `signal_agent/operator/governed_shell/`

Rejected because it would blur the line between:

- proposal intake and operator control
- authoritative execution governance

The operator may propose later, but it should not own the governed shell boundary.

### Separate toy project

Rejected because the module must be first-class in the existing repository and must reuse existing governance patterns.

## Phase 1 Deliverables

- architecture docs
- strict JSON Schema contracts
- schema-focused pytest coverage

## Phase 2 Dependency Note

`jsonschema>=4` is the recommended validator dependency for full Draft 2020-12 enforcement in later phases.
