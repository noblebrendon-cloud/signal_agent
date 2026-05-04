# Governed Shell MVP Acceptance

## Phase 1 Acceptance Criteria

Phase 1 is complete when the repository contains:

- governed shell architecture docs
- strict JSON Schema contracts under `app/governed_shell/schemas/`
- pytest coverage for schema validation and raw-shell rejection

## Phase 2 Acceptance Criteria

Phase 2 is complete when the repository contains:

- governed shell proposal loading helpers
- explicit schema validation helpers
- deterministic canonical JSON and proposal hashing
- path validation that rejects absolute paths and traversal

## Phase 3 Acceptance Criteria

Phase 3 is complete when the repository contains:

- a config-driven default-deny governed shell policy
- deterministic policy review helpers
- authoritative risk recomputation
- explicit denial of unknown commands, unknown parameters, unknown roots, native operations, network requests, and privilege escalation requests

## Phase 4 Acceptance Criteria

Phase 4 is complete when the repository contains:

- an append-only governed-shell audit ledger
- deterministic record hashing and `prev_hash` chaining
- read-only replay by session
- read-only verify-log support that fails closed on tampering

## Phase 5 Acceptance Criteria

Phase 5 is complete when the repository contains:

- exact proposal-hash confirmation utilities
- sealed execution plan construction from normalized proposal and policy review state
- deterministic `plan_hash` verification
- atomic sealed-plan JSON writing without execution behavior

## Phase 6 Acceptance Criteria

Phase 6 is complete when the repository contains:

- metadata-only snapshot manifests derived from sealed plan declared paths
- deterministic snapshot hashing and verification
- simulation-only receipts with `executed=false`
- optional simulation audit trail events that remain append-only and replayable

## Required Proofs

The governed shell tests must prove:

- a valid read-only proposal passes schema validation
- a valid dry-run `registered_script` proposal passes schema validation
- malformed proposals fail
- unknown top-level fields fail
- raw shell fields fail
- forbidden PowerShell command identifiers fail
- path traversal fails
- absolute paths fail
- unknown operation types fail
- canonical hashing is stable across key ordering
- recursive read risk escalates above low risk
- unknown or disabled bindings fail closed
- policy loading failures fail closed
- audit hash chains verify on clean ledgers
- edited records are detected
- broken `prev_hash` values are detected
- malformed JSONL is detected
- missing replay sessions report not clean
- confirmation-required proposals fail without an exact full hash match
- sealed plan hashes verify and fail after mutation
- denied policy decisions cannot create plans
- snapshot manifests verify and fail after mutation
- simulation receipts verify and fail after mutation
- simulation audit events preserve a clean verify-log chain

## Phase 7 Acceptance Criteria

Phase 7 is complete when the repository contains:

- a deterministic CLI entrypoint at `python -m app.governed_shell.cli`
- proposal stub, policy-test, review, approve, simulate, verify-log, and replay commands
- JSON-only command output suitable for local operator control
- no command path that executes, dispatches, or invokes an external runner

## Explicit Non-Goals

Phases 1 through 3 do not implement:

- execution
- simulation behavior
- runner behavior
- PowerShell invocation
- audit logging
- sealed plan creation
- model integration
- registered script execution
- module registration

Phase 4 still does not implement:

- execution
- PowerShell invocation
- proposal approval
- sealed execution plans
- repair of corrupted ledgers

Phase 5 still does not implement:

- execution
- PowerShell invocation
- simulation behavior
- proposal approval
- runner behavior
- process creation or output capture

Phase 6 still does not implement:

- real execution
- PowerShell invocation
- shell command invocation
- subprocess creation
- runner behavior
- proposal approval
- model integration

Phase 7 still does not implement:

- real execution
- subprocess creation
- shell command invocation
- runner behavior
- model integration

Any claim that governed shell execution exists after Phase 6 is incorrect.

## MVP Boundary Notes

- `registered_native` is present only as a structural schema shape
- it is denied in MVP policy review
- dry-run `registered_script` proposals may validate structurally
- structural validation is not execution authorization
- disabled script bindings remain denied even after schema validation

## Validator Note

`jsonschema>=4` is the required schema validator for the governed shell enforcement layers in Phases 2 and 3. The Phase 3 policy layer must fail closed rather than silently falling back to permissive behavior.
