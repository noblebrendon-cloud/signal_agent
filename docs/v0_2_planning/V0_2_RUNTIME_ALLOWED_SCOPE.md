# v0.2 Runtime Allowed Scope

Version target:

```text
v0.2-local-authoring-surface
```

## Scope Purpose

This document defines the runtime scope allowed by the Phase 25 UI/server decision gate.

It is documentation/decision only. It does not implement runtime behavior, server behavior, browser-backend submission, production writes, or default canonical ledger writes.

## Allowed Runtime Scope For Phase 26

Phase 26 may include:

- Local command-router implementation.
- Path classification implementation.
- Explicit workspace validation.
- Explicit output directory validation.
- Explicit result path validation.
- Explicit summary path validation.
- Explicit validation report path validation.
- Explicit metadata path validation.
- Explicit draft path validation.
- Optional explicit ledger path validation.
- Forbidden path rejection.
- Parent traversal rejection.
- Ambiguous path fail-closed behavior.
- Command-router skeleton over existing offline proof paths.
- Tests proving no production writes.
- Tests proving no default ledger writes.
- Tests proving no server/network behavior.

## Allowed Commands

The first implementation may cover command groups already defined in the router design:

- `verify-static-export`
- `run-demo-bundle`
- `inspect-result-packet`
- `validate-output-directory`
- `summarize-proof-output`

Each command must use explicit inputs and explicit output paths where writes occur.

## Allowed Writes

Allowed writes are limited to:

- Explicit result path inside approved workspace `results/`.
- Explicit summary path inside approved workspace `summaries/`.
- Explicit validation path inside approved workspace `validation/`.
- Explicit metadata path inside approved workspace `metadata/`.
- Explicit draft path inside approved workspace `drafts/`.
- Explicit optional ledger path inside approved workspace `ledgers/`.
- Explicit temp output path selected for the run.

Every write must pass path classification before file creation or append.

## Forbidden Runtime Scope For Phase 26

Phase 26 must not include:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Browser-to-Python submission.
- Hosted app behavior.
- Production authoring artifact writes.
- Default canonical ledger writes.
- Writes under repo `data/`.
- Writes to production ledger paths.
- Writes to production artifact paths.
- Implicit output directories.
- Hidden background state.
- Production-governed UI claims.

## Required Fail-Closed Behavior

The runtime must fail before writing for:

- `forbidden_repo_data_path`
- `forbidden_production_ledger_path`
- `forbidden_production_artifact_path`
- `forbidden_parent_traversal`
- `ambiguous_path`
- `unknown_path`
- Existing output files when overwrite is not explicitly approved
- Missing required output paths

## Ledger Boundary

Canonical ledger writes remain disabled by default.

The only allowed Phase 26 ledger behavior is validation of an optional explicit local ledger path.

If ledger append is implemented in Phase 26, it must be:

- Explicitly requested.
- Explicit-path only.
- Inside approved workspace `ledgers/` or an approved temp directory.
- Outside repo `data/`.
- Outside production ledger paths.
- Covered by tests proving no default ledger write.

## Authority Boundary

Phase 26 may preserve local reviewer markers and review status in command outputs.

Phase 26 must not treat:

- Browser sessions as production authority.
- Generated output as its own approval authority.
- Local reviewer markers as production identity.
- Result packets as publication approval.

## Safe Claims

Allowed for this scope:

- "Phase 26 is limited to local command-router foundations."
- "Phase 26 excludes server behavior and browser-backend submission."
- "Phase 26 keeps v0.2 local and non-production."

Disallowed:

- "Phase 26 creates a backend-wired UI."
- "Phase 26 adds a local server."
- "Phase 26 enables production writes."
- "Phase 26 proves repo-wide governance."
- "Phase 26 completes IBVM proof."
