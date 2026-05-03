# Governed Shell MVP Acceptance

## Phase 1 Acceptance Criteria

Phase 1 is complete when the repository contains:

- governed shell architecture docs
- strict JSON Schema contracts under `app/governed_shell/schemas/`
- pytest coverage for schema validation and raw-shell rejection

## Required Proofs

The Phase 1 tests must prove:

- a valid read-only proposal passes schema validation
- a valid dry-run `registered_script` proposal passes schema validation
- malformed proposals fail
- unknown top-level fields fail
- raw shell fields fail
- forbidden PowerShell command identifiers fail
- path traversal fails
- absolute paths fail
- unknown operation types fail

## Explicit Non-Goals

Phase 1 does not implement:

- execution
- simulation behavior
- runner behavior
- policy engine behavior
- model integration
- registered script execution

Any claim that governed shell execution exists after Phase 1 is incorrect.

## MVP Boundary Notes

- `registered_native` is present only as a structural schema shape
- it is not executable in MVP planning
- dry-run `registered_script` proposals may validate structurally
- structural validation is not execution authorization

## Validator Note

`jsonschema>=4` is the recommended validator dependency for later phases that add enforcement code. If unavailable in another environment, Phase 1 schema tests should skip clearly rather than silently falling back to permissive behavior.
