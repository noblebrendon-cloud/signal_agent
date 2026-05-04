# Governed Shell Integration Plan

## Target Flow

The governed shell is designed around a proposal-only boundary:

`intent -> proposal -> schema validation -> policy evaluation -> sealed plan -> simulation -> audit/replay`

## Authority Model

- user intent is not executable authority
- model output is not executable authority
- the proposal is only an input artifact
- validation and policy are the authority
- execution must consume a sealed plan, not a free-form prompt or shell string

## Phase 1 Scope

Phase 1 establishes only the static contracts:

- repository placement
- schema definitions
- test coverage for strict proposal validation
- explicit rejection of raw shell representations

Phase 1 does not implement:

- policy evaluation logic
- execution plan generation code
- simulation code
- audit ledger writers
- replay verification code

## Phase 2 Scope

Phase 2 adds only the repo-native validation layer:

- proposal JSON loading
- command proposal schema validation
- deterministic canonical JSON rendering
- stable proposal hashing
- symbolic path reference validation

Phase 2 still does not implement:

- policy decisions
- execution
- simulation behavior
- audit logging

## Phase 3 Scope

Phase 3 adds only deterministic policy review:

- config-driven default-deny policy loading
- command catalog matching
- authoritative risk recomputation
- confirmation requirement reporting
- deterministic policy review reports

Phase 3 still does not implement:

- execution
- PowerShell invocation
- runner behavior
- audit logging
- sealed plan creation
- state writes

## Phase 4 Scope

Phase 4 adds only append-only review evidence:

- append-only JSONL audit logging for review events
- deterministic record hashing and hash-chain linking
- read-only replay by session
- read-only log verification

Phase 4 still does not implement:

- execution
- PowerShell invocation
- proposal approval
- sealed plan creation
- state mutation outside the audit ledger itself
- repair of corrupted ledgers

## Phase 5 Scope

Phase 5 adds only exact-hash confirmation and sealed plan creation:

- exact proposal-hash confirmation checks
- sealed execution plan construction from normalized proposals and policy decisions
- deterministic `plan_hash` computation and verification
- atomic writing of sealed plan JSON

Phase 5 still does not implement:

- execution
- PowerShell invocation
- simulation behavior
- proposal approval workflows
- runner behavior
- stdout or stderr capture
- process creation

## Proposal Contract Direction

The proposal contract is intentionally narrow:

- operations are explicit
- path references use `root_id + relative_path`
- absolute paths are not allowed in proposal input
- parent traversal using `..` is not allowed
- raw shell payloads are not representable

Allowed operation shapes in the schema:

1. `powershell_cmdlet`
   - uses `cmdlet_id`
   - uses typed parameters only
2. `registered_script`
   - uses `script_id`
   - uses typed arguments only
   - dry-run shapes may validate structurally in Phase 1
3. `registered_native`
   - may exist structurally
   - remains denied in MVP planning

## Execution Direction

Later phases should preserve these constraints:

- no raw shell text in proposal input
- no inline PowerShell `-Command`
- no `Invoke-Expression`
- no `Start-Process`
- no model-supplied script text
- no permissive fallback for unknown operations or parameters

## Policy Direction

Phase 3 policy review is default-deny:

- unknown command rejects
- unknown parameter rejects
- unknown root rejects
- path escape rejects
- missing dry-run support rejects
- logging failure rejects
- snapshot failure rejects

The MVP policy catalog is intentionally narrow:

- `ps.get_child_items_v1` is the only enabled binding
- `registered_script` remains structurally representable but disabled
- `registered_native` remains denied in MVP

The Phase 4 audit layer is also intentionally narrow:

- it records review state only
- it does not imply execution exists
- it fails closed on malformed JSONL, schema drift, broken `prev_hash`, incorrect `record_hash`, or non-monotonic `event_index`

The Phase 5 plan layer is similarly narrow:

- it creates plans only
- it requires exact proposal-hash confirmation when policy requires it
- it does not execute or simulate the plan it writes

## Validation Direction

The Phase 1 schemas are written in strict Draft 2020-12 style and are intended to be enforced with `jsonschema>=4`.
