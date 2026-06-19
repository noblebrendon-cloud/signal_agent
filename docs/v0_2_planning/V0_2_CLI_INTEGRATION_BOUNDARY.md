# v0.2 CLI Integration Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Boundary Statement

Phase 29 exposes the local command-router foundation through the Governed Authoring CLI for covered explicit workspace paths only.

It does not convert the system into a production app, local server, backend-wired UI, production artifact store, repo-wide governance layer, or complete IBVM proof.

## Allowed Phase 29 Claim

Use:

```text
v0.2 exposes a local command-router foundation through the Governed Authoring CLI for covered explicit workspace paths.
```

Required qualifiers:

- Local.
- Non-production.
- Covered explicit workspace paths only.
- Fail-closed path validation.
- No default ledger writes.
- No repo `data/` writes.
- No production authoring writes.
- No server or browser-backend submission.

## Unsafe Claims

Do not claim:

- v0.2 is production-ready.
- v0.2 is a local server.
- The static UI is backend-wired.
- Browser-backend submission exists.
- Production authoring writes are governed.
- Default production canonical authoring ledger writes are enabled.
- Repo-wide governance is complete.
- Complete IBVM proof exists.

## Mutation Boundary

Phase 29 added CLI integration and tests for the covered router commands.

It did not add:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Static prototype UI wiring.
- Production authoring artifact writes.
- Default production canonical ledger writes.

## Ledger Boundary

Canonical ledger behavior remains explicit-path only for this surface.

Phase 29 does not enable default production canonical ledger writes and does not make production JSONL ledgers part of the command-router write target.

## Workspace Boundary

The CLI requires an explicit workspace path for router operations that write proof outputs.

Covered writes remain confined to validated local workspaces and fail closed on forbidden paths such as repo `data/`, production ledger paths, production artifact paths, ambiguous paths, and parent traversal.
