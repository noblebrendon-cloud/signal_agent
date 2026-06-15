# Governed Authoring Static Export/Import

This document records the static prototype export/import patch added in Phase 9 by commit `feff458`.

The static prototype lives in `products/governed_authoring_studio/prototype_v1a/`. Phase 9 adds a local browser JSON exchange surface only. It does not add a server, call Python from the browser, submit to a backend, write production authoring artifacts, or enable production ledger writes.

## Purpose

Phase 9 closes the previous static-prototype packet exchange gap:

```text
Before:
The static prototype demonstrated workflow shape but could not exchange bridge-compatible packets.

After:
The static prototype can export and import bridge-compatible JSON packets.
```

The supported static flow is:

```text
static prototype state
-> bridge-compatible JSON export
-> offline/backend proof path outside the UI
-> backend output manifest or prototype result packet
-> static prototype JSON import
```

## What The Static UI Supports

The static prototype now supports:

- Exporting backend-compatible governed authoring JSON packets.
- Importing backend result/output manifest packets.
- Preserving evidence refs.
- Preserving unresolved tensions.
- Preserving review status.
- Preserving provisional, rejected, deferred, and approved output status.
- Flagging publication-ready packets that lack evidence refs.
- Flagging generator/model self-approval.

Primary files:

- `products/governed_authoring_studio/prototype_v1a/app.js`
- `products/governed_authoring_studio/prototype_v1a/index.html`
- `products/governed_authoring_studio/prototype_v1a/prototype_bridge_static.js`
- `products/governed_authoring_studio/prototype_v1a/README.md`
- `tests/test_governed_authoring_static_export_import.py`

## What Is Proven

The Phase 9 tests prove:

- Static export packet shape matches the documented bridge contract.
- Imported backend result packets can be parsed into prototype-readable fields.
- Evidence refs survive export/import.
- Unresolved tensions survive export/import.
- Review status survives export/import.
- Output status survives export/import.
- Missing evidence is flagged.
- Generator self-approval is flagged.
- No server, network, or backend submission behavior was added.
- No production writes were added.
- Production JSONL ledgers remain unchanged during the static export/import tests.

## Browser Verification Limitation

The in-app browser could not verify direct `file://` interaction because browser policy blocked direct local-file navigation.

That means the current evidence proves packet shape and static JavaScript behavior through tests, but does not prove full interactive browser behavior under `file://`.

This is a verification limitation, not evidence of backend wiring. Do not treat the static UI as production-governed because these tests pass.

## What Is Not Proven

Phase 9 does not prove:

- The static prototype submits to a backend.
- A server/app surface exists.
- A production authoring artifact write path exists.
- Production canonical authoring ledger writes are enabled by default.
- The UI is production-governed.
- All authoring outputs are governed.
- Repo-wide promotion governance is complete.

## Current Safe Boundary

Safe wording:

"The static prototype can export and import bridge-compatible JSON packets."

"The prototype remains non-production."

"No backend submission occurs from the static UI."

"No production writes occur from the static UI."

"Backend proof exists separately for covered Governed Authoring decisions."

Unsafe wording:

"The UI is backend-governed."

"The app is production-ready."

"The prototype submits to the backend."

"All authoring outputs are governed."

"Repo-wide governance is complete."
