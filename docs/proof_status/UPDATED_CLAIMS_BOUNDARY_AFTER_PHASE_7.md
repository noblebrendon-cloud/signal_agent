# Updated Claims Boundary After Phase 7

This document updates the claims boundary after commit `51e32a1`.

## Allowed Language

The following statements are now supported:

- "Governed Authoring has a backend proof path for covered decisions."
- "A minimal bridge now aligns static prototype packet shapes with the backend proof path."
- "The bridge preserves evidence refs, tensions, review state, and output status."
- "The bridge can flag publication-ready packets without evidence."
- "The bridge can flag generator/model self-approval."
- "The static prototype remains a non-production UI surface."

## Disallowed Language

Do not claim:

- "The app is wired."
- "Governed Authoring is production-ready."
- "The full UI is backend-governed."
- "All authoring outputs are governed."
- "Repo-wide promotion governance is complete."
- "Production canonical authoring ledger writes are enabled by default."
- "The prototype has a server backend."

## Current Safe Summary

Use:

```text
Governed Authoring now has a backend proof path for covered source-packet-to-output decisions, plus a minimal bridge that aligns static prototype packet shapes with that backend path.

The static prototype UI remains non-production and is not wired to a production backend.
No production authoring artifact write path has been added.
Repo-wide governance is not proven.
```

## Boundary By Surface

| Surface | Current claim |
| --- | --- |
| Backend runtime | Covered Governed Authoring decisions are executable and tested. |
| Prototype bridge | Prototype-style packets can be converted to backend packets and backend manifests can be converted to prototype-readable results. |
| Static prototype UI | Still a local/static UI demonstration; not backend-wired yet. |
| Production ledgers | Not modified by bridge tests; canonical authoring writes remain optional/configured. |
| Repo-wide governance | Not proven. |

## Publication-Safe Phrase

"A backend proof path and prototype-compatible packet bridge now exist for Governed Authoring covered decisions."

This is safer than:

"Governed Authoring is implemented."
