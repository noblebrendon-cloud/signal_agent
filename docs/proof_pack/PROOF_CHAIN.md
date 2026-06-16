# Proof Chain

This file records the formal governance and Governed Authoring proof chain through commit `4ff755d`.

| Commit | Gap closed | What it proved | Still out of scope |
| --- | --- | --- | --- |
| `0314eda` Add isolated formal governance proof pack V0 | No isolated proof surface for governed transitions. | Formal governance primitives, decisions, ledger behavior, and CLI proof pack existed as an isolated executable surface. | Runtime integrations and repo-wide governance. |
| `1f864f3` Enforce evidence requirements for active claim runtime | Active claim runtime allowed empty evidence refs. | Anchored and publication-ready claims require non-empty evidence refs in the covered claim path. | Repo-wide promotion governance and every state-mutating path. |
| `8ae5b32` Separate HQ promotion decision from promoted artifact writes | HQ promotion wrote promoted bundle artifacts before governed decision success. | Covered HQ capture promotion path separates governed decision from promoted artifact materialization. | Other promotion paths and global promotion governance. |
| `34ad079` Add canonical governed-transition ledger adapter | No normalized canonical transition ledger row for covered subsystem decisions. | Canonical governed-transition entries can link subsystem evidence when configured. | Replacement of historical subsystem ledgers or default production ledger writes. |
| `161e9da` Add operator canonical governed-transition ledger linkage | Operator runtime had subsystem evidence without canonical transition linkage. | Covered operator decisions can emit canonical entries when explicitly configured. | Governed Authoring and repo-wide operator coverage. |
| `c2a993c` Add governed authoring backend proof path | Governed Authoring was a static/localStorage workflow demonstration only. | Covered source-packet-to-output decisions run through backend schemas, runtime decisions, manifests, tests, and optional canonical ledger entries. | Full app surface, UI backend wiring, production artifact writes. |
| `9a56449` Update proof status after formal governance integrations | Claims docs lagged runtime proof state after Phases 1-5. | Proof docs aligned with evidence after backend integrations. | UI bridge, static exchange, offline proof loop. |
| `51e32a1` Add minimal Governed Authoring prototype bridge | Static prototype packet shape was not aligned with backend proof path. | Prototype-style packets can convert to backend packets and backend manifests can convert to prototype-readable results. | UI rewrite, server wiring, production writes. |
| `3a5e50e` Document Governed Authoring prototype bridge boundary | Bridge boundary was not documented. | Safe bridge claims and unsupported claims were documented. | Static export/import behavior and backend submission. |
| `feff458` Add static Governed Authoring packet export and import | Static prototype could not exchange backend-compatible packets. | Static prototype can export and import bridge-compatible JSON packets. | Browser-backend submission and production-governed UI behavior. |
| `91c8d2d` Document static Governed Authoring export/import boundary | Static export/import proof status was undocumented. | Non-production export/import boundary was documented. | Server/app surface and production writes. |
| `612d98b` Add offline Governed Authoring packet verification harness | No fixture-driven local exchange loop through backend proof path. | Static export fixtures can run through the backend proof path and emit static-import-compatible results. | CLI wrapper, server behavior, production writes. |
| `c7f4e01` Document offline Governed Authoring harness boundary | Offline harness boundary was undocumented. | Harness claims, fixture outcomes, and exclusions were documented. | CLI, proof bundle, production app behavior. |
| `5ee82a0` Add local Governed Authoring offline verification CLI | No local command accepted static export JSON and wrote static-import-compatible result JSON. | Local CLI verifies static export packets through backend proof path. | Server, browser submission, production writes. |
| `7b88f75` Document local Governed Authoring offline CLI boundary | CLI proof boundary was undocumented. | CLI behavior, optional explicit ledger path, and non-production boundary were documented. | Proof bundle and production app behavior. |
| `c1ab877` Add local Governed Authoring demo proof bundle | No repeatable local proof-bundle command for representative fixtures. | Demo command writes local result packets and `proof_summary.md`; optional ledger stays inside chosen output dir. | Server, browser submission, production writes, default production ledgers. |
| `4ff755d` Document Governed Authoring demo proof bundle boundary | Demo bundle proof status was undocumented. | Phase 15 behavior, safe claims, and next proof-pack boundary were documented. | Release proof-pack consolidation and production wiring. |

## Chain Summary

The proof chain moves from isolated formal proof surface to selected runtime integrations, then into Governed Authoring backend proof, static packet exchange, offline verification, CLI execution, and repeatable local proof-bundle generation.

It is not a claim of complete repo-wide governance.
