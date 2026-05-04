# Architecture Diagnostic

## Runtime Boundaries

### Canonical vs non-canonical code roots
- `ARCHITECTURE.md` declares `signal_agent/` canonical and marks `app/` non-canonical.
- The live enforcement core still materially depends on `app/`, including:
  - `app/hq/governance/transition_gate.py`
  - `app/utils/io_contract.py`
  - `app/retention/*`
  - `app/governed_shell/*`
- Architectural consequence: the repo has a declared canonical root, but the actual runtime authority is split between `signal_agent/` and `app/`.

### Main runtime surfaces
- Operator runtime: `signal_agent/operator/runtime.py`
- Transition gate: `app/hq/governance/transition_gate.py`
- Retention spine: `app/retention/*`
- Governed shell: `app/governed_shell/*`
- Audit/report split: `app/audit/runtime_audit.py`, `app/audit/runtime_audit_reports.py`, `app/audit/runtime_audit_evidence.py`, `app/audit/task_contract.py`

## Governance Gates

### Transition gate
`app/hq/governance/transition_gate.py:238-419` enforces:
- invalid current state rejection
- invalid next state rejection
- forbidden transition rejection
- transition-defined gate lookup and policy evaluation
- control-state TTL expiry handling

`emit_transition_event()` appends transition attempts to `data/state/transition_gate_events.jsonl` through `append_jsonl_atomic()` at `app/hq/governance/transition_gate.py:435-467`.

### Operator write gate
`signal_agent/operator/runtime.py` uses:
- plan contract checks before execution (`:420-489`)
- declared-write vs workflow-mode enforcement (`:813-861`)
- bounded observation scopes over reads/writes/authority paths (`:920-989`)
- post-dispatch boundary evidence and hard rejection on mismatch (`:1569-1658`)

### Governed-shell policy gate
`app/governed_shell/policy.py` provides default-deny review with explicit rejection of:
- forbidden fields/tokens
- unknown operations/bindings/parameters
- network requests
- privilege escalation
- unsupported native operations in MVP

### Retention staged gates
The retention path separates:
- reconciliation (`app/retention/reconcile.py`)
- dispatch readiness (`app/retention/dispatch_gate.py`)
- queue projection (`app/retention/send_queue.py`)
- sender preview (`app/retention/sender_contract.py`)
- outbound authorization (`app/retention/outbound_authorization.py`)

This is one of the clearest proposal/approval/execution-separation patterns in the repo.

## State Files And Ledgers

### Canonical state/event ledgers
- `data/state/transition_gate_events.jsonl`
- `data/operator/runs/operator_runs.jsonl`
- `data/intake/intake.jsonl`
- `data/state/module_artifacts.jsonl`
- Retention ledgers:
  - `data/state/events.jsonl`
  - `data/state/transitions.jsonl`
  - `data/state/contacts.jsonl`
  - `data/state/content_dispatch.jsonl`
- Appointment ledgers:
  - `data/state/appointment_intake.jsonl`
  - `data/state/appointment_proposals.jsonl`
  - `data/state/appointment_transitions.jsonl`
  - `data/state/appointment_schedule_dry_run.jsonl`

### Projection / preview / report artifacts
- `data/state/send_queue_preview.json`
- `data/state/send_preview.json`
- `data/state/send_authorization.json`
- `data/state/preflight.json`
- `data/state/postflight.json`
- `data/state/contract_eval.json`

## Append-Only Behavior

### Strong surfaces
- `app/utils/io_contract.py:122-168` provides append-only JSONL primitives.
- `app/retention/jsonl_store.py` layers hash chaining (`prev_hash`, `record_hash`) on top of atomic append.
- `app/governed_shell/logstore.py` creates an append-only audited hash chain.
- `signal_agent/operator/runtime.py:2186-2202` appends operator run summaries through the shared append helper.

### Limits
- Append-only guarantees are strong on named ledgers, but not every repo mutation surface participates in the same observed-vs-declared enforcement pattern.
- The deterministic-governance publication bundle itself explicitly narrows its proof claims to the strongest paths instead of claiming repo-wide coverage.

## Atomic IO Behavior

### Coherent parts
- `app/utils/io_contract.py:24-37` implements atomic overwrite via temp file + `os.replace()`.
- `app/utils/io_contract.py:122-168` implements locked atomic append.
- Retention CLI writes preview/authorization outputs through `atomic_write_text()` (`app/retention/cli.py:529`, `:552`, `:578`).
- Curation registry append and artifact index refresh are explicitly tested to use shared helpers (`tests/test_curate_publication_gate.py`).

### Drift / exceptions
- `signal_agent/operator/runtime.py:78-82` still uses a runtime-local `_atomic_write()` helper for session state rather than the shared IO contract.
- `signal_agent/operator/runtime.py:1296-1363` writes transactional snapshot files with `write_bytes()` / `write_text()` rather than shared atomic helpers.
- `app/hq/curation/curate.py` stages final artifacts with a custom temp-copy + `os.replace()` flow instead of the shared helper.

The architecture is directionally coherent, but not yet fully unified on one IO abstraction.

## CLI Entrypoints

### Packaging / console scripts
- `drift-audit`
- `signal-operator`
- `campaign`
- `wtpu`

### Module CLIs
- `python -m signal_agent.cli.operator_cli`
- `python -m app.retention.cli`
- `python -m signal_agent.laviathon.diagnostic.stability_snapshot.cli`
- `python -m signal_agent.core.clock.clock`

The operator and retention CLIs are the clearest currently-governed operational entrypoints.

## Module Registration

`data/state/module_artifacts.jsonl` plus `docs/operator/module_artifact_index.md` provide a real module registry.

Observed state:
- 15 active reviewed modules
- 1 deprecated historical record (`letters_of_light_core`)
- no current candidate modules

The registry is a meaningful governance surface because `signal_agent/operator/invariant_checker.py` consumes it to enforce:
- current path existence
- forbidden dependency edges
- governed JSONL append rules
- export-surface alignment

Notable gap:
- `governed_shell` is documented and tested, but it is not registered as a module artifact.

## Test Coverage Structure

The test architecture is not shallow. It is organized around boundaries:
- operator mutation path and contract tests
- transition/state-machine/security tests
- governed-shell schema/policy/replay tests
- retention and appointment lifecycle/reporting tests
- curation/release path tests
- runtime-audit and contract-layer tests
- invariant-checker tests against module metadata

This is a strength: the repo often tests exact boundary claims instead of only broad behavior.

## Documentation-Code Alignment

### Alignment is strong when
- docs describe operator write-path enforcement, governed-shell proof phases, retention staging, and runtime-audit split boundaries
- tests exist for those exact surfaces

### Alignment drifts when
- docs imply repo-wide determinism, but live identities still depend on wall-clock time
  - `signal_agent/operator/runtime.py:73-75` derives `run_id` from `started_at`
  - `signal_agent/operator/runtime.py:1291-1294` derives transaction IDs from current time
- docs present `tools/verify_system.py` as verification, but `tools/verify_system.py:126-214` runs mutating curation checks against the live repo
- older promotion/remediation docs still describe candidate/blocked states that the module index now treats as active

## Where The Architecture Is Coherent
- Operator runtime + config registries + transition gate + IO contract form the clearest control loop.
- Retention is staged, local-only, and explicit about what is still blocked.
- Governed shell is unusually disciplined for an unexecuted shell surface: no raw shell text, schema-first validation, default-deny policy, append-only audit, replay support.
- Module artifact registration plus invariant checking is a real structural governance layer, not just prose.

## Where The Architecture Is Drifting / Unclear / Too Complex
- Declared canonical root vs actual enforcement root (`signal_agent/` vs `app/`).
- Repo-wide sprawl and legacy roots dilute authority discovery.
- Some proof language is broader than the strongest tested surfaces.
- `tools/verify_system.py` is part verifier, part mutating smoke harness, which is an awkward governance role.
- Artifact registry authority is still split across `data/artifact_registry.jsonl` and `data/state/artifact_registry.jsonl` references.
