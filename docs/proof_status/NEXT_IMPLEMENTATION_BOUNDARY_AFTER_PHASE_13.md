# Next Implementation Boundary After Phase 13

The next safe implementation phase is:

```text
Phase 15: Demo proof bundle command.
```

## Goal

Provide a local demo command or scripted proof bundle that runs representative static export fixtures through the Phase 13 CLI into a temp output directory and produces a proof summary.

The intended local-only flow is:

```text
representative static export fixtures
-> local demo proof bundle command
-> Phase 13 offline CLI
-> temp result JSON files
-> proof summary
```

## Allowed Scope

Allowed:

- Add a narrow local demo command or script.
- Use representative static export fixtures.
- Write result JSON files only to an explicit temp or caller-provided output directory.
- Produce a proof summary describing fixture outcomes.
- Use optional canonical ledger output only when explicitly provided and constrained to temp/caller paths.
- Keep production JSONL ledgers unchanged.
- Keep the static prototype UI unchanged.

## Disallowed Scope

Do not add:

- Server code.
- Browser-to-backend submission.
- Network calls from the static prototype.
- Python calls from the browser UI.
- Production authoring artifact writes.
- Default production canonical authoring ledger writes.
- Authentication or hosted-app behavior.
- Claims that the UI is backend-governed.
- Claims that repo-wide governance is complete.

## Acceptance Criteria

Phase 15 should be accepted only if:

- The demo command runs representative static export fixtures through the local CLI.
- Outputs are written only to a temp or explicit caller-provided directory.
- The proof summary records provisional, approved, rejected, and deferred outcomes.
- Missing evidence remains rejected.
- Blocking unresolved tension remains deferred.
- Generator/model self-approval remains rejected.
- Evidence refs survive the demo loop.
- Unresolved tensions survive the demo loop.
- Review status survives the demo loop.
- Output status survives the demo loop.
- Optional canonical ledger writes occur only when an explicit temp/caller path is provided.
- Production JSONL ledgers remain unchanged.
- Static prototype source files are not rewritten.

## Remaining Deferred Work

Still deferred after Phase 15 unless explicitly implemented later:

- Hosted app/server surface.
- Browser-to-backend submission.
- Production backend wiring.
- Durable authoring artifact store.
- Production canonical ledger policy for authoring.
- Real user identity and human authority source.
- Full interactive browser verification under local-file constraints.
- Full repo-wide governance.
