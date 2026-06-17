# v0.2 Router Test Plan

Version target:

```text
v0.2-local-authoring-surface
```

## Purpose

This document defines tests a future local command-router implementation must pass. It is a design artifact only.

## Path Safety Tests

Future tests must prove:

- Command validates allowed temp output directory.
- Command rejects repo `data/` output directory.
- Command rejects implicit production ledger path.
- Command rejects optional canonical ledger path under repo `data/`.
- Command fails closed when path classification is ambiguous.
- Known outputs are not overwritten by default.

## Routing Tests

Future tests must prove:

- Static export packet can route to result packet.
- Backend-compatible source packet can route through covered proof path.
- Demo bundle can route to temp output directory.
- Inspect command can read a static-import-compatible result packet.
- Summary command can produce a local proof summary.

## Ledger Tests

Future tests must prove:

- Optional canonical ledger writes only to explicit temp path.
- Ledger writes are disabled by default.
- Ledger write is skipped on validation failure.
- Production JSONL fingerprint remains unchanged.

## Governance Preservation Tests

Future tests must prove:

- Evidence refs survive.
- Unresolved tensions survive.
- Review status survives.
- Output status survives.
- Local reviewer marker is preserved when supplied.
- Generator/model self-certification is rejected.
- Missing evidence for approval-ready output is rejected.
- Blocking unresolved tension defers or blocks approval.

## Server And Network Tests

Future tests must prove:

- No server behavior is introduced.
- No network behavior is introduced.
- No browser-backend submission is introduced.

Suggested static scan tokens:

- `http.server`
- `socket`
- `requests`
- `urllib`
- `FastAPI`
- `Flask`
- `fetch(`
- `WebSocket`
- `EventSource`

## Command Result Tests

Future tests must prove:

- Success returns `0`.
- Missing input returns nonzero.
- Invalid JSON returns nonzero.
- Unsupported packet shape returns nonzero.
- Forbidden path returns nonzero.
- Governance rejection/defer returns nonzero or explicit governed status.

## Regression Tests

Future router implementation should run alongside existing v0.1 proof-pack tests:

- Formal governance proof-pack tests.
- Governed Authoring backend tests.
- Prototype bridge tests.
- Static export/import tests.
- Offline harness tests.
- Offline CLI tests.
- Demo bundle tests.

## Non-Goals

This test plan does not prove:

- Production app readiness.
- Backend-wired production UI.
- Repo-wide governance.
- Complete IBVM proof.
