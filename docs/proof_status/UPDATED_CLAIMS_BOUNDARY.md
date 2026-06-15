# Updated Claims Boundary After Phases 1-5

This document gives publication-safe language for the current repository after commit `c2a993c`.

## Can Now Be Claimed

Use these statements when describing the current state:

- "A backend-governed Governed Authoring proof path exists for covered source-packet-to-output fixtures."
- "Covered Governed Authoring backend decisions can produce provisional, rejected, deferred, and approved output manifests."
- "Covered Governed Authoring backend approvals require evidence references and approved human review authority."
- "Covered Governed Authoring backend approvals defer when blocking unresolved tensions are present."
- "Canonical governed-transition ledger entries are available for covered claim, HQ promotion, operator, and Governed Authoring decisions when explicitly configured."
- "Formal governance proof is integrated into selected runtime paths."
- "The system has bounded proof surfaces for claim evidence enforcement, HQ promotion separation, operator canonical linkage, and Governed Authoring backend decisions."
- "Subsystem ledgers remain intact; canonical entries link to subsystem evidence instead of replacing historical ledgers."

## Must Be Qualified

Use careful wording for these statements:

| Risky wording | Safer wording |
| --- | --- |
| "The system is governed." | "Selected runtime paths are governed by formal decisions, gates, tests, and optional canonical ledger entries." |
| "Claims require evidence." | "Covered active claim anchoring and publication-ready actions require evidence references." |
| "Governed Authoring is implemented." | "A Governed Authoring backend proof path is implemented for covered source-packet-to-output decisions." |
| "Operator decisions are canonical-ledgered." | "Covered operator decisions can emit canonical governed-transition entries when configured." |
| "Promotion is separated from artifact writes." | "The covered HQ capture promotion path now delays final promoted writes until after governed decision success." |
| "Generator self-certification is prevented." | "Generator/model/self-certification is rejected in covered claim evidence and Governed Authoring review paths." |
| "Same input gives same decision." | "Selected deterministic decision ids are stable for fixed inputs; full runtime artifacts may still vary." |

## Cannot Yet Be Claimed

Do not claim:

- Full repo-wide governance.
- All state changes are gated.
- All claims require evidence across the repository.
- Production Governed Authoring application.
- Static prototype UI backed by the Governed Authoring backend.
- Production authoring artifact write path.
- Universal self-certification prevention.
- Universal canonical ledger append.
- Complete same-input/same-decision proof across the full repository.
- Complete Invariant Branch Vector Mapping proof across every path.
- Historical subsystem ledgers are migrated into canonical proof records.

## Required Boundary Language

Use this boundary after Phase 5:

```text
Governed Authoring now has a backend proof path for covered source-packet-to-output decisions.

The static prototype UI is still not wired to that backend.
No production authoring artifact write path has been added.
This does not prove repo-wide promotion governance.
```

## Evidence Rule

A claim may be treated as proven only when the repository has:

- Runtime code implementing the behavior.
- Tests covering positive and negative cases.
- Durable evidence or a ledger path where the claim concerns decisions, promotion, or auditability.

If one of those is missing, label the claim as partial, conceptual, or out of scope.
