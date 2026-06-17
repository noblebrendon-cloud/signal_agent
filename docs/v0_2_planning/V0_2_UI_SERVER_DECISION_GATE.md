# v0.2 UI/Server Decision Gate

Version target:

```text
v0.2-local-authoring-surface
```

## Context

`v0.1-local-proof-pack` is complete, tagged, pushed, and released as a GitHub prerelease.

The v0.2 planning sequence has established:

- Phase 20: v0.2 planning package.
- Phase 21: local authoring surface architecture spec.
- Phase 22: local-only command router design.
- Phase 23: local file workspace contract.
- Phase 24: explicit output directory policy.

Current direction:

- Start with a local command-router architecture over existing proof-pack paths.
- Use caller-selected local workspaces.
- Keep all writes explicit-path, local, non-production, and outside repo `data/`.
- Do not implement router runtime unless a decision gate approves the next phase.

## Decision Summary

Decision:

- Local server work: deferred.
- Browser-backend submission: deferred.
- Production writes: forbidden.
- Backend-wired UI claim: forbidden.
- Next allowed runtime work: local command router with fail-closed path classification.

This decision keeps v0.2 local, non-production, explicit-path, and command-router first.

## Options Considered

| Option | Proof value | Implementation complexity | Boundary risk | Write safety risk | Claim inflation risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| Continue CLI-only | Preserves existing offline proof-pack behavior with minimal new surface. | Low. | Low. | Low. | Low. | Safe fallback, but does not improve workflow ergonomics enough for v0.2. |
| Implement local command router | Adds a controlled local interface over proven offline paths and validates output boundaries. | Medium. | Medium-low if bounded by Phase 24 policies. | Medium-low with fail-closed path classification. | Medium-low if claims remain local and non-production. | Recommended next runtime phase. |
| Add local server | Could support future UI interaction after router safety exists. | High. | High because it may look like a production backend. | High unless path policy, authority, and session boundaries are already tested. | High because it can imply backend-wired UI. | Defer. |
| Add browser-backend submission | Could reduce manual export/import later. | High. | High because it changes the static prototype boundary. | High because browser-originated writes need stronger gating. | High because it can imply production UI governance. | Defer. |
| Build desktop/local app later | Could create a polished local surface after command-router maturity. | High. | Medium-high. | Medium-high. | Medium-high. | Reconsider after router and server decisions are proven. |

## Rationale

The strongest next step is a local command-router runtime foundation because it directly implements the planning policies already created:

- Explicit workspace validation.
- Explicit output directory validation.
- Forbidden path rejection.
- Optional ledger path validation.
- No default production writes.
- No server or browser submission behavior.

A local server or browser submission path would introduce new authority, session, network, and UI-claim risks before the write-boundary runtime exists.

## Browser Submission Boundary

Browser-backend submission is not approved yet.

Allowed:

- Manual static export/import.
- CLI/router execution.
- Local file packets.
- Explicit output directories.

Deferred:

- Browser-to-Python submission.
- Browser-to-local-server submission.
- Browser-to-production-backend submission.
- Automatic UI-triggered writes.

## Runtime Allowed Scope For Phase 26

Phase 26 may allow only:

- Local command-router implementation.
- Path classification implementation.
- Forbidden path rejection.
- Explicit workspace validation.
- Explicit output directory validation.
- Optional ledger path validation.
- Focused tests proving no production writes.
- No network/server behavior.

## Runtime Forbidden Scope For Phase 26

Phase 26 must forbid:

- Server code.
- HTTP endpoints.
- Browser-backend submission.
- Websocket behavior.
- Hosted app behavior.
- Production authoring artifact writes.
- Default canonical ledger writes.
- Writes under repo `data/`.
- Production-governed UI claims.

## Preconditions For Future Local Server Work

Before local server work can be approved in a later phase, the repo must have:

- Command router implemented and tested.
- Path classification tested.
- Output policy tested.
- Production JSONL fingerprint test.
- Authority model test.
- No self-certification test.
- Explicit server boundary document.
- Explicit local-only network policy.
- Explicit decision on browser submission.
- Explicit decision on authentication/session boundary.

## Phase 26 Decision

Recommended Phase 26:

```text
Local command-router runtime foundation.
```

Scope:

- Implement path classification.
- Implement workspace validation.
- Implement command-router skeleton over existing offline proof paths.
- Add focused tests for allowed and forbidden output behavior.
- Do not add a server.
- Do not wire browser UI.
- Do not create production writes.
- Do not enable default production ledger writes.

## Safe Claims

Allowed after Phase 25:

- "v0.2 decision gate defers local server and browser-backend submission."
- "The next runtime phase is limited to local command-router foundations."
- "v0.2 remains local and non-production."

Disallowed after Phase 25:

- "v0.2 has a backend-wired UI."
- "v0.2 includes a local server."
- "v0.2 is production-ready."
- "Browser submission is implemented."
- "Production authoring writes are governed."

## Non-Goals

This decision gate does not approve:

- Production Governed Authoring app behavior.
- Backend-wired UI.
- Server code.
- Browser-backend submission.
- Production authoring artifact writes.
- Default production canonical ledgers.
- Repo-wide governance.
- Complete IBVM proof.
