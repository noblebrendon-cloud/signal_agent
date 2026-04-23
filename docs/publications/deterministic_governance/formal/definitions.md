# Definitions

## Claim Labels

- `repo-proven`: implemented on a live path and backed by direct code plus tests or canonical runtime use.
- `repo-supported`: code, config, docs, or ledgers support the claim, but proof is partial, indirect, or path-limited.
- `theoretical`: useful model statement, but not yet demonstrated by the repo.

## Terms

- Transition: an attempted lifecycle move from one declared state to another.
- Policy allowed: the transition is accepted by the active gate, state machine, lane status, and policy checks.
- Declared intent: the explicit operator or workflow declaration that names what kind of action is allowed.
- Declared read/write boundary: the files or directories a governed tool is expected to inspect or mutate.
- Observed effect: the actual file-system or ledger change seen after execution.
- Recorded lineage: durable evidence in ledgers, registries, manifests, or lineage reconstruction surfaces.
- Control illusion: apparent oversight without actual comprehension, timing authority, intervention, verification, or boundary enforcement.
- Constraint-governed transformation: action that must pass declared constraints before mutation is allowed.

## Repo Scope

- Most complete proof surface identified in this pass: `signal_agent/operator/runtime.py`, `config/operator/tools.yaml`, `config/operator/workflows.yaml`, `app/hq/governance/transition_gate.py`, `tests/test_operator_write_contract.py`, and `tests/test_operator_transaction_snapshot.py`.
- Primary state authority surface identified in this pass: `app/hq/governance/transition_gate.py` and `config/state_machine.yaml`.
- Publication reuse files identified in this pass: `docs/publications/v0.1.0_deterministic_constraint_kernel_technical_note.md` and `docs/publications/v0.1.0_deterministic_constraint_kernel_framework_sheet.md`.

## Interpretation Rule

If a statement depends on a file path that only documents intent, the statement is not `repo-proven` unless a code path or test also enforces it.
