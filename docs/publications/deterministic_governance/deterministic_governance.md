# Deterministic Governance / Control Illusion

## Abstract

This document limits the model to repo-demonstrated surfaces in `E:\signal_agent`. The strongest repo-proven surfaces in this pass are the governed operator write path in `signal_agent/operator/runtime.py` and one named docs-route publication path from `compiled` to `staged` to `emitted` across `app/hq/curation/curate.py` and `services/release_orchestrator/runner.py`. Routing, other publication paths, and release boundary integrity outside that named path remain partial or theoretical.

## Claim Legend

- `repo-proven`: directly implemented on the exact named surface or tested path and backed by tests or a canonical runtime path with direct evidence.
- `repo-supported`: present in code, config, or docs, but only partially enforced, only partially tested, or broader than the exact proven surface.
- `theoretical`: useful model statement, but not demonstrated as a live repo invariant.

## A. Determinism Invariant

A transition is valid iff all of the following hold:

1. The transformation is allowed under policy for the current state.
2. Declared intent fully specifies intended reads and writes.
3. Observed effects match declared effects.
4. The transition is recorded in lineage or ledger surfaces.
5. No mutation occurs outside the declaration.

Formally:

`ValidTransition(t) iff PolicyAllowed(t) and DeclaredIntentComplete(t) and ObservedEffectsMatchDeclaredEffects(t) and RecordedInLineage(t) and NoMutationOutsideDeclaration(t)`

### Repo Mapping By Clause

| Invariant clause | Exact enforcement files | Exact proving tests | Enforcement status | Claim label | Notes |
|---|---|---|---|---|---|
| Policy allowed under current state | `app/hq/governance/transition_gate.py`; `config/state_machine.yaml`; `config/lanes.yaml`; `config/policies/intake_policy.yaml`; `config/policies/promotion_policy.yaml`; `config/policies/routing_policy.yaml`; `config/policies/publication_policy.yaml` | `tests/test_operator_write_denial.py`; `tests/test_operator_parser_entry.py`; `tests/security/test_transition_bypass.py`; `tests/test_publication_pipeline_end_to_end.py` | enforced on governed transition paths | `repo-proven` | The new end-to-end publication test exercises one real `compiled -> staged` publication-policy path through curation before release emission. Broader publication surfaces still do not share operator-style boundary verification. |
| Declared intent fully specifies reads and writes | `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `signal_agent/operator/runtime.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_intent_contract.py`; `tests/test_operator_parser_entry.py`; `tests/test_operator_compound_parser_entry.py` | enforced on operator ready-plan entrypoints | `repo-proven` | Parser/planner output and ready `OperatorRuntime.execute()` entrypoints are registry-bound. This clause is not claimed for routing, curation, or release mutators. |
| Observed effects on declared operator surfaces match or reject | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py` | enforced on declared operator mutation surfaces | `repo-proven` | The runtime now fails closed on `no_effect_observed`, transactional partials, zero-write observed mutation, and in-scope extra undeclared writes by declared-write tools. |
| Transition recorded in lineage or ledgers | `app/hq/governance/transition_gate.py`; `signal_agent/operator/runtime.py`; `shared/state_registry.py`; `app/intake/intake.py`; `app/hq/capture/promote.py`; `app/hq/capture/router.py`; `services/release_orchestrator/runner.py` | `tests/test_operator_write_denial.py`; `tests/test_phase2_improvements.py`; `tests/test_release_orchestrator.py` | enforced on named ledger surfaces | `repo-proven` | Exactness of downstream lineage varies; `signal_agent/content/lineage_status.py` still reports `inferred` links. |
| No mutation occurs outside the declaration | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_contract.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py`; `tests/test_operator_compound_parser_entry.py` | enforced only on explicit operator observation scopes | `repo-supported` | Zero-write tools and declared-write tools now reject observed mutation outside the declared write set on explicit read, authority, workflow-bound, and immediate non-root parent-directory scopes for declared file surfaces. Mutation outside that bounded observation scope remains unproven. |

### Clause 5 Scope Taxonomy

| mutation surface | covered | intentionally excluded | proof status | notes |
|---|---|---|---|---|
| Exact declared write paths | yes | no | `repo-proven` on operator path | Direct path snapshots still prove declared append and transactional mutations on the named operator write surfaces. |
| Explicit declared directories and current descendants | yes | no | `repo-proven` on operator path | `signal_agent/operator/runtime.py::_tool_observation_scope_paths` expands existing declared directories to current descendants. |
| Immediate non-root parent directories of declared file surfaces | yes | no | `repo-proven` on operator path | Sibling-file creation or deletion beside declared file surfaces is now observed and tested on both zero-write and declared-write operator flows. |
| Exact `.lock` companion of a declared append target | yes | no | `repo-proven` on operator append paths | `signal_agent/operator/runtime.py::_observed_changes_outside_declared_writes` treats the same-path `.lock` sidecar as auxiliary to the declared append target rather than as rogue mutation. |
| Repo-root-adjacent sibling mutation beside top-level declared files | no | yes | unproven | Repo root is intentionally excluded from derived parent-directory observation to avoid a broad top-level watch scope. |
| Undeclared locations outside the assembled operator scope | no | no | unproven | The proof boundary is limited to tool reads, lifecycle writes, workflow authority paths, workflow write paths, explicit declared directories, and immediate non-root parent directories for declared file surfaces. |
| Runtime bookkeeping surfaces such as `data/operator/runs/`, `data/operator/state/session_state.json`, and snapshot directories | no | yes | intentionally excluded | These are runtime-managed bookkeeping surfaces rather than tool-declared mutation surfaces for clause 5 proof on the operator path. |
| Auxiliary side effects beyond the exact declared path and exact `.lock` companion | no | no | unproven | The current proof boundary does not show that broader auxiliary artifacts are impossible or always rejected. |

### Intended Operator Clause 5 Contract

The intended long-term contract for the operator path is a bounded mutation-detection guarantee, not a stronger scope-completeness guarantee.

This contract is grounded in the live assembly logic in `signal_agent/operator/runtime.py::_tool_observation_scope_paths`, which explicitly watches:

- tool reads
- lifecycle writes
- workflow authority paths
- workflow write paths
- explicit declared directories and their current descendants
- immediate non-root parent directories of declared file surfaces

The bundle does not treat scope completeness as the intended contract because the current operator registry already includes broad directories such as `constraints/spines/` and `signal_agent/operator/`, runtime bookkeeping paths such as `data/operator/runs/operator_runs.jsonl` and `data/operator/state/session_state.json`, and top-level files such as `ARCHITECTURE.md`. Expanding clause 5 toward a broader completeness guarantee would materially increase false-positive risk from ambient repo activity, runtime-managed bookkeeping, and top-level sibling changes that are not part of the tool's declared mutation contract.

## B. Control Illusion Detection Test

A system exhibits control illusion when oversight is present but one or more of these are missing:

- comprehension
- timing authority
- intervention capability
- verification
- boundary enforcement

### Repo Check Matrix

| Check | Exact files | Exact tests | Enforcement status | Claim label | Notes |
|---|---|---|---|---|---|
| Comprehension | `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `signal_agent/operator/runtime.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_intent_contract.py`; `tests/test_operator_parser_entry.py` | enforced on operator ready-plan entrypoints | `repo-proven` | The action is bound to an explicit registry entry, and ready runtime entrypoints reject plan/intent/workflow mismatches. |
| Timing authority | `signal_agent/operator/runtime.py`; `app/hq/governance/transition_gate.py` | `tests/test_operator_write_denial.py`; `tests/test_operator_transaction_snapshot.py` | enforced on operator write path | `repo-proven` | Transition validation occurs before the governed tool handler runs. |
| Intervention capability | `signal_agent/operator/runtime.py`; `app/hq/governance/transition_gate.py`; `app/governor/activation_governor.py` | `tests/test_operator_write_denial.py`; `tests/test_activation_governor.py` | enforced on operator and governor paths | `repo-proven` | These paths can reject, hold, or block rather than only logging. |
| Verification | `signal_agent/operator/runtime.py` | `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py` | enforced on declared operator surfaces | `repo-proven` | The runtime records boundary evidence and rejects observed-vs-declared mismatch on those surfaces. |
| Boundary enforcement | `config/operator/tools.yaml`; `config/operator/workflows.yaml`; `signal_agent/operator/runtime.py` | `tests/test_operator_write_contract.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py`; `tests/test_operator_compound_parser_entry.py` | enforced only on explicit operator observation scopes | `repo-supported` | Non-write workflows are blocked, and in-scope observed mutation outside the declared write set now rejects for both zero-write and declared-write tools. The remaining limit is scope completeness, not lack of declared-write rejection inside that scope. |

### Repo Result

- The control-illusion test is strongest on the governed operator path, but boundary enforcement remains scope-bounded. `repo-supported`
- The same test is only partial on routing, curation, and release surfaces because `shared/contract.py`, `app/hq/curation/curate.py`, and `services/release_orchestrator/runner.py` do not all prove the same boundary-verification pattern. `repo-supported`

## C. Constraint-Governed Transformation Model

Replace:

`AI -> Human -> Action`

with:

`AI -> Constraint -> Action`

### Repo Mapping

| Statement | Exact files | Enforcement status | Claim label | Notes |
|---|---|---|---|---|
| The formula `AI -> Constraint -> Action` is a formal model. | `formal/invariant.tex`; `formal/control_test.tex` | not a runtime surface | `theoretical` | This is the model statement, not code. |
| On the operator write path, constraint checks occur before mutation. | `signal_agent/operator/runtime.py`; `app/hq/governance/transition_gate.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | enforced on operator write path | `repo-proven` | The runtime validates workflow mode, transition context, duplicate conditions, and boundary setup before dispatching the mutator. |
| Routing, curation, and release include lifecycle or constraint code, but do not uniformly prove the same pre-mutation boundary checks. | `shared/contract.py`; `app/hq/capture/router.py`; `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py` | partial | `repo-supported` | These surfaces exist, but the repo does not prove a uniform declared-boundary invariant across all of them. |
| A universal repo-wide `AI -> Constraint -> Action` invariant holds on every mutation surface. | `config/state_machine.yaml`; `config/lanes.yaml` | not proven | `theoretical` | `config/state_machine.yaml` explicitly notes that some current repo flows only partially implement the graph. |

## Major Repo-Demonstrated Claims

| Claim | Exact files | Exact tests | Claim label |
|---|---|---|---|
| Undefined or forbidden transitions are rejected before governed write execution. | `app/hq/governance/transition_gate.py`; `config/state_machine.yaml` | `tests/test_operator_write_denial.py`; `tests/security/test_transition_bypass.py` | `repo-proven` |
| Mutating tools cannot run inside non-write workflows. | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_contract.py` | `repo-proven` |
| Duplicate append attempts can be rejected before mutation. | `signal_agent/operator/runtime.py`; `config/operator/workflows.yaml` | `tests/test_operator_duplicate_gate.py`; `tests/test_operator_compound_parser_entry.py` | `repo-proven` |
| Transactional overwrite workflows capture pre-state snapshots and post-state hash evidence. | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml` | `tests/test_operator_transaction_snapshot.py` | `repo-proven` |
| Operator write mismatches now fail closed instead of returning `ok`. | `signal_agent/operator/runtime.py` | `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py` | `repo-proven` |
| The operator run ledger now appends through the shared atomic append primitive. | `signal_agent/operator/runtime.py`; `app/utils/io_contract.py` | `tests/test_operator_write_contract.py` | `repo-proven` |
| Routing rejects inference-only contract resolution. | `shared/contract.py`; `app/hq/capture/router.py` | `tests/test_phase2_improvements.py` | `repo-proven` |
| Release-local lifecycle transitions are enforced inside the release orchestrator. | `services/release_orchestrator/contract.py`; `services/release_orchestrator/runner.py` | `tests/test_release_orchestrator.py` | `repo-proven` |
| One named docs-route publication path is proven end to end across curation and release. | `app/hq/curation/curate.py`; `app/hq/governance/transition_gate.py`; `config/policies/publication_policy.yaml`; `services/release_orchestrator/runner.py` | `tests/test_publication_pipeline_end_to_end.py` | `repo-proven` |

## Non-goals

This artifact does not claim repo-wide invariant enforcement across every mutation surface.

It does not claim universal parser exclusivity, universal routing-source precedence, or universal publication-lane coverage.

For the governed operator path, clause 5 is not a scope-completeness guarantee. It is a bounded mutation-detection guarantee over declared and explicitly assembled observation surfaces.

This artifact also does not claim universal interception of all auxiliary side effects, universal repo-root sibling monitoring, or full parity between every downstream surface and the strongest operator-path enforcement model.

Where the repo does not prove a stronger claim, the bundle treats that boundary as partial or theoretical rather than implied.

## Future work

The next highest-value work is not broader rhetoric but broader proof.

Priority areas include:

1. Strengthening declared-vs-observed verification parity on additional publication and release lanes.
2. Proving more than one named compiled -> staged -> emitted path end to end.
3. Tightening routing-source precedence where registry lookup failure and fallback behavior still leave partial boundaries.
4. Improving downstream lineage exactness across broader lifecycle surfaces.
5. Exploring whether additional auxiliary artifact handling should remain explicitly bounded and opt-in, rather than expanding clause 5 toward global scope completeness.

Any future expansion of clause 5 beyond bounded mutation detection should be treated as an architectural change, not a documentation upgrade.

## Boundaries

- This document does not claim a universal invariant across every mutation path.
- This document treats publication files and whitepapers as evidence of publication surfaces, not as enforcement.
- The only repo-proven end-to-end publication flow in this bundle is the docs-route path exercised in `tests/test_publication_pipeline_end_to_end.py`.
- Where the repo still uses plain append, legacy catalogs, broad contract-resolution fall-through, or partial lifecycle coverage, those areas remain `repo-supported` or `theoretical`.
