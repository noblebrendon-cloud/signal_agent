# Current Proof Status After Phases 1-5

Date: 2026-06-15

This document records the current proof boundary after the committed implementation chain from the isolated formal governance proof pack through the Governed Authoring backend proof path.

## Commit Chain

| Commit | Phase | Proof movement |
| --- | --- | --- |
| `0314eda` | Formal governance proof pack V0 | Added typed formal primitives, decision gates, canonical ledger schema, fixtures, and proof-pack tests. |
| `1f864f3` | Claim evidence enforcement | Integrated evidence enforcement into the active claim runtime for covered claim actions. |
| `8ae5b32` | HQ promotion separation | Moved promoted bundle/state writes behind the governed transition decision for the covered HQ promotion path. |
| `34ad079` | Canonical ledger adapter | Added normalized governed-transition ledger entries that link to subsystem evidence. |
| `161e9da` | Operator canonical linkage | Added optional canonical governed-transition entries for covered operator runtime decisions. |
| `c2a993c` | Governed Authoring backend proof | Added a backend-governed source-packet-to-output path with schemas, decisions, canonical ledger linkage, and tests. |

## Now Proven For Covered Paths

The repository now proves these bounded claims for the files and tests listed below:

| Claim | Evidence | Status |
| --- | --- | --- |
| Formal governance primitives and gates exist as executable runtime objects. | `signal_agent/formal_governance/models.py`, `signal_agent/formal_governance/decision.py`, `signal_agent/formal_governance/gates.py`, `schemas/formal_governance/*`, `tests/test_formal_governance_*.py` | Proven for proof-pack fixtures. |
| Active claim anchoring/publication-ready paths require non-empty evidence refs and reject generator/model/self-certified evidence. | `signal_agent/content/claim_engine.py`, `signal_agent/content/claim_distributor.py`, `tests/test_claim_evidence_enforcement.py` | Proven for covered claim runtime actions. |
| HQ capture promotion does not materialize final promoted bundle/state writes before governed transition success. | `app/hq/capture/promote.py`, `tests/test_hq_promotion_separation.py` | Proven for the covered HQ capture promotion path. |
| Canonical governed-transition ledger entries can link subsystem evidence for claim and HQ decisions. | `signal_agent/formal_governance/adapters.py`, `signal_agent/formal_governance/canonical_ledger.py`, `tests/test_canonical_ledger_adapter.py` | Proven when canonical ledger paths are explicitly configured. |
| Covered operator decisions can emit canonical governed-transition entries while preserving operator subsystem ledgers. | `signal_agent/operator/runtime.py`, `signal_agent/operator/chat.py`, `tests/test_operator_canonical_ledger_adapter.py` | Proven for selected allow, reject, duplicate, and contract-violation operator decisions when configured. |
| Governed Authoring has one backend-governed source-packet-to-output proof path. | `signal_agent/governed_authoring/*`, `schemas/governed_authoring/*`, `tests/test_governed_authoring_backend.py` | Proven for covered fixtures and runtime decisions. |

## Partially Proven

| Claim | Why partial |
| --- | --- |
| "Formal governance is integrated into runtime." | Integrated into selected claim, HQ promotion, operator, and Governed Authoring paths only. Other mutation paths remain outside this proof boundary. |
| "Every governed decision appends a canonical ledger entry." | Canonical append is available and tested for covered paths when configured, but not mandatory across the repo. |
| "Artifact admission is distinct from state promotion." | Covered HQ promotion path is improved, but all artifact/state paths have not been audited or routed through the same adapter. |
| "Generator cannot self-certify." | Proven for active claim evidence and Governed Authoring review fixtures; not universal across every subsystem. |
| "Same input gives same decision." | Deterministic decision ids are tested for selected adapters. Full runtime artifacts still include timestamps, run ids, and filesystem state. |
| "Unresolved tensions defer promotion." | Proven in the formal proof pack and Governed Authoring backend path; not wired into every promotion path. |

## Not Proven

Do not claim these as proven:

- Full repo-wide governance.
- All state changes are gated.
- Complete Invariant Branch Vector Mapping across every runtime path.
- Universal self-certification prevention.
- Universal canonical ledger append for every decision.
- Complete same-input/same-decision proof across the full repository.
- Production Governed Authoring application.
- Static prototype UI backed by the new backend.
- Production authoring artifact write path.

## Out Of Scope After Phase 5

- The static Governed Authoring prototype remains a local UI/workflow demonstration.
- No app/server surface was added for Governed Authoring.
- No production authoring artifacts are written by the new backend proof path.
- Existing subsystem ledgers remain intact and are not replaced.
- Production JSONL ledgers are not migrated.
- Historical records are not backfilled into canonical governed-transition entries.

## Current Safe Summary

Safe current-state language:

"The repository contains a formal governance proof pack and selected runtime integrations. Covered claim, HQ promotion, operator, and Governed Authoring backend decisions can produce formal decisions and optional canonical governed-transition ledger entries. These are bounded proof surfaces, not a repo-wide governance guarantee."
