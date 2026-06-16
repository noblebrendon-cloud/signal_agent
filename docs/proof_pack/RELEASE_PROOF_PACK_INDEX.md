# Release Proof Pack Index

This local proof pack consolidates the formal governance and Governed Authoring proof chain through commit `4ff755d`.

It is a documentation and manifest layer only. It does not change runtime behavior, production ledgers, server surfaces, UI backend wiring, or production authoring writes.

## Proof Pack Scope

The current proof pack covers:

- Isolated formal governance proof pack V0.
- Claim evidence enforcement in the active claim runtime.
- HQ promotion separation for the covered capture promotion path.
- Canonical governed-transition ledger adapter.
- Operator canonical governed-transition ledger linkage for covered operator decisions.
- Governed Authoring backend proof path for covered source-packet-to-output decisions.
- Governed Authoring prototype packet bridge.
- Static prototype export/import of bridge-compatible JSON packets.
- Offline Governed Authoring harness.
- Local offline CLI for static export verification.
- Local demo proof bundle for representative fixtures.

## Index Files

- `docs/proof_pack/PROOF_CHAIN.md`
- `docs/proof_pack/TEST_COMMANDS.md`
- `docs/proof_pack/DEMO_COMMANDS.md`
- `docs/proof_pack/SAFE_CLAIMS.md`
- `docs/proof_pack/BOUNDARIES_AND_GAPS.md`
- `docs/proof_pack/COMMIT_SCOPE_GUIDE.md`

## Supporting Proof-Status Docs

- `docs/proof_status/CURRENT_PROOF_STATUS.md`
- `docs/proof_status/UPDATED_EXECUTABLE_PROOF_MATRIX.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY.md`
- `docs/proof_status/PHASE_1_TO_5_CHANGELOG.md`
- `docs/proof_status/NEXT_INTEGRATION_PLAN.md`
- `docs/proof_status/PHASE_7_BRIDGE_UPDATE.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY_AFTER_PHASE_7.md`
- `docs/proof_status/NEXT_IMPLEMENTATION_BOUNDARY_AFTER_PHASE_7.md`
- `docs/proof_status/PHASE_9_STATIC_EXPORT_IMPORT_UPDATE.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY_AFTER_PHASE_9.md`
- `docs/proof_status/NEXT_IMPLEMENTATION_BOUNDARY_AFTER_PHASE_9.md`
- `docs/proof_status/PHASE_11_OFFLINE_HARNESS_UPDATE.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY_AFTER_PHASE_11.md`
- `docs/proof_status/NEXT_IMPLEMENTATION_BOUNDARY_AFTER_PHASE_11.md`
- `docs/proof_status/PHASE_13_OFFLINE_CLI_UPDATE.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY_AFTER_PHASE_13.md`
- `docs/proof_status/NEXT_IMPLEMENTATION_BOUNDARY_AFTER_PHASE_13.md`
- `docs/proof_status/PHASE_15_DEMO_PROOF_BUNDLE_UPDATE.md`
- `docs/proof_status/UPDATED_CLAIMS_BOUNDARY_AFTER_PHASE_15.md`
- `docs/proof_status/NEXT_IMPLEMENTATION_BOUNDARY_AFTER_PHASE_15.md`

## Governed Authoring Docs

- `docs/governed_authoring/PROTOTYPE_BRIDGE.md`
- `docs/governed_authoring/PROTOTYPE_PACKET_CONTRACT.md`
- `docs/governed_authoring/STATIC_EXPORT_IMPORT.md`
- `docs/governed_authoring/OFFLINE_HARNESS.md`
- `docs/governed_authoring/OFFLINE_CLI.md`
- `docs/governed_authoring/DEMO_PROOF_BUNDLE.md`

## Current Safe Summary

The repository contains an isolated formal-governance proof pack and several selected runtime integrations. Governed Authoring now has a backend proof path, prototype packet bridge, static export/import, offline harness, offline CLI, and repeatable local demo proof bundle for covered fixtures.

The proof pack remains bounded. It does not prove a production Governed Authoring app, backend-wired UI, server/app surface, production authoring artifact writes, default production canonical ledger writes, repo-wide governance, universal state-mutation gating, or complete IBVM proof across every path.

## Next Recommended Phase

The next safe phase is a documentation-only release checklist or proof-pack review pass that verifies this index against the current commit set before any production wiring is attempted.
