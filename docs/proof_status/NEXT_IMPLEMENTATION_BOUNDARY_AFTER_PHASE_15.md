# Next Implementation Boundary After Phase 15

The next safe implementation phase is:

```text
Phase 17: Release/proof-pack consolidation.
```

## Goal

Create one local proof-pack index that points to the proof chain, proof-status docs, relevant test commands, demo bundle command, generated-output expectations, and safe claims.

This should consolidate evidence without changing runtime behavior.

## Allowed Scope

Allowed:

- Add a local proof-pack index document.
- Reference existing proof-chain commits.
- Reference existing proof-status documents.
- Reference existing Governed Authoring docs.
- List test commands that prove the covered behavior.
- List the demo proof-bundle command.
- List safe claims and disallowed claims.
- Keep production JSONL ledgers unchanged.
- Keep static prototype UI files unchanged.

## Disallowed Scope

Do not add:

- Runtime behavior changes.
- Server code.
- Browser-to-backend submission.
- Network calls from the static prototype.
- Python calls from the browser UI.
- Production authoring artifact writes.
- Default production canonical authoring ledger writes.
- Authentication or hosted-app behavior.
- Claims that the UI is backend-governed.
- Claims that repo-wide governance is complete.

## Suggested Proof-Pack Index Contents

The proof-pack index should include:

- Proof chain commit list.
- Current safe summary.
- Links to backend, bridge, offline harness, CLI, and demo-bundle docs.
- Test command matrix.
- Demo command examples.
- Expected local demo output artifacts.
- Ledger boundary statement.
- Static UI boundary statement.
- Production-write exclusion.
- Remaining proof gaps.

## Acceptance Criteria

Phase 17 should be accepted only if:

- It is documentation/index-only.
- It changes no runtime/source files.
- It stages no production data files.
- It does not modify production JSONL ledgers.
- It names the exact local proof surfaces that are proven.
- It names the exact claims still out of scope.
- It keeps the safe-claims boundary aligned with executable evidence.

## Remaining Deferred Work

Still deferred after Phase 17 unless explicitly implemented later:

- Hosted app/server surface.
- Browser-to-backend submission.
- Production backend wiring.
- Durable authoring artifact store.
- Production canonical ledger policy for authoring.
- Real user identity and human authority source.
- Full interactive browser verification under local-file constraints.
- Full repo-wide governance.
