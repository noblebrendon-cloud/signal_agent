# Boundaries And Gaps

This file defines what the proof pack does not claim yet.

## Not Proven

The current proof pack does not prove:

- Production Governed Authoring app.
- Backend-wired UI.
- Server/app surface.
- Browser-backend submission.
- Production authoring artifact writes.
- Default production canonical authoring ledger writes.
- Repo-wide governance.
- All state-mutating paths gated.
- Universal self-certification prevention.
- Complete IBVM proof across every path.

## Governed Authoring Boundary

Proven:

- Covered backend source-packet-to-output decisions.
- Prototype packet bridge.
- Static export/import packet compatibility.
- Offline harness verification for representative fixtures.
- Local CLI verification of static export packets.
- Local demo proof bundle for representative fixtures.

Not proven:

- Hosted or production app behavior.
- Static UI backend submission.
- Production authoring artifact persistence.
- Production canonical authoring ledger policy.
- Real user identity and authority integration for production authoring.

## Ledger Boundary

Proven:

- Canonical governed-transition ledger adapter exists.
- Covered claim, HQ promotion, operator, and Governed Authoring paths can use canonical entries when configured.
- Offline CLI and demo-bundle ledger writes are explicit-path only.

Not proven:

- Default production canonical ledger writes for Governed Authoring.
- A single production ledger replacing all subsystem ledgers.
- Ledger coverage for every repository mutation path.

## Promotion Boundary

Proven:

- Covered HQ capture promotion path separates governed decision from promoted artifact writes.

Not proven:

- Every promotion path uses this separation.
- All artifact admission and state promotion paths are globally governed.

## Claim Boundary

Proven:

- Active claim runtime rejects missing evidence for anchored/publication-ready claims in the covered path.
- Generator/model/self-certified evidence is rejected in covered claim evidence tests.

Not proven:

- Every claim-like object in the repository uses this active claim runtime.
- Every publication or promotion path is routed through the same evidence gate.

## Remaining Work

Future implementation should keep separating:

- Local proof surfaces from production write paths.
- Optional ledger output from default production ledger policy.
- Static packet exchange from backend-wired UI behavior.
- Covered runtime paths from repo-wide governance.
