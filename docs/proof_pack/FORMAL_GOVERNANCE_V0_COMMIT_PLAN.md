# Formal Governance V0 Commit Plan

This document identifies the intended files for a future commit and the files to exclude. It is a planning document only. No staging or commit was performed during verification.

This proves the isolated formal-governance proof pack V0. It does not yet prove repo-wide integration across HQ, operator, Governed Authoring, or claim runtime paths.

## Exact Recommended Git Add List

Add only these intended repo-local files for the proof-pack V0 commit:

```powershell
git add signal_agent/formal_governance/__init__.py
git add signal_agent/formal_governance/models.py
git add signal_agent/formal_governance/decision.py
git add signal_agent/formal_governance/gates.py
git add signal_agent/formal_governance/ledger.py
git add signal_agent/formal_governance/hashing.py
git add signal_agent/formal_governance/cli.py
git add schemas/formal_governance/state.v1.schema.json
git add schemas/formal_governance/invariant.v1.schema.json
git add schemas/formal_governance/invariant_path.v1.schema.json
git add schemas/formal_governance/branch_vector.v1.schema.json
git add schemas/formal_governance/artifact_pocket.v1.schema.json
git add schemas/formal_governance/variant_pocket.v1.schema.json
git add schemas/formal_governance/architecture_node.v1.schema.json
git add schemas/formal_governance/invariant_architecture.v1.schema.json
git add schemas/formal_governance/human_trigger.v1.schema.json
git add schemas/formal_governance/consolidation_pass.v1.schema.json
git add schemas/formal_governance/unresolved_tension.v1.schema.json
git add schemas/formal_governance/rollback_path.v1.schema.json
git add schemas/formal_governance/promotion_decision.v1.schema.json
git add schemas/formal_governance/governed_transition_ledger_entry.v1.schema.json
git add tests/fixtures/formal_governance/valid_promotion.json
git add tests/fixtures/formal_governance/missing_lineage.json
git add tests/fixtures/formal_governance/missing_invariant.json
git add tests/fixtures/formal_governance/raw_artifact_self_promotion.json
git add tests/fixtures/formal_governance/unresolved_tension_blocking.json
git add tests/fixtures/formal_governance/missing_evidence.json
git add tests/fixtures/formal_governance/missing_human_authority.json
git add tests/fixtures/formal_governance/generator_self_certification.json
git add tests/fixtures/formal_governance/rollback_required_missing.json
git add tests/fixtures/formal_governance/duplicate_transition.json
git add tests/test_formal_governance_models.py
git add tests/test_formal_governance_decision.py
git add tests/test_formal_governance_ledger.py
git add tests/test_formal_governance_cli.py
git add docs/proof_pack/FORMAL_GOVERNANCE_V0_VERIFICATION.md
git add docs/proof_pack/FORMAL_GOVERNANCE_V0_PROOF_MATRIX.md
git add docs/proof_pack/FORMAL_GOVERNANCE_V0_BOUNDARY.md
git add docs/proof_pack/FORMAL_GOVERNANCE_V0_COMMIT_PLAN.md
```

## Exact Files And Paths Not To Add

Do not add these accidental duplicate or quarantine paths:

```powershell
E:\signal_agent\formal_governance\
E:\schemas\formal_governance\
E:\tests\test_formal_governance*.py
E:\tests\fixtures\formal_governance\
E:\docs\evaluation\
E:\docs\proof_pack\
```

Do not add generated caches:

```powershell
signal_agent/formal_governance/__pycache__/
tests/__pycache__/
.pytest_cache/
```

Do not add production ledgers or runtime output as part of this proof-pack commit:

```powershell
data/
.tmp/
logs/
repro_out/
```

## Verification Commands For Commit Review

Before committing in a later task, rerun:

```powershell
python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q
python -m pytest tests/test_hq_transition_gate.py tests/security/test_transition_bypass.py tests/test_operator_write_contract.py tests/test_operator_write_denial.py tests/test_operator_duplicate_gate.py -q
.venv\Scripts\python.exe -m pytest tests/test_governed_shell_policy.py tests/test_governed_shell_log_replay.py -q
```

## Commit Message Candidate

```text
Add isolated formal governance proof pack V0
```

## Commit Scope Boundary

This commit should introduce a parallel proof-pack runtime only. It should not include runtime integration into HQ promotion, operator workflows, Governed Authoring, or claim enforcement.
