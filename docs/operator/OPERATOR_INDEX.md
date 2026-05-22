# Signal Agent Operator Index

Generated: 2026-05-07
Phase: Stabilization and canonicalization
Mode: fail-closed consolidation
Status: active

## System Identity

Signal Agent is a deterministic governance and operational continuity system.

It is centered on:
- bounded state transition
- observable execution
- append-only operational memory
- fail-closed runtime behavior
- governed AI-assisted engineering workflows

It is not unrestricted autonomous AI, uncontrolled orchestration, self-modifying agent infrastructure, or a replacement for developers.

The practical identity is:

```text
declared intent -> bounded workflow -> transition gate -> governed write -> append-only evidence -> reconciliation
```

If authority cannot be proven, the system should reject, hold, fail, or report unsupported behavior. Unknown authority is not permission.

## Canonical Entrypoints

Use these as the current canonical operator surfaces.

| Purpose | Entrypoint |
|---|---|
| Operator CLI | `python -m signal_agent.cli.operator_cli --repo-root E:\signal_agent "inspect system state"` |
| Operator interactive mode | `python -m signal_agent.cli.operator_cli --repo-root E:\signal_agent --interactive` |
| Deterministic clock runtime | `python -m signal_agent.core.clock.clock` |
| Drift audit CLI | `python -m signal_agent.laviathon.cli.drift_audit_cli` |
| Invariant checker | `python -m signal_agent.operator.invariant_checker --repo-root E:\signal_agent` |
| Daily witness runtime | `python -B -m signal_agent.health.daily_check --repo-root E:\signal_agent` |
| Retention CLI | `python -m app.retention.cli` |
| Controlled failure demo | `python -m app.demo.controlled_failure.cli` |

On this workstation, prefer the repo virtualenv:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m signal_agent.cli.operator_cli --repo-root E:\signal_agent "inspect system state"
```

## Repo Zones

| Zone | Surfaces | Operator meaning |
|---|---|---|
| canonical | `signal_agent/`, selected governed modules under `app/`, `shared/`, `config/`, `data/state/module_artifacts.jsonl` | Active architecture and governance authority. |
| legacy | top-level `leviathan/`, top-level `laviathon/`, `site_laviathon/` | Historical or compatibility surface. Do not treat as production entrypoints unless explicitly marked. |
| experimental | `experiments/`, `.tmp/`, `tmp_route_debug/`, `repro_out/`, root debug outputs | Useful evidence or scratch, not authority. |
| demo | `app/demo/controlled_failure/`, demo docs | Public proof surfaces. Keep reproducible and local. |
| publication/research | `docs/publications/`, `SYSTEM_RESEARCH_BRIEF.md`, market/research briefs | Explanatory and public-facing proof, not runtime authority. |
| internal-only | `docs/operator/`, `reviews/`, `migration_reports/` | Operator planning, audit history, consolidation decisions. |
| operator-facing | `docs/operator/OPERATOR_INDEX.md`, `docs/operator/README.md`, operator CLI, retention guide, invariant plans | Human control surface for daily operation. |

Important ambiguity:
- `signal_agent/` is the canonical package root.
- `app/` is not a canonical package root, but it still contains active governed modules such as transition gate, IO contract, retention, capture, curation, audit, and demos.

## Canonical Architecture

Primary architecture files:
- `README.md`
- `ARCHITECTURE.md`
- `GOVERNANCE_KERNEL.md`
- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/operator/intents.yaml`
- `config/operator/tools.yaml`
- `config/operator/workflows.yaml`
- `data/state/module_artifacts.jsonl`

Primary runtime/governance modules:
- `signal_agent/operator/runtime.py`
- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`
- `app/hq/governance/transition_gate.py`
- `app/utils/io_contract.py`
- `shared/authority.py`
- `shared/coherence.py`
- `shared/reconcile.py`
- `shared/health.py`

Current single-source-of-truth rule:
- lifecycle graph: `config/state_machine.yaml`
- transition validator: `app/hq/governance/transition_gate.py`
- operator workflow authority: `config/operator/*.yaml`
- state write primitive: `app/utils/io_contract.py`
- module boundary registry: `data/state/module_artifacts.jsonl`
- lane authority: `config/lanes.yaml`

Known unresolved authority issue:
- content artifact registry authority is split between `data/artifact_registry.jsonl` and `data/state/artifact_registry.jsonl`. This must be resolved before broad witness-node claims.

## Lifecycle Flow

Canonical system lifecycle:

```text
captured -> normalized -> classified -> constrained -> promoted -> routed -> transformed -> compiled -> staged -> emitted -> audited
```

Control states:

```text
held
failed
rejected
aborted
```

Operator write flow:

```text
command text
  -> intent parser
  -> workflow planner
  -> registry contract validation
  -> transition gate
  -> context assembly
  -> tool dispatch
  -> boundary evidence
  -> operator run ledger
```

The strongest implemented proof surface is the operator runtime declared-vs-observed write contract.

## Governance Invariants

Core invariant:

```text
No state change without validated, observable, governed transition.
```

Operational invariants:
- no ungoverned mutation
- fail closed by default
- deterministic transformation where inputs are identical
- append-only observability for ledgers
- declared mutation contract for tools and workflows
- reconciliation before downstream trust
- local-only boundaries before external action

Protected mechanisms:
- `append_jsonl_atomic(...)`
- transition gate validation
- operator write contracts
- runtime boundary evidence
- module invariant checker
- retention reconciliation
- read-only MCP exposure
- drift audit golden tests

## Operational Modes

| Mode | Meaning | External action |
|---|---|---|
| read-only inspection | Reconstruct status from configs, ledgers, and files. | No |
| governed write | Mutating workflow through declared tool, transition gate, and boundary evidence. | No by default |
| local-only dry run | Simulates dispatch or execution without irreversible action. | No |
| reconciliation | Reads ledgers and reports drift or corruption. | No |
| publication/demo | Produces explainable artifacts or public proof outputs. | No unless separately admitted |
| external execution | Not currently admitted as a general boundary. | Blocked until explicit policy exists |

Retention remains local-only:
- `send_ready` is not `sent`
- `accepted_preview` is not `sent`
- authorization does not permit external delivery
- `network_allowed` remains false
- `external_actions_allowed` remains false

## Witness-Node Role

The witness node is a low-power operational continuity observer.

It should:
- observe
- verify
- reconcile
- snapshot
- report

It should not:
- self-modify
- autonomously expand governance
- perform unrestricted execution
- deliver external messages
- replace operator approval

Daily witness-node loop:

1. Pull or receive repo state.
2. Run fast invariant verification.
3. Run targeted tests.
4. Validate ledgers.
5. Generate compact health report.
6. Write daily snapshot.
7. Append daily continuity record.
8. Archive results.

Canonical manual command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
E:\signal_agent\.venv\Scripts\python.exe -B -m signal_agent.health.daily_check --repo-root E:\signal_agent
```

This command is manual-only. Do not add scheduling, notifications, external delivery, or autonomous repair until a later governance decision.

## Verification Commands

Fast orientation:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m signal_agent.cli.operator_cli --repo-root E:\signal_agent "inspect system state"
E:\signal_agent\.venv\Scripts\python.exe -m signal_agent.cli.operator_cli --repo-root E:\signal_agent "list workflows"
```

Invariant checker:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m signal_agent.operator.invariant_checker --repo-root E:\signal_agent
```

Drift audit proof:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/drift_audit/ -q
```

Runtime governance proof slices:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_operator_write_contract.py tests/test_operator_write_denial.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/security/test_transition_bypass.py tests/security/test_write_contract_abuse.py tests/security/test_replay_tamper.py -q
```

Retention local-only proof:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_reconcile.py tests/test_retention_dispatch_gate.py tests/test_retention_authorization.py tests/test_retention_execution_dry_run.py -q
```

Runtime audit proof:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_runtime_audit_evidence.py tests/test_runtime_audit_reports.py -q
```

Full collection check:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Known verification caution:
- `tests/test_governance_unification.py` may be slow or timeout on a dirty/generated tree. Stabilization should narrow its traversal instead of treating timeout as architectural failure.

## Onboarding Links

Start here:
- `docs/operator/OPERATOR_INDEX.md`
- `docs/operator/README.md`
- `README.md`
- `ARCHITECTURE.md`
- `GOVERNANCE_KERNEL.md`

Closeout authority:
- `docs/operator/MASTER_ENDPOINT_REGISTER.md`
- `docs/operator/RELEASE_ARCHIVE_PLAN.md`

Canonicalization and witness-node planning:
- `docs/operator/canonicalization_witness_node_consolidation_plan.md`
- `docs/operator/daily_witness_runtime_v1.md`
- `docs/operator/pi_manual_deployment_checklist.md`
- `docs/operator/raspberry_pi_witness_node_setup.md`
- `docs/operator/system_invariant_enforcement_plan.md`
- `docs/operator/invariant_checker_implementation_plan.md`
- `docs/operator/module_formalization_closeout.md`

Operator architecture:
- `docs/operator/architecture.md`
- `docs/operator/module_artifact_index.md`
- `docs/architecture/STATE_MACHINE.md`
- `docs/architecture/TRANSITION_GATE.md`

Retention and local-only automation:
- `docs/operator/retention_subsystem_guide.md`
- `docs/operator/retention_pre_external_v1_checkpoint.md`
- `docs/operator/retention_stage7_dry_run_checkpoint.md`

Governed shell:
- `docs/operator/governed_shell_invariants.md`
- `docs/operator/governed_shell_mvp_acceptance.md`
- `docs/operator/governed_shell_integration_plan.md`

Public proof and education:
- `docs/demo/controlled_failure_demo_script.md`
- `docs/publications/deterministic_governance/README.md`
- `docs/publications/deterministic_governance/implementation_evidence.md`
- `docs/publications/deterministic_governance/failure_modes.md`
- `docs/publications/deterministic_governance/top_3_missing_proofs.md`

## Active Roadmap

Immediate priorities:
1. Keep this operator index authoritative.
2. Create `docs/operator/START_HERE.md`.
3. Create `docs/operator/CANONICAL_SURFACES.md`.
4. Create `docs/operator/LEDGER_MAP.md`.
5. Decide canonical content artifact registry path.
6. Implement a fast daily health command.
7. Narrow slow governance traversal.
8. Keep retention local-only.

Near-term stabilization:
- daily witness-node health report
- append-only witness continuity ledger
- state write inventory scanner in audit mode
- public controlled-failure demo package
- transition rejection demo
- runtime mutation detection demo

Do not expand architecture until the current system is understandable, reconcilable, verifiable, operator-readable, and witness-node compatible.

## Operator Checklist

Before trusting a run:
- Confirm repo zone and entrypoint.
- Confirm workflow is declared.
- Confirm write mode is intentional.
- Confirm transition gate authority exists.
- Confirm ledgers parse.
- Confirm reconciliation is clean.
- Confirm output is local-only unless explicit external policy exists.

When blocked:
- Read the rejection reason first.
- Check transition event ledger.
- Check operator run ledger.
- Run invariant checker.
- Run the smallest targeted test slice.
- Do not bypass governance to make a demo pass.

## Canonical Claim Boundary

The publishable claim is narrow:

```text
Signal Agent demonstrates bounded deterministic governance on named local execution surfaces.
```

Do not claim:
- universal autonomy
- global filesystem interception
- full repo-wide mutation proof
- external delivery readiness
- complete publication-lane coverage

Where proof is partial, say it is partial. That honesty is part of the governance model.
