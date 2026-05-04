# Test + Verification Review

## Commands Run

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_governed_shell_schema.py tests/test_governed_shell_no_raw_shell.py tests/test_governed_shell_normalize.py tests/test_governed_shell_policy.py tests/test_governed_shell_log_replay.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_appointments_aging_alerts.py tests/test_retention_appointments_summary.py tests/test_retention_appointments_worklist.py -q
E:\signal_agent\.venv\Scripts\python.exe tools\verify_system.py
```

## Results
- governed-shell focused suite: PASS
  - `68 passed in 4.18s`
- retention appointment reporting suite: PASS
  - `34 passed in 39.51s`
- system verifier: PASS
  - completed with `OK: verify_system passed`

## Failure Summary
- No command failed in this focused run.

## What The Passes Mean

### Governed shell
The requested governed-shell suite gives strong evidence for:
- schema strictness
- raw-shell rejection
- deterministic proposal normalization/hashing
- default-deny policy review
- append-only audit log replay and tamper detection

### Retention appointments
The requested retention appointment suite gives strong evidence for:
- read-only reporting boundaries
- deterministic summary/worklist/aging-alert outputs
- explicit no-network / no-notification posture in those reporting surfaces

### `tools/verify_system.py`
The verifier passed, but this needs qualification:
- it runs `pip check`, import probes, agent fallback checks, resilience tests, curation smoke checks, and capture sanity checks
- it is not a purely observational verifier
- `tools/verify_system.py:126-214` creates temporary intake files, runs live curation commands, and verifies dedup behavior against live repo data

## Real vs Environmental vs Stale-Test Assessment
- governed-shell pass: appears real
- retention appointment pass: appears real
- verifier pass: appears real, but the test target is partly environmental and partly smoke-oriented rather than purely invariant-oriented

## Highest-Value Next Test To Add

Add a verifier-boundary test that proves `tools/verify_system.py` is either:
- read-only by default, or
- explicitly marked mutating and forced to run against an isolated temp root

Why this is the highest-value next test:
- the repo currently treats `verify_system.py` as verification authority
- the script demonstrably mutates curation-related repo data during execution
- that weakens audit repeatability and operator trust in the verifier

Suggested gate:
- a focused test that runs the verifier against a temp repo root and asserts no live repo files under `data/` changed unless an explicit mutating mode flag is enabled

## Tests That Appear To Define Core System Truth
- `tests/test_operator_write_contract.py`
- `tests/test_operator_write_denial.py`
- `tests/security/test_transition_bypass.py`
- `tests/test_governance_unification.py`
- `tests/test_governed_shell_schema.py`
- `tests/test_governed_shell_policy.py`
- `tests/test_governed_shell_log_replay.py`
- `tests/test_retention_cli.py`
- `tests/test_retention_reconcile.py`
- `tests/test_retention_dispatch_gate.py`
- `tests/test_retention_send_queue.py`
- `tests/test_retention_sender_contract.py`
- `tests/test_retention_authorization.py`
- `tests/test_publication_pipeline_end_to_end.py`
- `tests/test_runtime_audit_evidence.py`
- `tests/test_runtime_audit_reports.py`
- `tests/test_task_contract_runtime.py`
- `tests/test_invariant_checker_v1.py`

## Notes
- Because the repo worktree is already heavily dirty, this review does not attempt to attribute every existing change to the verifier run.
- The verifier output itself is enough to establish that it wrote through the curation path during this session.
