# v0.2 CLI Integration Decision

Version target:

```text
v0.2-local-authoring-surface
```

## Decision

Phase 29 may expose the command-router foundation through the existing Governed Authoring CLI.

Decision status:

```text
Approved for bounded CLI integration only.
```

This decision does not approve server work, browser-backend submission, production writes, default production ledger writes, or static prototype UI changes.

## Rationale

The command-router foundation has been re-verified after Phase 26:

- Path policy tests passed.
- Workspace tests passed.
- Command router tests passed.
- Existing Governed Authoring offline proof paths still pass.
- Production JSONL fingerprint stayed unchanged.
- No server/network behavior was added.

The next bounded improvement is CLI exposure of the existing local router behavior, not a new runtime surface.

## Approved Phase 29 Scope

Phase 29 may:

- Add a local CLI command group that calls the existing command-router foundation.
- Route explicit input files to explicit workspace outputs.
- Preserve fail-closed path classification.
- Preserve no default ledger writes.
- Preserve no production writes.
- Use tests only with temp workspaces and fixtures.
- Report structured path and governance errors from the router.

## Required CLI Properties

The CLI integration must remain:

- Local.
- Non-production.
- Explicit-input.
- Explicit-workspace.
- Explicit-output-path for writes.
- Outside repo `data/`.
- Server-free.
- Browser-submission-free.
- Default-ledger-write-free.

## Forbidden Phase 29 Scope

Phase 29 must not add:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Static prototype UI changes.
- Production authoring writes.
- Default production canonical ledger writes.
- Repo `data/` writes.
- Production-governed UI claims.

## CLI Commands To Consider

Candidate CLI exposure may map to existing router commands:

- `verify-static-export`
- `run-demo-bundle`
- `inspect-result-packet`
- `validate-output-directory`
- `summarize-proof-output`

The CLI should not invent default production paths.

## Required Phase 29 Tests

Phase 29 tests should prove:

- CLI rejects repo `data/` workspace.
- CLI rejects repo `data/` output path.
- CLI rejects production ledger path.
- CLI rejects implicit ledger path when ledger is requested.
- CLI rejects overwrite by default.
- CLI writes result packets only to explicit workspace `results/`.
- CLI writes summaries only to explicit workspace `summaries/`.
- Optional ledger writes require explicit workspace `ledgers/` path.
- No default ledger write occurs.
- Production JSONL fingerprint remains unchanged.
- No static prototype UI files change.
- No server/network behavior is added.

## Safe Claim After Phase 28

Use:

```text
v0.2 command-router foundation has been re-verified and is approved for bounded CLI integration planning.
```

Do not claim CLI integration exists until Phase 29 implements and tests it.
