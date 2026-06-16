# Governed Authoring Offline Harness

This document records the local offline verification harness added in Phase 11 by commit `612d98b`.

The harness lives in `signal_agent/governed_authoring/offline_harness.py`. It is a local file-based verification adapter only. It does not add server code, browser-to-backend submission, production authoring artifact writes, default production canonical ledger writes, or production-governed UI behavior.

## Purpose

Phase 11 proves the covered offline packet loop:

```text
static export packet
-> backend Governed Authoring proof path
-> backend result/output manifest
-> static-import-compatible result packet
```

The harness can:

- Load static prototype export packets.
- Convert them into backend Governed Authoring inputs.
- Run the backend proof path.
- Emit static-import-compatible result packets.
- Optionally write canonical ledger entries only when a caller provides a path.

## Primary Files

Implementation:

- `signal_agent/governed_authoring/offline_harness.py`

Tests:

- `tests/test_governed_authoring_offline_harness.py`

Fixtures:

- `tests/fixtures/governed_authoring/static_export_valid_provisional.json`
- `tests/fixtures/governed_authoring/static_export_valid_approved.json`
- `tests/fixtures/governed_authoring/static_export_missing_evidence.json`
- `tests/fixtures/governed_authoring/static_export_blocking_tension.json`
- `tests/fixtures/governed_authoring/static_export_generator_self_approval.json`

## Covered Fixture Outcomes

| Fixture | Expected backend outcome | Static import outcome |
| --- | --- | --- |
| `static_export_valid_provisional.json` | `EMIT_PROVISIONAL_DRAFT` | provisional result |
| `static_export_valid_approved.json` | `APPROVE_OUTPUT` | approved result |
| `static_export_missing_evidence.json` | `REJECT_MISSING_EVIDENCE` | rejected result |
| `static_export_blocking_tension.json` | `DEFER_UNRESOLVED_TENSION` | deferred result |
| `static_export_generator_self_approval.json` | `REJECT_SELF_APPROVAL` | rejected result |
| temp canonical ledger path | temp-path append only | canonical entry id reflected in result |

## What Survives The Offline Loop

The Phase 11 tests prove preservation of:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Provisional, rejected, deferred, and approved output status.
- Canonical ledger entry id when an optional temp ledger path is supplied.

## What Is Proven

Phase 11 proves:

- Static export packets can be verified locally through the backend proof path.
- Backend result/output manifest packets can be produced for static import.
- The offline loop works without server code.
- The offline loop works without browser-to-backend submission.
- The offline loop works without production writes.
- Optional canonical ledger output can be constrained to temp paths.
- Production JSONL ledgers remain unchanged during harness tests.

## What Is Not Proven

Phase 11 does not prove:

- The static UI submits to the backend.
- A server/app surface exists.
- A production authoring artifact write path exists.
- A default production canonical authoring ledger write exists.
- The UI is production-governed.
- Repo-wide promotion governance is complete.

## Current Boundary

Safe wording:

"The offline packet loop is proven for covered fixtures."

"Static export packets can be verified locally through the backend proof path."

"The harness emits static-import-compatible result packets."

"No server, backend submission, or production writes are added."

Unsafe wording:

"The UI is backend-wired."

"The app is production-ready."

"The static prototype submits to the backend."

"Production authoring writes are governed."

"Repo-wide governance is complete."
