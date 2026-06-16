# Updated Claims Boundary After Phase 11

This document updates the claims boundary after commit `612d98b`.

## Allowed Language

The following statements are now supported:

- "The offline packet loop is proven for covered fixtures."
- "Static export packets can be verified locally through the backend proof path."
- "The harness emits static-import-compatible result packets."
- "No server, backend submission, or production writes are added."
- "Optional canonical ledger output can be constrained to temp paths."
- "Evidence refs, unresolved tensions, review status, and output status survive the offline loop."

## Disallowed Language

Do not claim:

- "The UI is backend-wired."
- "The app is production-ready."
- "The static prototype submits to the backend."
- "Production authoring writes are governed."
- "Repo-wide governance is complete."
- "Default production canonical authoring ledger writes are enabled."
- "The UI is production-governed."

## Current Safe Summary

Use:

```text
Governed Authoring now has a backend proof path, a prototype packet bridge, static JSON export/import, and a local offline harness that verifies covered static export fixtures through the backend proof path.

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
| Optional canonical ledger | Can be written to caller-provided temp paths in tests; no default production write is enabled. |
| Production ledgers | Not modified by offline harness tests. |
| Production authoring artifacts | No production write path exists. |
| Repo-wide governance | Not proven. |

## Publication-Safe Phrase

"The local offline harness proves the static-export to backend-result packet loop for covered fixtures while preserving non-production boundaries."

This is safer than:

"The static prototype is connected to Governed Authoring."
