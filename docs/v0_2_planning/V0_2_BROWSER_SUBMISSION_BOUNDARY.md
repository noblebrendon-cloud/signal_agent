# v0.2 Browser Submission Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Boundary Purpose

This document defines the v0.2 browser submission boundary.

It is documentation/decision only. It does not wire the static prototype to a backend, add browser-to-server behavior, add server code, create production writes, or enable default canonical ledger writes.

## Current Decision

Browser-backend submission is not approved yet.

Manual static import/export remains allowed.

CLI/router execution remains allowed.

Browser-to-Python or browser-to-server submission remains deferred.

## Allowed Browser-Adjacent Behavior

Allowed:

- Static prototype manual export of bridge-compatible JSON packets.
- Static prototype manual import of backend result packets.
- Local file inspection by the user.
- CLI/router execution on explicitly selected local files.
- Documentation that explains manual packet exchange boundaries.

## Deferred Browser Behavior

Deferred:

- Browser-to-Python submission.
- Browser-to-local-server submission.
- Browser-to-production-backend submission.
- Automatic browser-triggered ledger writes.
- Automatic browser-triggered result writes.
- Browser-originated production authoring artifact writes.

## Forbidden Claims

Do not claim:

- The static UI is backend-wired.
- The browser submits to a backend.
- The UI is production-governed.
- Browser actions create production authoring artifacts.
- Browser actions append production ledgers.
- All authoring through the UI is governed.

## Manual Packet Boundary

Manual packet exchange remains the safe v0.2 browser-adjacent path:

```text
static export packet
-> local CLI/router execution
-> local result packet
-> static manual import
```

This path is local, explicit-file, non-production, and user-mediated.

It does not create a production app surface.

## Future Approval Requirements

Before browser submission can be approved later, the repo must have:

- Command router implemented and tested.
- Path classification implemented and tested.
- Output directory policy tests.
- Production JSONL fingerprint test.
- No default ledger write test.
- Authority marker test.
- Self-certification rejection test.
- Explicit local-only network policy.
- Explicit authentication/session boundary.
- Explicit browser submission design.
- Explicit server boundary if a local server is involved.

## Phase 26 Boundary

Phase 26 must not add browser submission.

Phase 26 may only implement local command-router runtime foundations over explicit files and explicit output paths.

## Safe Claim

Use:

```text
v0.2 preserves manual static import/export while deferring browser-backend submission.
```

Do not use:

```text
v0.2 wires the browser UI to the backend.
```
