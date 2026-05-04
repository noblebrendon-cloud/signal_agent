# Governance + Invariant Audit

## 1. Deterministic Execution
- status: PARTIAL
- evidence:
  - Canonical JSON and stable hashing exist in `app/governed_shell/proposal.py`, `app/governed_shell/logstore.py`, `app/retention/jsonl_store.py`, and `signal_agent/operator/runtime.py`.
  - Focused tests prove deterministic governed-shell hashing and deterministic retention reporting (`tests/test_governed_shell_normalize.py`, `tests/test_retention_appointments_summary.py`, `tests/test_retention_appointments_worklist.py`, `tests/test_retention_appointments_aging_alerts.py`).
- missing evidence:
  - `signal_agent/operator/runtime.py:73-75` and `:1291-1294` include current time in IDs.
  - `tools/verify_system.py` uses `time.time()` for unique curation inputs and therefore is not itself deterministic.
- recommended next action:
  - Narrow the claim to structural determinism, or remove time from identities where strict replay is required.

## 2. Declared Write Paths
- status: PARTIAL
- evidence:
  - Operator tools and workflows declare reads/writes in `config/operator/tools.yaml` and `config/operator/workflows.yaml`.
  - Module registry records state surfaces in `data/state/module_artifacts.jsonl`.
- missing evidence:
  - There is no single repo-wide declaration system covering every mutator outside the operator/module-registry surfaces.
- recommended next action:
  - Treat operator registry + module artifact registry as the two current authorities and explicitly document surfaces still outside them.

## 3. No Undeclared Mutation
- status: PARTIAL
- evidence:
  - `signal_agent/operator/runtime.py:920-989` assembles bounded observation scopes.
  - `signal_agent/operator/runtime.py:1640-1658` rejects in-scope undeclared mutation.
  - `tests/test_operator_write_contract.py` and `tests/test_operator_write_denial.py` cover mismatch rejection.
- missing evidence:
  - The observation model is bounded, not repo-complete.
  - Publication/release/capture surfaces do not all prove the same declared-vs-observed enforcement pattern.
- recommended next action:
  - Extend operator-style mutation verification to the next highest-value mutating lanes, starting with verifier/capture-adjacent surfaces.

## 4. Append-Only State Where Required
- status: PARTIAL
- evidence:
  - `app/utils/io_contract.py` provides locked append helpers.
  - `app/retention/jsonl_store.py` adds `prev_hash` / `record_hash` lineage.
  - Governed-shell audit logging is append-only and replay-verified.
- missing evidence:
  - Not every state-like surface is append-only; some remain overwrite artifacts by design.
  - The repo still contains dual artifact-registry references and a deprecated local activation ledger path.
- recommended next action:
  - Keep append-only claims scoped to named ledgers and resolve dual-registry authority.

## 5. Atomic Writes Where Required
- status: PARTIAL
- evidence:
  - `app/utils/io_contract.py:24-37` and `:122-168` provide atomic overwrite and append.
  - Retention CLI output files use `atomic_write_text()`.
  - Curation registry append / index write are covered by tests.
- missing evidence:
  - Operator session state uses a runtime-local atomic helper.
  - Transaction snapshots and some staged artifact writes bypass the shared helper.
- recommended next action:
  - Route session-state, snapshot, and staged-artifact persistence through the shared IO contract or explicitly bless them as aliases.

## 6. Fail-Closed Behavior On Policy Uncertainty
- status: PARTIAL
- evidence:
  - `app/hq/governance/transition_gate.py:265-325` rejects invalid states.
  - `app/governed_shell/policy.py` fails closed on missing/malformed policy and denied bindings.
  - Retention preview/authorization reject unclean or unsafe inputs.
- missing evidence:
  - Some helpers fall back or suppress errors instead of failing closed, such as `_safe_emit_upstream_transition()` in `app/intake/intake.py` and config-default fallback in `app/hq/curation/curate.py`.
- recommended next action:
  - Separate “strict governance boundary” behavior from “best-effort helper” behavior in docs and enforce stricter failure at selected helper seams.

## 7. Explicit Operator Authorization For External / Network Actions
- status: PARTIAL
- evidence:
  - Retention explicitly sets `external_actions_allowed: false`, `network_allowed: false`, `irreversible_action_allowed: false` in its registry record and code/docs.
  - Governed-shell MVP policy requires `network_allowed` and `privilege_escalation_allowed` to remain false.
- missing evidence:
  - The repo still includes provider/model and optional network-capable surfaces outside those local-only boundaries.
  - There is no single repo-wide authorization gate for every external-capable module.
- recommended next action:
  - Make the “external action boundary” an explicit cross-repo policy object instead of a per-subsystem convention.

## 8. Replayable Or Inspectable Decision History
- status: PARTIAL
- evidence:
  - Operator runs ledger and per-run records under `data/operator/`.
  - Transition-event ledger under `data/state/transition_gate_events.jsonl`.
  - Governed-shell audit/replay path with hash-chain verification.
  - Retention ledgers and appointment ledgers are inspectable and partially hash-chained.
- missing evidence:
  - Replay semantics are not unified across all subsystems.
  - Some downstream lineage remains inferred rather than exact.
- recommended next action:
  - Define a minimum replayability contract shared across operator, capture, curation, and release surfaces.

## 9. Separation Between Proposal, Approval, Plan, And Execution
- status: PARTIAL
- evidence:
  - Governed shell explicitly separates proposal, policy review, plan, and simulation.
  - Operator runtime separates intent parse, plan, and execution.
  - Retention separates proposal/approval/schedule/preview/authorization.
- missing evidence:
  - The separation is subsystem-specific rather than universal.
  - `tools/verify_system.py` mixes verification and live mutation smoke behavior.
- recommended next action:
  - Apply the same phase separation vocabulary to verifier and publication smoke paths.

## 10. Test-Backed Claims
- status: PARTIAL
- evidence:
  - Focused tests directly back major claims for operator writes, governed shell, retention, curation/release, runtime audit, and the invariant checker.
  - Current focused verification passed:
    - governed shell suite: `68 passed`
    - retention appointment reporting suite: `34 passed`
    - `tools/verify_system.py`: `passed`
- missing evidence:
  - Some docs still make broader repo-wide claims than the test surface proves.
  - `tools/verify_system.py` passing does not prove side-effect-free verification.
- recommended next action:
  - Add a verifier-boundary test proving whether verification is read-only by default or intentionally mutating behind an explicit flag.
