# Next Implementation Boundary After Phase 7

The next safe implementation phase is:

```text
Phase 9: Static prototype export/import UI patch.
```

## Goal

Allow the existing static prototype UI to export backend-compatible packets and import backend result packets.

This should make the static prototype useful with the backend proof path while keeping it static.

## Allowed Scope

Allowed:

- Add export JSON action for a bridge-compatible prototype packet.
- Add import JSON action for a backend/prototype result packet.
- Display imported backend result status in the existing UI.
- Use the Phase 7 packet contract.
- Keep all data local to the browser.
- Add tests or fixtures that do not modify production JSONL ledgers.

## Disallowed Scope

Do not add:

- Server code.
- Python calls from the browser.
- Production authoring artifact writes.
- Production canonical ledger writes by default.
- Authentication.
- Hosted app behavior.
- Full UI rewrite.
- Claims that the UI is backend-governed.

## Acceptance Criteria

Phase 9 should be accepted only if:

- The existing static prototype UI is patched minimally, not rewritten.
- The UI can export a packet compatible with `prototype_to_source_packet(...)`.
- The UI can import a result compatible with `output_manifest_to_prototype_result(...)`.
- Existing prototype state remains local/browser-based.
- Production JSONL ledgers remain unchanged in tests.
- Phase 7 bridge tests still pass.
- Governed Authoring backend tests still pass.

## Remaining Deferred Work

Still deferred after Phase 9:

- Hosted app/server surface.
- Production backend wiring.
- Durable authoring artifact store.
- Production canonical ledger policy for authoring.
- Real user identity and human authority source.
- Full repo-wide governance.
