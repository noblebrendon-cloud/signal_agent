# Updated Claims Boundary After Phase 13

This document updates the claims boundary after commit `5ee82a0`.

## Allowed Language

The following statements are now supported:

- "A local CLI can verify static export packets through the backend proof path."
- "The CLI writes static-import-compatible result JSON."
- "Canonical ledger output is optional and explicit-path only."
- "No server, browser-backend submission, or production writes are added."
- "Evidence refs, unresolved tensions, review status, and output status survive CLI execution."

## Disallowed Language

Do not claim:

- "The UI is backend-wired."
- "The app is production-ready."
- "The prototype submits to the backend."
- "Production authoring writes are governed."
- "Repo-wide governance is complete."
- "Default production canonical authoring ledger writes are enabled."
- "The UI is production-governed."

## Current Safe Summary

Use:

```text
Governed Authoring now has a backend proof path, a prototype packet bridge, static JSON export/import, a local offline harness for fixture verification, and a local CLI that verifies static export packets through the backend proof path and writes static-import-compatible result JSON.

The static UI still does not submit to a backend.
No server/app surface exists.
No production authoring artifact write path exists.
No production canonical authoring ledger write is enabled by default.
The UI is still not production-governed.
Repo-wide governance is not proven.
```

## Boundary By Surface

| Surface | Current claim |
| --- | --- |
| Backend runtime | Covered Governed Authoring decisions are executable and tested. |
| Python prototype bridge | Prototype-style packets can be converted to backend packets and backend manifests can be converted to prototype-readable results. |
| Static prototype UI | Can export/import bridge-compatible JSON packets; remains local/static and non-production. |
| Offline harness | Can verify covered static export fixtures through the backend proof path and emit static-import-compatible result packets. |
| Offline CLI | Can verify static export JSON files locally and write static-import-compatible result JSON files. |
| Optional canonical ledger | Can be written only to an explicit caller-provided path; no default production write is enabled. |
| Production ledgers | Not modified by offline CLI tests. |
| Production authoring artifacts | No production write path exists. |
| Repo-wide governance | Not proven. |

## Publication-Safe Phrase

"A local CLI can verify static export packets through the backend proof path and emit static-import-compatible result JSON while preserving non-production boundaries."

This is safer than:

"The static prototype is connected to Governed Authoring."
