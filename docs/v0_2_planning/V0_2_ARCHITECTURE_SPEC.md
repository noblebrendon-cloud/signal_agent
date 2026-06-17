# v0.2 Architecture Spec

Version target:

```text
v0.2-local-authoring-surface
```

## Architecture Purpose

v0.2 defines a controlled local authoring surface over the covered v0.1 proof-pack paths.

The architecture should make the local Governed Authoring workflow easier to run without crossing into production claims. It must remain local, non-production, explicit-path only, and bounded to covered paths.

## Baseline Proof Paths

v0.2 starts from the v0.1 proof pack:

- Offline harness.
- Local offline CLI.
- Demo proof bundle.
- Static export/import.
- Governed Authoring backend proof path.
- Explicit-path canonical ledger behavior.

The v0.1 public release remains:

```text
v0.1-local-proof-pack verifies a local proof pack for formal governance and covered Governed Authoring paths.
```

## Recommended Architecture

The safest next architecture is:

```text
local command-router over existing proof-pack paths
```

This means v0.2 should first design a local command interface that routes explicit local inputs to already-proven proof surfaces:

```text
source/static packet
-> local command router
-> offline harness or CLI
-> explicit output directory
-> result packet, proof summary, optional explicit ledger
```

## Deferred Architectures

Do not approve these yet:

- Local server surface.
- Browser-backend submission.
- Production writes.
- Default canonical ledger writes.
- Production-governed UI.

These can be reconsidered only after the local command-router contract and write boundary are specified and tested.

## Architecture Options Summary

| Option | Recommendation |
| --- | --- |
| CLI-only continuation | Safe fallback, but less ergonomic. |
| Static UI plus manual import/export | Keep available as a non-server bridge. |
| Local command router | Recommended for v0.2. |
| Local server surface | Defer until after explicit decision gate. |
| Desktop/local app later | Defer; useful later but larger surface area. |

## Local Authority Model

v0.2 should represent local review without claiming production identity or real authority integration.

The model must distinguish:

- Local reviewer marker.
- Review status.
- Evidence refs.
- Output status.
- Unresolved tensions.
- Generator/model self-certification rejection.

A local reviewer marker is a local proof/workflow field only. It is not a production user identity, authentication source, or legal authority record.

## Write Boundary Model

Allowed writes:

- Explicit caller-selected output directory.
- Temp output directories.
- Explicit optional ledger path outside repo `data/`.
- Local proof summaries.
- Static-import-compatible result packets.

Forbidden writes:

- Repo `data/` writes.
- Production authoring artifact writes.
- Default canonical ledger writes.
- Implicit output paths.
- Overwriting known outputs without explicit policy.

## Runtime Decision Gates

Before runtime implementation, v0.2 must answer:

- Is v0.2 CLI-only or command-router first?
- Is local server work deferred?
- Is browser-backend submission deferred?
- What output directories are allowed?
- What paths are forbidden?
- Is ledger writing disabled by default?
- How is local human authority represented?
- How is self-certification blocked?
- What tests must prove no production writes?

## Non-Goals

v0.2 architecture does not prove:

- Production Governed Authoring app.
- Backend-wired production UI.
- Public hosted app.
- Production artifact store.
- Default production canonical ledgers.
- Repo-wide governance.
- All state mutations gated.
- Complete IBVM proof.

## Recommended Phase 22

Phase 22 should be:

```text
Local-only command router design.
```

It should design command names, inputs, outputs, error handling, forbidden path behavior, and tests before runtime implementation.
