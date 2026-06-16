# Safe Claims

This file defines publication-safe claims supported by the current proof chain through commit `4ff755d`.

## Supported Claims

The following statements are supported by committed files, tests, and documentation:

- "The repo contains an isolated formal-governance proof pack V0."
- "Selected runtime paths integrate formal-governance decisions."
- "Active claim runtime enforces evidence for anchored/publication-ready claims."
- "HQ promotion separates governed decision from promoted artifact writes for the covered path."
- "Canonical governed-transition ledger entries are available for covered claim, HQ promotion, operator, and Governed Authoring decisions when configured."
- "Governed Authoring has a backend proof path for covered source-packet-to-output decisions."
- "The static prototype can export/import bridge-compatible JSON packets."
- "A local offline harness and CLI can verify static export packets through the backend proof path."
- "A local demo proof bundle can produce repeatable proof outputs for covered fixtures."

## Safer Expanded Summary

Use:

```text
The repository contains an isolated formal-governance proof pack plus selected runtime integrations. Governed Authoring has a covered backend proof path, prototype packet bridge, static JSON export/import, offline harness, local CLI, and repeatable local demo proof bundle.
```

Also use:

```text
These proof surfaces are bounded to covered paths and local proof commands. They do not establish production app behavior or repo-wide governance.
```

## Claims Requiring Care

Allowed with qualifiers:

- "Canonical ledger entries are available when configured for covered paths."
- "The demo bundle can write an optional canonical ledger inside the chosen output directory."
- "The static prototype can exchange bridge-compatible JSON packets."

Avoid dropping the qualifiers "when configured", "covered paths", "optional", "local", and "non-production".

## Unsupported Claims

Do not claim:

- "Governed Authoring is production-ready."
- "The static UI is backend-wired."
- "The prototype submits to the backend."
- "Production authoring writes are governed."
- "Default production canonical authoring ledger writes are enabled."
- "Repo-wide governance is complete."
- "All state-mutating paths are gated."
- "Universal self-certification prevention is proven."
- "Complete IBVM proof exists across every path."
