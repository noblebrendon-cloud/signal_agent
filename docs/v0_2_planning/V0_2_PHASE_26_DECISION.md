# v0.2 Phase 26 Decision

Version target:

```text
v0.2-local-authoring-surface
```

## Decision

Recommended Phase 26:

```text
Local command-router runtime foundation.
```

Phase 26 should implement the local command-router/path-classification runtime first, not a local server.

## Approved Scope

Phase 26 may implement:

- Path classification.
- Workspace validation.
- Explicit output directory validation.
- Forbidden path rejection.
- Optional ledger path validation.
- Command-router skeleton over existing offline proof paths.
- Focused tests proving no production writes.
- Focused tests proving fail-closed behavior.
- Focused tests proving no default ledger writes.

## Required Runtime Characteristics

The Phase 26 runtime must remain:

- Local.
- Non-production.
- Explicit-path only.
- Caller-workspace based.
- Outside repo `data/`.
- Separate from production ledgers.
- Separate from production authoring artifacts.
- Server-free.
- Browser-submission-free.

## Forbidden Scope

Phase 26 must not implement:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Hosted app behavior.
- Backend-wired UI.
- Production authoring artifact writes.
- Default canonical ledger writes.
- Writes under repo `data/`.
- Production-governed UI claims.

## Required Tests

Phase 26 should include tests for:

- Allowed temp workspace.
- Allowed explicit workspace outside repo `data/`.
- Allowed result path under workspace `results/`.
- Allowed summary path under workspace `summaries/`.
- Allowed validation path under workspace `validation/`.
- Allowed metadata path under workspace `metadata/`.
- Allowed draft path under workspace `drafts/`.
- Optional explicit ledger path under workspace `ledgers/`.
- Rejection of repo `data/` workspace.
- Rejection of repo `data/` result path.
- Rejection of production ledger path.
- Rejection of implicit ledger path.
- Rejection of parent traversal outside workspace.
- Rejection of ambiguous or unknown paths.
- Rejection of overwrite attempts by default.
- No production JSONL fingerprint change.
- No server or network behavior.
- No production authoring artifact writes.

## Inputs To Reuse

Phase 26 should build from:

- `V0_2_COMMAND_ROUTER_DESIGN.md`
- `V0_2_COMMAND_CONTRACT.md`
- `V0_2_ROUTER_ERROR_MODEL.md`
- `V0_2_WORKSPACE_CONTRACT.md`
- `V0_2_OUTPUT_DIRECTORY_POLICY.md`
- `V0_2_PATH_CLASSIFICATION_POLICY.md`
- `V0_2_OVERWRITE_POLICY.md`
- `V0_2_OUTPUT_POLICY_TEST_MATRIX.md`

## Expected Safe Claim After Phase 26

Only if implemented and tested:

```text
v0.2 has a local command-router foundation with fail-closed path classification for covered explicit local output paths.
```

Still unsafe after Phase 26:

- Production app.
- Local server.
- Browser-backend submission.
- Backend-wired UI.
- Production authoring writes.
- Repo-wide governance.
- Complete IBVM proof.

## Non-Goals

Phase 26 is not a UI phase, server phase, hosted app phase, or production artifact phase.
