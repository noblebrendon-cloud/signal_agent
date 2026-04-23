# Control Illusion Detection Test

## Definition

A system exhibits control illusion when oversight is present but one or more of the following are missing:

- comprehension
- timing authority
- intervention capability
- verification
- boundary enforcement

This test distinguishes symbolic review from actual control.

## Repo Check Matrix

| Check | Exact files | Exact tests | Enforcement status | Claim label | Notes |
|---|---|---|---|---|---|
| Comprehension | `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `signal_agent/operator/runtime.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | `tests/test_operator_write_intent_contract.py`; `tests/test_operator_parser_entry.py` | enforced on operator ready-plan entrypoints | `repo-proven` | Write authority is explicit and registry-backed, and ready runtime entrypoints reject plan/intent/workflow mismatches. |
| Timing authority | `signal_agent/operator/runtime.py`; `app/hq/governance/transition_gate.py` | `tests/test_operator_write_denial.py`; `tests/test_operator_transaction_snapshot.py` | enforced on operator write path | `repo-proven` | The gate runs before the governed mutator executes. |
| Intervention capability | `signal_agent/operator/runtime.py`; `app/hq/governance/transition_gate.py`; `app/governor/activation_governor.py` | `tests/test_operator_write_denial.py`; `tests/test_activation_governor.py` | enforced on operator and governor paths | `repo-proven` | These surfaces can reject, hold, or block. |
| Verification | `signal_agent/operator/runtime.py` | `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py` | enforced on declared operator surfaces | `repo-proven` | The runtime records boundary evidence and rejects observed-vs-declared mismatch on those surfaces. |
| Boundary enforcement | `config/operator/tools.yaml`; `config/operator/workflows.yaml`; `signal_agent/operator/runtime.py` | `tests/test_operator_write_contract.py`; `tests/test_operator_write_denial.py`; `tests/test_operator_duplicate_gate.py`; `tests/test_operator_compound_parser_entry.py` | enforced only on explicit operator observation scopes | `repo-supported` | Non-write workflows cannot dispatch mutating tools, and in-scope observed mutation outside the declared write set now rejects for both zero-write and declared-write tools. The remaining limit is scope completeness. |

## Governed Operator Write Path

| Result | Exact files | Exact tests | Claim label |
|---|---|---|---|
| Verification is fail-closed on declared operator surfaces, but boundary enforcement remains scope-bounded. | `signal_agent/operator/runtime.py`; `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml`; `app/hq/governance/transition_gate.py` | `tests/test_operator_write_intent_contract.py`; `tests/test_operator_write_contract.py`; `tests/test_operator_duplicate_gate.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py` | `repo-supported` |

## Partial Surfaces Outside The Operator Path

| Surface | Exact files | Current status | Why it remains partial |
|---|---|---|---|
| Routing contract authority | `shared/contract.py`; `app/hq/capture/router.py`; `tests/test_phase2_improvements.py` | partial | Inference-only routing now fails closed, but the broader routing surface remains partial because config fallback and plain log append do not match the operator boundary-verification pattern. |
| Curated publication staging | `app/hq/curation/curate.py`; `config/policies/publication_policy.yaml`; `app/hq/governance/transition_gate.py`; `tests/test_curate_publication_gate.py`; `tests/test_publication_pipeline_end_to_end.py` | partial | The staged surface now has focused gate and atomic-persistence tests plus one real downstream handoff into release emission, but it still lacks operator-style observed-vs-declared mutation verification. |
| Release emission and registry append | `services/release_orchestrator/contract.py`; `services/release_orchestrator/runner.py`; `services/release_orchestrator/feedback.py`; `tests/test_release_orchestrator.py`; `tests/test_publication_pipeline_end_to_end.py` | partial | Release manifest, constraints, and registry persistence now use shared atomic helpers, and one named registry-append failure now cleans up emitted files, but the release path still lacks operator-style declared-boundary verification. |
| Downstream lineage exactness | `signal_agent/content/lineage_status.py`; `signal_agent/operator/routing_lineage_drilldown.py` | partial | These files explicitly disclose `inferred` lineage and legacy catalog dependence. |

## Repo Verdict

- The repo proves fail-closed verification on declared operator surfaces, but boundary enforcement remains scope-bounded. `repo-supported`
- The repo does not prove the same control quality uniformly across routing, curation, publication, and release. `repo-supported`
- A repo-wide guarantee that every mutation surface passes the same five checks remains `theoretical`.
