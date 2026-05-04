# Repository Surface Map

## Top-Level Directory Map

### Canonical and near-canonical code roots
- `signal_agent/`
  - Declared canonical Python package root in `README.md` and `ARCHITECTURE.md`.
- `app/`
  - Large operational code surface containing governance, retention, capture, curation, providers, CLI wrappers, utilities, and demos.
- `tools/`
  - Verification and utility scripts, including `tools/verify_system.py`.
- `tests/`
  - Large pytest/unittest surface across governance, operator, retention, capture, runtime audit, security, and drift audit.

### Config and governance roots
- `config/`
  - Holds `state_machine.yaml`, `lanes.yaml`, operator registries, and policy YAML files.
- `governance/`
  - Design/spec documents; appears conceptual rather than the live enforcement surface.
- `docs/operator/`
  - Operator-facing review, promotion, boundary, and remediation documents.
- `docs/publications/`
  - Publication bundles, including deterministic-governance materials.

### Data, state, and generated roots
- `data/`
  - Main state and artifact root; contains ledgers, previews, registries, releases, diagnostics, and capture outputs.
- `logs/`, `repro_out/`, `.tmp/`, `.tmp_offload_out/`
  - Runtime or generated output directories called out in `README.md`.
- `.venv/`, `.pytest_cache/`, `__pycache__/`, `drift_audit.egg-info/`
  - Environment/generated directories.

### Legacy, duplicate, or ambiguous roots
- `leviathan/`, `laviathon/`, `site_laviathon/`
  - Surface suggests legacy or mirrored namespaces/sites; `ARCHITECTURE.md` explicitly marks some of these non-canonical.
- `services/`, `shared/`, `business/`, `marketing/`, `books/`, `oil/`, `sites/`, `surfaces/`, `orchestration_core/`
  - Real repo content, but authority level is less obvious from the surface alone.
- `New folder/`
  - Ambiguous/non-authoritative by name alone.

## Main Python Packages / Modules
- `signal_agent.operator`
  - Repo-native operator runtime, registries, planner, response, and invariant checker.
- `app.hq.governance`
  - Canonical transition gate and lifecycle validation.
- `app.governed_shell`
  - Proposal/schema/policy/replay/audit-plan surface for a proposal-only governed shell.
- `app.retention`
  - Retention ledgers, dispatch gate, queue projection, sender preview, authorization, and appointment workflows.
- `app.hq.capture`
  - Capture, promotion, routing, decay, and instability surfaces.
- `app.hq.curation`
  - Deterministic staging / registry / index refresh surface.
- `app.audit`
  - Runtime audit facade, evidence collector, task contract, coherence kernel.
- `app.providers`
  - Provider registry and stub/failure providers.
- `signal_agent.leviathan.diagnostic.*` / `signal_agent.laviathon.*`
  - Stability snapshot and drift-audit diagnostic surfaces.

## Main CLI Surfaces
- `signal-operator`
  - From `pyproject.toml`; maps to `signal_agent.cli.operator_cli:main`.
- `drift-audit`
  - From `pyproject.toml`; maps to `signal_agent.laviathon.cli.drift_audit_cli:main`.
- `campaign`
  - From `pyproject.toml`; maps to `signal_agent.cli.campaign_cli:main`.
- `wtpu`
  - From `pyproject.toml`; maps to `signal_agent.cli.wtpu_cli:main`.
- `python -m app.retention.cli`
  - Retention and appointment CLI surface.
- `python -m signal_agent.cli.operator_cli`
  - Operator single-turn and interactive surface.
- `python -m signal_agent.laviathon.diagnostic.stability_snapshot.cli`
  - Called out in `README.md`.
- `python -m signal_agent.core.clock.clock`
  - Declared deterministic clock runtime in `README.md`.

## Main Docs Surfaces
- Root authority docs:
  - `README.md`
  - `ARCHITECTURE.md`
  - `GOVERNANCE_KERNEL.md`
- Operator docs:
  - `docs/operator/README.md`
  - `docs/operator/architecture.md`
  - `docs/operator/module_artifact_index.md`
  - `docs/operator/retention_subsystem_guide.md`
  - `docs/operator/governed_shell_invariants.md`
- Publication bundle:
  - `docs/publications/deterministic_governance/README.md`
  - `docs/publications/deterministic_governance/deterministic_governance.md`
  - `docs/publications/deterministic_governance/implementation_evidence.md`

## Main Test Families
- Operator / governed mutation path
  - `tests/test_operator_write_contract.py`
  - `tests/test_operator_write_denial.py`
  - `tests/test_operator_transaction_snapshot.py`
  - `tests/test_operator_write_intent_contract.py`
- Governance / state-machine enforcement
  - `tests/security/test_transition_bypass.py`
  - `tests/test_governance_unification.py`
  - `tests/test_invariant_checker_v1.py`
- Governed shell
  - `tests/test_governed_shell_schema.py`
  - `tests/test_governed_shell_no_raw_shell.py`
  - `tests/test_governed_shell_policy.py`
  - `tests/test_governed_shell_log_replay.py`
  - additional later-phase tests also exist: `test_governed_shell_execution_plan.py`, `test_governed_shell_simulation.py`
- Retention / appointments
  - `tests/test_retention_*.py`
  - `tests/test_retention_appointments_*.py`
- Capture / curation / release
  - `tests/test_capture_*.py`
  - `tests/test_curate_publication_gate.py`
  - `tests/test_publication_pipeline_end_to_end.py`
  - `tests/test_release_orchestrator.py`
- Runtime audit / task contract
  - `tests/test_runtime_audit_evidence.py`
  - `tests/test_runtime_audit_reports.py`
  - `tests/test_task_contract_runtime.py`
- Security, memory, drift-audit, and integration suites also exist.

## Known Generated / State Directories
- Runtime/state roots
  - `data/state/`
  - `data/operator/`
  - `data/capture/`
  - `data/intake/`
- Generated/output roots
  - `artifacts/`
  - `repro_out/`
  - `logs/`
  - `.tmp/`
  - `.tmp_offload_out/`
- Generated caches
  - `__pycache__/`
  - `tests/__pycache__/`
  - `.pytest_cache/`
  - `drift_audit.egg-info/`

## Files That Appear Canonical / High-Authority
- `README.md`
- `ARCHITECTURE.md`
- `GOVERNANCE_KERNEL.md`
- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/operator/intents.yaml`
- `config/operator/tools.yaml`
- `config/operator/workflows.yaml`
- `data/state/module_artifacts.jsonl`
- `docs/operator/module_artifact_index.md`

## Files / Areas That Look Stale, Duplicated, Or Ambiguous
- Canonical-root ambiguity
  - `ARCHITECTURE.md` says `signal_agent/` is canonical and `app/` is non-canonical, but major live enforcement code still sits in `app/`.
- Registry-path ambiguity
  - Both `data/artifact_registry.jsonl` and `data/state/artifact_registry.jsonl` appear in docs, code, and tests.
- Review-doc drift
  - Older promotion/remediation docs still discuss candidate/blocked states for modules that `docs/operator/module_artifact_index.md` now lists as active.
- Legacy/mirror roots
  - `leviathan/`, `laviathon/`, `site_laviathon/`.
- Debug / scratch / output files at repo root
  - `out*.txt`, `out*.json`, `error.log`, `probe_output.txt`, `parse_results.txt`, `test_out.txt`, `pytest.log`, and similar files look operationally incidental rather than canonical.
