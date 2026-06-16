# Next Implementation Boundary After Phase 11

The next safe implementation phase is:

```text
Phase 13: Local CLI wrapper for the offline harness.
```

## Goal

Provide a local command that takes a static export JSON file and writes a static-import-compatible result JSON file to a chosen output path, without server code, backend submission, production writes, or default production ledger writes.

The intended local-only flow is:

```text
static export JSON file
-> local CLI command
-> offline harness
-> backend Governed Authoring proof path
-> static-import-compatible result JSON file
```

## Allowed Scope

Allowed:

- Add a narrow local CLI entry point or command module for the offline harness.
- Read a static export JSON file from a user-provided path.
- Write a static-import-compatible result JSON file to a user-provided output path.
- Support an optional canonical ledger path only when explicitly provided.
- Keep tests isolated to temp paths and fixtures.
- Keep production JSONL ledgers unchanged.

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

## Acceptance Criteria

Phase 13 should be accepted only if:

- CLI reads a static export fixture and writes a static-import-compatible result file.
- CLI output matches the existing offline harness result contract.
- Optional canonical ledger writes occur only when a temp/test path is explicitly supplied.
- Evidence refs survive CLI execution.
- Unresolved tensions survive CLI execution.
- Review status survives CLI execution.
- Output status survives CLI execution.
- Missing evidence and generator/model self-approval remain rejected or flagged.
- Production JSONL ledgers remain unchanged.
- Static prototype source files are not rewritten.

## Remaining Deferred Work

Still deferred after Phase 13:

- Hosted app/server surface.
- Browser-to-backend submission.
- Production backend wiring.
- Durable authoring artifact store.
- Production canonical ledger policy for authoring.
- Real user identity and human authority source.
- Full interactive browser verification under local-file constraints.
- Full repo-wide governance.
