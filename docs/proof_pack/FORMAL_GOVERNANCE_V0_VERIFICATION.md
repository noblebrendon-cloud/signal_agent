# Formal Governance V0 Verification

Repository: `E:\signal_agent`

Verification date: 2026-06-13

Mode: inspection, test execution, and documentation only.

This proves the isolated formal-governance proof pack V0. It does not yet prove repo-wide integration across HQ, operator, Governed Authoring, or claim runtime paths.

## Verification Summary

The intended repo-local formal-governance proof pack V0 is implemented, importable, tested, and bounded to an isolated proof-pack runtime.

Verified package:

- `signal_agent/formal_governance/__init__.py`
- `signal_agent/formal_governance/models.py`
- `signal_agent/formal_governance/decision.py`
- `signal_agent/formal_governance/gates.py`
- `signal_agent/formal_governance/ledger.py`
- `signal_agent/formal_governance/hashing.py`
- `signal_agent/formal_governance/cli.py`

Verified schemas:

- `schemas/formal_governance/state.v1.schema.json`
- `schemas/formal_governance/invariant.v1.schema.json`
- `schemas/formal_governance/invariant_path.v1.schema.json`
- `schemas/formal_governance/branch_vector.v1.schema.json`
- `schemas/formal_governance/artifact_pocket.v1.schema.json`
- `schemas/formal_governance/variant_pocket.v1.schema.json`
- `schemas/formal_governance/architecture_node.v1.schema.json`
- `schemas/formal_governance/invariant_architecture.v1.schema.json`
- `schemas/formal_governance/human_trigger.v1.schema.json`
- `schemas/formal_governance/consolidation_pass.v1.schema.json`
- `schemas/formal_governance/unresolved_tension.v1.schema.json`
- `schemas/formal_governance/rollback_path.v1.schema.json`
- `schemas/formal_governance/promotion_decision.v1.schema.json`
- `schemas/formal_governance/governed_transition_ledger_entry.v1.schema.json`

Verified fixtures:

- `tests/fixtures/formal_governance/valid_promotion.json`
- `tests/fixtures/formal_governance/missing_lineage.json`
- `tests/fixtures/formal_governance/missing_invariant.json`
- `tests/fixtures/formal_governance/raw_artifact_self_promotion.json`
- `tests/fixtures/formal_governance/unresolved_tension_blocking.json`
- `tests/fixtures/formal_governance/missing_evidence.json`
- `tests/fixtures/formal_governance/missing_human_authority.json`
- `tests/fixtures/formal_governance/generator_self_certification.json`
- `tests/fixtures/formal_governance/rollback_required_missing.json`
- `tests/fixtures/formal_governance/duplicate_transition.json`

Verified tests:

- `tests/test_formal_governance_models.py`
- `tests/test_formal_governance_decision.py`
- `tests/test_formal_governance_ledger.py`
- `tests/test_formal_governance_cli.py`

## Import Verification

Command run:

```powershell
python -c "from signal_agent.formal_governance import BranchVector, InvariantPath, HumanTrigger, PromotionDecision, LedgerEntry, evaluate_transition; from signal_agent.formal_governance.cli import main; print('formal_governance_import_ok')"
```

Result:

```text
formal_governance_import_ok
```

Status: passed.

## Test Results

New proof-pack tests:

```powershell
python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q
```

Result:

```text
19 passed in 2.84s
```

Existing transition/operator tests:

```powershell
python -m pytest tests/test_hq_transition_gate.py tests/security/test_transition_bypass.py tests/test_operator_write_contract.py tests/test_operator_write_denial.py tests/test_operator_duplicate_gate.py -q
```

Result:

```text
80 passed in 80.84s
```

Existing governed-shell tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_governed_shell_policy.py tests/test_governed_shell_log_replay.py -q
```

Result:

```text
31 passed in 4.01s
```

Note: system Python did not have `jsonschema`; the governed-shell tests were run with the repo virtual environment, which has `jsonschema` available.

## Production Ledger Check

Before running tests, a snapshot was taken of production JSONL ledgers under `data/**/*.jsonl` using path, length, last write time, and SHA-256 hash.

After running tests, the same snapshot was repeated and compared.

Result:

```text
production_jsonl_unchanged count=52
```

Status: production JSONL ledgers were not modified by this verification pass.

## Proof Obligations Satisfied In Isolation

The V0 proof pack now satisfies these obligations in the isolated formal-governance runtime:

- Package imports cleanly.
- Required typed primitives exist in `models.py`.
- The decision engine returns typed promotion decisions.
- Lineage, invariant, branch vector, raw artifact self-promotion, evidence, unresolved tension, human authority, rollback, duplicate transition, and self-certification gates exist.
- Deterministic decision ids are stable for fixed fixtures.
- Timestamped ledger entries are separate from deterministic decision ids.
- Canonical governed transition ledger entries include the required proof fields.
- Hash chaining is implemented and verified for the proof-pack ledger.
- CLI proof output is tested with temporary output paths.
- Valid promotion, rejection, deferral, duplicate blocking, self-certification rejection, and ledger append are demonstrated through fixtures and tests.

## Still Not Proven Repo-Wide

This verification does not prove:

- HQ promotion uses the formal governance decision engine.
- Operator runtime uses the formal governance ledger entry.
- Governed Authoring has a backend path governed by this proof pack.
- Claim runtime enforces evidence references through this proof pack.
- All production state changes append canonical formal governance ledger entries.
- Repo-wide generator/self-certification separation exists across claims, promotions, branches, and authoring outputs.

## Quarantine From Commit Planning

The following accidental or duplicate paths must be excluded from commit planning unless separately reviewed:

- `E:\signal_agent\formal_governance\`
- `E:\schemas\formal_governance\`
- `E:\tests\test_formal_governance*.py`
- `E:\tests\fixtures\formal_governance\`
- `E:\docs\evaluation\`
- `E:\docs\proof_pack\`

Do not delete, move, clean, or treat these as disposable as part of this verification.

## Recommended Status Language

Use:

```text
The repository now has bounded runtime governance proof plus an isolated formal-governance proof pack V0 for Invariant Branch Vector Mapping primitives, gates, deterministic decisions, canonical ledger entries, and proof fixtures.

The proof pack demonstrates the formal layer in isolation.

Repo-wide integration across HQ promotion, operator runtime, Governed Authoring, and claim enforcement remains the next implementation phase.
```
