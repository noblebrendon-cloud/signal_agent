# System Purpose Reconstruction

## 1. Actual System Purpose

`signal_agent` is best understood as a repo-native deterministic governance and operational-control system, not just a single application.

The strongest live surfaces are:
- a governed operator runtime that maps bounded natural-language requests onto declared workflows and write contracts
- a transition-gated artifact lifecycle controlled by `config/state_machine.yaml` and `config/lanes.yaml`
- append-only and atomic state-handling utilities
- local-only governed subsystems such as retention and governed shell that explicitly stop short of unconstrained execution or external sending

## 2. Core Operating Model

The repo uses a layered operating model:

1. Inputs, artifacts, or operator requests enter through bounded surfaces.
2. Lifecycle progression is validated against a canonical state machine and lane/policy configuration.
3. Mutations are expected to be declared, observable, and recorded in append-only ledgers or controlled artifacts.
4. Operator-facing registries and module-artifact metadata define what is authoritative.
5. Audit/replay/report surfaces reconstruct or verify what happened.

The clearest concrete chains are:
- operator intent -> workflow registry -> tool contract -> transition gate -> bounded mutation -> operator ledger
- retention event -> reconciliation -> dispatch gate -> send queue projection -> local preview -> explicit authorization -> still no external send
- governed-shell proposal -> schema validation -> policy review -> audit/replay and plan/simulation scaffolding, with no real execution admitted

## 3. Main Invariants

The repo repeatedly asserts these invariants in code and docs:
- no governed state change without transition validation (`app/hq/governance/transition_gate.py`)
- fail closed on invalid states, unknown commands, malformed policy/config, or unclean downstream artifacts
- append-only ledgers where historical trace matters
- atomic writes for ledgers and many whole-file outputs (`app/utils/io_contract.py`)
- explicit declaration of write surfaces in the operator layer (`config/operator/tools.yaml`, `config/operator/workflows.yaml`)
- local-only / no-network boundaries for retention and governed shell MVP paths
- module-boundary formalization through `data/state/module_artifacts.jsonl`

## 4. Main State Transitions

### Canonical artifact lifecycle
`config/state_machine.yaml` defines the main working progression:
- `captured -> normalized -> classified -> constrained -> promoted -> routed -> transformed -> compiled -> staged -> emitted -> audited`

It also defines control states:
- `held`
- `rejected`
- `failed`
- `aborted`

### Operator execution lifecycle
`signal_agent/operator/intent.py`, `planner.py`, and `runtime.py` implement:
- command text parsing
- workflow resolution
- write-contract checking
- optional transition validation for write-mode workflows
- post-dispatch boundary evidence and ledger writes

### Retention lifecycle
The retention guide documents a local-only chain:
- contact event append
- reconciliation
- dispatch readiness gate
- send queue projection
- local preview
- explicit local authorization

### Governed-shell review lifecycle
The governed-shell docs and tests support:
- proposal load
- schema validate
- normalize/hash
- policy evaluate
- append-only review audit
- replay/verify
- sealed plan + simulation scaffolding in later phases

## 5. Main Modules And Their Roles
- `signal_agent/operator/*`
  - internal operator control surface and bounded runtime
- `app/hq/governance/transition_gate.py`
  - lifecycle gate and transition-event emission
- `app/utils/io_contract.py`
  - shared atomic append / atomic overwrite primitives
- `app/retention/*`
  - governed local retention spine
- `app/governed_shell/*`
  - proposal-only shell governance surface
- `app/hq/capture/*`
  - volatile capture, promotion, routing, decay, instability
- `app/hq/curation/curate.py`
  - deterministic staged-publication surface
- `app/audit/*`
  - runtime audit facade, evidence collection, contract evaluation, coherence kernel
- `app/providers/*`
  - deterministic provider metadata and fallback registry behavior

## 6. What “Governance” Means In This Repo

In this repo, governance does not mean a single policy document. It means a collection of runtime and metadata controls:
- declared state machine and lane model (`config/state_machine.yaml`, `config/lanes.yaml`)
- gate-based validation before mutation (`app/hq/governance/transition_gate.py`)
- append-only / atomic persistence (`app/utils/io_contract.py`)
- declared tool read/write contracts in the operator layer (`config/operator/*.yaml`)
- module-boundary registration (`data/state/module_artifacts.jsonl`)
- proof surfaces in tests and operator review documents

## 7. What “Fail-Closed” Means In Practice

In practice, fail-closed means:
- unknown or invalid lifecycle endpoints are rejected by `validate_transition()`
- forbidden transitions are rejected before handlers run
- governed-shell policy loading or validation errors deny the proposal rather than falling back
- retention preview/authorization reject unsafe or inconsistent queue/preview artifacts
- operator write-contract mismatches become `contract_violation` rather than soft warnings

It does not mean every part of the repo aborts on every uncertainty. Some helper paths still degrade or default more softly than the docs imply, for example `_safe_emit_upstream_transition()` in `app/intake/intake.py` swallows gate exceptions and `load_config()` in `app/hq/curation/curate.py` can fall back to defaults.

## 8. What Is Currently Production-Like vs Experimental

### Production-like / live-governed surfaces
- operator runtime and registries
- transition gate
- IO contract helpers
- retention local-governance path
- governed-shell schema/policy/audit/replay path
- runtime audit split surfaces (`runtime_audit`, `runtime_audit_evidence`, `task_contract`)
- module artifact registry and invariant checker

### Experimental / legacy / ambiguous surfaces
- legacy namespace and site roots (`leviathan/`, `laviathon/`, `site_laviathon/`)
- broad top-level workspace directories not tied to canonical entrypoints
- `tools/verify_system.py` as a verifier: it passes, but behaves partly like a live smoke script because it mutates repo data during curation checks
- governed shell execution itself: docs explicitly say execution does not exist after the current phases

## 9. Difference Between First Impression And Reconstructed Understanding

The first-impression guess was directionally correct about governance, auditability, and bounded automation.

The deeper reconstruction changes the picture in three important ways:
- the repo is less a single agent and more a control plane spanning operator runtime, artifact lifecycle governance, retention, capture/curation, and diagnostics
- the strongest demonstrated invariant is not repo-wide determinism; it is the bounded operator write path plus a few adjacent governed subsystems
- some claims in docs are broader than the live proof surface, so the system should be described as strongly governed in specific paths rather than uniformly governed everywhere
