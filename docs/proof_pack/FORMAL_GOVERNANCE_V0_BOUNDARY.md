# Formal Governance V0 Boundary

This document defines the claim boundary for the V0 proof pack.

This proves the isolated formal-governance proof pack V0. It does not yet prove repo-wide integration across HQ, operator, Governed Authoring, or claim runtime paths.

## What V0 Proves

V0 proves, in isolation:

- The formal-governance package imports from the repo root.
- Required primitives have typed representations.
- Required schemas exist under `schemas/formal_governance/`.
- Fixed fixtures exist for positive, rejected, deferred, duplicate, and self-certification cases.
- `evaluate_transition()` returns typed promotion decisions.
- Gate coverage includes lineage, invariant, branch vector, raw artifact self-promotion, evidence, unresolved tension, human authority, rollback, duplicate transition, and self-certification.
- Deterministic decision identity is independent of timestamped ledger entry identity.
- Canonical governed transition ledger entries include required fields.
- Ledger hash chaining is implemented and verified by tests.
- The proof-pack CLI writes proof artifacts to supplied temporary output paths in tests.
- Production JSONL ledgers under `data/` were unchanged during verification.

## What V0 Does Not Prove

V0 does not prove:

- HQ promotion is governed by the formal proof pack.
- Operator runtime emits formal governed transition ledger entries.
- Governed Authoring has backend-governed execution.
- Claim engine rejects empty `evidence_refs`.
- All state mutations in the repository use the formal decision engine.
- Existing production ledgers contain complete canonical V0 ledger entries.
- Repo-wide generator/self-certification boundaries exist.

## Safe Status Language

Use:

```text
The repository now has bounded runtime governance proof plus an isolated formal-governance proof pack V0 for Invariant Branch Vector Mapping primitives, gates, deterministic decisions, canonical ledger entries, and proof fixtures.

The proof pack demonstrates the formal layer in isolation.

Repo-wide integration across HQ promotion, operator runtime, Governed Authoring, and claim enforcement remains the next implementation phase.
```

Avoid:

- "IBVM is fully proven repo-wide."
- "All state changes are formally governed."
- "Claims require evidence across the repository."
- "Governed Authoring is executable backend proof."
- "The formal ledger has replaced production ledgers."
- "HQ/operator paths now use the proof pack."

## Integration Boundary

The formal-governance package is intentionally parallel. It should remain isolated until a separate integration task explicitly wires it into an active runtime path with tests and ledger evidence.

Recommended integration order:

1. Claim engine evidence enforcement.
2. HQ promotion artifact/state separation.
3. Canonical ledger adapter.
4. Governed Authoring backend path.
5. Repo-wide self-certification boundary.

## Quarantine Boundary

Exclude these duplicate or accidental paths from commit planning:

- `E:\signal_agent\formal_governance\`
- `E:\schemas\formal_governance\`
- `E:\tests\test_formal_governance*.py`
- `E:\tests\fixtures\formal_governance\`
- `E:\docs\evaluation\`
- `E:\docs\proof_pack\`

The intended repo-local proof-pack paths are:

- `E:\signal_agent\signal_agent\formal_governance\`
- `E:\signal_agent\schemas\formal_governance\`
- `E:\signal_agent\tests\fixtures\formal_governance\`
- `E:\signal_agent\tests\test_formal_governance_models.py`
- `E:\signal_agent\tests\test_formal_governance_decision.py`
- `E:\signal_agent\tests\test_formal_governance_ledger.py`
- `E:\signal_agent\tests\test_formal_governance_cli.py`
