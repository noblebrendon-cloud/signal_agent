# Updated Claims Boundary After Phase 9

This document updates the claims boundary after commit `feff458`.

## Allowed Language

The following statements are now supported:

- "The static prototype can export and import bridge-compatible JSON packets."
- "The prototype remains non-production."
- "No backend submission occurs from the static UI."
- "No production writes occur from the static UI."
- "Backend proof exists separately for covered Governed Authoring decisions."
- "The static export/import tests prove packet shape and static behavior."
- "The static export/import surface preserves evidence refs, unresolved tensions, review status, and output status."
- "The static export/import surface flags missing evidence for publication-ready packets."
- "The static export/import surface flags generator/model self-approval."

## Disallowed Language

Do not claim:

- "The UI is backend-governed."
- "The app is production-ready."
- "The prototype submits to the backend."
- "All authoring outputs are governed."
- "Repo-wide governance is complete."
- "A production authoring artifact write path exists."
- "Production canonical authoring ledger writes are enabled by default."
- "The browser interaction under `file://` has been fully verified."

## Current Safe Summary

Use:

```text
Governed Authoring has a backend proof path for covered source-packet-to-output decisions.

The static prototype can export and import bridge-compatible JSON packets.
The static prototype remains non-production.
No backend submission occurs from the static UI.
No production writes occur from the static UI.
Repo-wide governance is not proven.
```

## Boundary By Surface

| Surface | Current claim |
| --- | --- |
| Backend runtime | Covered Governed Authoring decisions are executable and tested. |
| Python prototype bridge | Prototype-style packets can be converted to backend packets and backend manifests can be converted to prototype-readable results. |
| Static prototype UI | Can export/import bridge-compatible JSON packets; remains local/static and non-production. |
| Browser interaction | Direct `file://` interaction was not verified because browser policy blocked local-file navigation. |
| Production ledgers | Not modified by static export/import tests; canonical authoring writes remain optional/configured. |
| Production authoring artifacts | No production write path exists. |
| Repo-wide governance | Not proven. |

## Publication-Safe Phrase

"The static Governed Authoring prototype can exchange bridge-compatible JSON packets while remaining non-production and offline."

This is safer than:

"The UI is wired to Governed Authoring."
