# v0.2 Architecture Decision Record

## Status

Proposed for v0.2 planning.

## Decision

Start v0.2 with a local command-router architecture over the existing v0.1 proof-pack paths.

Do not approve a local server yet.

Do not approve browser-backend submission yet.

Do not approve production writes.

## Context

v0.1 is complete as a verified local proof pack:

- Tag: `v0.1-local-proof-pack`
- Public release: `https://github.com/noblebrendon-cloud/signal_agent/releases/tag/v0.1-local-proof-pack`
- Safe claim: local proof pack for formal governance and covered Governed Authoring paths.

v0.2 should move toward a controlled local authoring surface while preserving:

- Local-only boundary.
- Explicit-path writes.
- No default production writes.
- No production UI/backend claim.
- No repo-wide governance claim.
- No complete IBVM claim.

## Alternatives Considered

### CLI-Only Continuation

Pros:

- Safest option.
- Reuses existing proof paths.
- Minimal boundary risk.

Cons:

- Less ergonomic.
- Does not substantially improve authoring workflow.

### Static UI Plus Manual Import/Export

Pros:

- Preserves static prototype boundary.
- Avoids server behavior.

Cons:

- Still manual.
- Limited workflow consolidation.

### Local Command Router

Pros:

- Improves local workflow without server behavior.
- Routes to existing proof paths.
- Keeps writes explicit and testable.
- Creates a clear next implementation target.

Cons:

- Requires careful command and path design.
- Could be over-described as an app if claims are not controlled.

### Local Server Surface

Pros:

- Better user experience later.
- Can support local browser workflows.

Cons:

- Higher UI/backend confusion risk.
- Higher write-boundary risk.
- Should not begin before explicit decision gates.

### Desktop/Local App Later

Pros:

- Could give a controlled local UX without public hosting.

Cons:

- Larger implementation surface.
- Packaging and authority model complexity.

## Rationale

The local command-router option has the best balance for v0.2. It moves beyond one-off CLI usage while avoiding the stronger boundary risks of a local server or browser-backend submission.

## Consequences

Phase 22 should design:

- Command names.
- Input packet types.
- Output directory rules.
- Optional ledger behavior.
- Forbidden path handling.
- Error behavior.
- Tests for no production writes.

Runtime implementation should wait until after Phase 22 and any necessary policy/spec phases.

## Non-Goals

This decision does not approve:

- Server code.
- Browser-backend submission.
- Production authoring artifact writes.
- Default production canonical ledger writes.
- Production Governed Authoring app claims.
- Repo-wide governance claims.
- Complete IBVM proof claims.
