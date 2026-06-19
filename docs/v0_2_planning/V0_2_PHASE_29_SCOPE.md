# v0.2 Phase 29 Scope

Version target:

```text
v0.2-local-authoring-surface
```

## Recommended Phase 29

Phase 29 should be:

```text
Command-router CLI integration.
```

Phase 29 should expose the command-router foundation through the local CLI only.

## Objective

Expose covered command-router behavior through explicit local CLI commands while preserving the Phase 26 and Phase 28 boundaries.

The CLI should make the local workflow easier to run without changing the system into a server, backend-wired UI, or production authoring surface.

## Allowed Scope

Phase 29 may:

- Add local CLI command routing to the existing Governed Authoring CLI.
- Call the existing command-router foundation.
- Require explicit input files.
- Require explicit workspace paths.
- Require explicit output paths for write-capable commands.
- Preserve fail-closed path classification.
- Preserve explicit optional ledger path behavior.
- Add tests using temp workspaces and existing fixtures.
- Record structured command errors.

## Forbidden Scope

Phase 29 must not add:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Static prototype UI changes.
- Production authoring writes.
- Default production canonical ledger writes.
- Repo `data/` writes.
- Hosted app behavior.
- Production-governed UI claims.

## Candidate CLI Commands

Candidate command names:

- `router verify-static-export`
- `router run-demo-bundle`
- `router inspect-result-packet`
- `router validate-output-directory`
- `router summarize-proof-output`

The exact CLI spelling should follow the existing Governed Authoring CLI style.

## Required Tests

Phase 29 should add tests for:

- Valid CLI result output under workspace `results/`.
- Valid CLI summary output under workspace `summaries/`.
- Valid CLI demo-bundle run into temp workspace.
- Explicit ledger path under workspace `ledgers/`.
- No default ledger write.
- Repo `data/` rejection.
- Production ledger path rejection.
- Overwrite rejection by default.
- Missing input.
- Invalid JSON.
- Unsupported packet shape.
- Production JSONL fingerprint preservation.
- No static prototype UI mutation.
- No server/network behavior.

## Required Verification

Phase 29 should re-run:

- New CLI integration tests.
- Phase 26 path policy tests.
- Phase 26 workspace tests.
- Phase 26 command router tests.
- Existing offline CLI/harness/demo bundle tests.
- Existing Governed Authoring backend and bridge tests.

## Safe Claim After Phase 29

Only if implemented and tested:

```text
v0.2 exposes the local command-router foundation through bounded explicit-path CLI commands.
```

Still unsafe:

- Production readiness.
- Local server.
- Browser submission.
- Backend-wired UI.
- Production authoring writes.
- Repo-wide governance.
- Complete IBVM proof.
