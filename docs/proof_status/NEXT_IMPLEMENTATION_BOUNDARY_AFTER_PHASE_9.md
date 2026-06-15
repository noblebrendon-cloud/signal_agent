# Next Implementation Boundary After Phase 9

The next safe implementation phase is:

```text
Phase 11: Local offline verification harness for static export/import packets.
```

## Goal

Use exported static packets as fixtures for the backend proof path and produce backend result packets that the static UI can import, without adding server code, backend submission, or production writes.

This should demonstrate a complete offline packet round trip:

```text
static export JSON fixture
-> backend Governed Authoring proof path
-> backend result/output manifest JSON fixture
-> static import-compatible result packet
```

## Allowed Scope

Allowed:

- Add local fixture packets under an appropriate test fixture directory.
- Add a CLI or test harness that reads an exported static packet fixture from disk.
- Run the existing backend Governed Authoring proof path against that fixture.
- Write test-scoped output fixtures only when isolated from production data.
- Assert that generated backend result packets are import-compatible with the static UI contract.
- Keep production JSONL ledgers unchanged.
- Keep the static UI non-production and offline.

## Disallowed Scope

Do not add:

- Server code.
- Browser-to-backend submission.
- Network calls from the static prototype.
- Python calls from the browser UI.
- Production authoring artifact writes.
- Production canonical ledger writes by default.
- Authentication or hosted-app behavior.
- Claims that the UI is backend-governed.

## Acceptance Criteria

Phase 11 should be accepted only if:

- Static export fixture shape matches the documented bridge contract.
- The backend proof path can consume the exported fixture.
- The harness produces backend result/output manifest JSON compatible with static import.
- Evidence refs survive the offline round trip.
- Unresolved tensions survive the offline round trip.
- Review status survives the offline round trip.
- Output status survives the offline round trip.
- Missing evidence and generator/model self-approval remain rejected or flagged.
- Production JSONL ledgers remain unchanged.
- Static prototype source files are not rewritten.

## Remaining Deferred Work

Still deferred after Phase 11:

- Hosted app/server surface.
- Production backend wiring.
- Durable authoring artifact store.
- Production canonical ledger policy for authoring.
- Real user identity and human authority source.
- Full interactive browser verification under local-file constraints.
- Full repo-wide governance.
