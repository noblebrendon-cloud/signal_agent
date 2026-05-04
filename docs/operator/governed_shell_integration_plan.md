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

## Validation Direction

The Phase 1 schemas are written in strict Draft 2020-12 style and are intended to be enforced with `jsonschema>=4`.
