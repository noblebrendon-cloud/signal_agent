# Updated Claims Boundary After Phase 15

This document updates the claims boundary after commit `c1ab877`.

## Allowed Language

The following statements are now supported:

- "The local demo proof bundle is repeatable for covered fixtures."
- "The demo bundle writes proof outputs only to a chosen output directory."
- "The demo bundle refuses repo data/ output paths."
- "The demo bundle can optionally write a canonical ledger file inside the chosen output directory only."
- "The demo bundle generates `proof_summary.md` and static-import-compatible fixture result JSON packets."
- "No server, browser-backend submission, production writes, or default production ledger writes are added."

## Disallowed Language

Do not claim:

- "The UI is backend-wired."
- "The app is production-ready."
- "The prototype submits to the backend."
- "Production authoring writes are governed."
- "Default production canonical authoring ledger writes are enabled."
- "The UI is production-governed."
- "Repo-wide governance is complete."

## Current Safe Summary

Use:

```text
Governed Authoring now has a backend proof path, a prototype packet bridge, static JSON export/import, a local offline harness, a local offline CLI, and a repeatable local demo proof bundle for covered fixtures.

The demo proof bundle writes result packets and proof_summary.md only to a chosen output directory.
Optional canonical ledger output is explicit and confined to the chosen output directory.
The command refuses repo data/ output paths.

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
| Demo proof bundle | Can run representative fixtures and produce local result packets plus `proof_summary.md`. |
| Optional canonical ledger | Can be written only to an explicit caller/demo output path; no default production write is enabled. |
| Production ledgers | Not modified by demo bundle tests or temp demo run. |
| Production authoring artifacts | No production write path exists. |
| Repo-wide governance | Not proven. |

## Publication-Safe Phrase

"A local demo proof bundle can run covered Governed Authoring static export fixtures through the offline proof path and produce local result packets plus a proof summary while preserving non-production boundaries."

This is safer than:

"Governed Authoring is now a production-governed app."
