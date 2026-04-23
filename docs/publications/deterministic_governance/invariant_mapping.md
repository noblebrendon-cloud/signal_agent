# Invariant Mapping

This file maps each Determinism Invariant clause to exact repo files, exact tests, and an enforcement status.

| Invariant component | Exact enforcement files | Exact proving tests | Enforcement status | Claim label | Limitation |
|---|---|---|---|---|---|
| 1. Transformation allowed under policy for the current state | `app/hq/governance/transition_gate.py`; `config/state_machine.yaml`; `config/lanes.yaml`; `config/policies/intake_policy.yaml`; `config/policies/promotion_policy.yaml`; `config/policies/routing_policy.yaml`; `config/policies/publication_policy.yaml` | `tests/test_operator_write_denial.py`; `tests/test_operator_parser_entry.py`; `tests/security/test_transition_bypass.py`; `tests/test_publication_pipeline_end_to_end.py` | enforced on governed transition paths | `repo-proven` | One named `compiled -> staged -> emitted` publication path is now exercised end to end. Other publication lanes and emission surfaces still do not share operator-style boundary verification. |
| 2. Declared intent fully specifies intended reads/writes | `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `signal_agent/operator/runtime.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_intent_contract.py`; `tests/test_operator_parser_entry.py`; `tests/test_operator_compound_parser_entry.py` | enforced on operator ready-plan entrypoints | `repo-proven` | Parser/planner output and ready runtime entrypoints are registry-bound. This mapping is not proven for routing, curation, or release mutators. |
| 3. Observed effects on declared operator surfaces match or reject | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py` | enforced on declared operator mutation surfaces | `repo-proven` | The repo does not show the same boundary-evidence layer on every non-operator mutator. |
| 4. Transition recorded in lineage or ledgers | `app/hq/governance/transition_gate.py`; `signal_agent/operator/runtime.py`; `shared/state_registry.py`; `app/intake/intake.py`; `app/hq/capture/promote.py`; `app/hq/capture/router.py`; `services/release_orchestrator/runner.py` | `tests/test_operator_write_denial.py`; `tests/test_phase2_improvements.py`; `tests/test_release_orchestrator.py` | enforced on named ledger surfaces | `repo-proven` | `signal_agent/content/lineage_status.py` still reports `inferred` downstream links. |
| 5. No mutation occurs outside the declaration | `signal_agent/operator/runtime.py`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_contract.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py`; `tests/test_operator_compound_parser_entry.py` | enforced only on explicit operator observation scopes | `repo-supported` | Zero-write tools and declared-write tools now reject in-scope mutation outside the declared write set across tool reads, lifecycle writes, workflow authority/write paths, explicit declared directories, and immediate non-root parent directories of declared file surfaces. Mutation outside that bounded scope remains unproven. |

## Partial Or Missing Mappings

| Surface | Exact files | Current status | Why it is not `repo-proven` |
|---|---|---|---|
| Routing contract-resolution exception handling and source precedence | `shared/contract.py`; `app/hq/capture/router.py`; `tests/test_phase2_improvements.py` | partial | Inference-only routing is now rejected, but broad exception fall-through in `shared/contract.py` keeps this surface short of full operator-style proof. |
| Publication paths beyond the named docs-route proof | `app/hq/curation/curate.py`; `config/policies/publication_policy.yaml`; `config/state_machine.yaml`; `services/release_orchestrator/runner.py`; `tests/test_publication_pipeline_end_to_end.py` | partial | The repo now proves one named `compiled -> staged -> emitted` path, but it does not prove every publication lane or emission surface end to end. |
| Operator-style observed-write verification on publication and release surfaces | `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py`; `app/utils/io_contract.py` | partial | Curation and release now use stronger atomic persistence, but they still do not prove declared-vs-observed mutation verification like the operator runtime. |

## Most Complete Mapping In This Pass

The most complete clause coverage observed in this pass is:

- `signal_agent/operator/runtime.py`
- `config/operator/tools.yaml`
- `config/operator/workflows.yaml`
- `app/hq/governance/transition_gate.py`
- `tests/test_operator_write_contract.py`
- `tests/test_operator_transaction_snapshot.py`

Those files jointly prove declared intent, pre-mutation gating, observed-vs-declared rejection on declared operator surfaces, and fail-closed write denial on the governed operator path.
