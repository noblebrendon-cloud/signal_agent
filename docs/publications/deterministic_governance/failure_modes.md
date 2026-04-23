# Failure Modes

This file records risks that are directly supported by repo evidence and then names the three highest-value proof-hardening targets.

| Failure mode | Exact repo evidence | Current status | Why it matters | Hardening direction |
|---|---|---|---|---|
| Shadow execution outside the operator write boundary | `app/hq/capture/router.py`; `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py`; contrast: `signal_agent/operator/runtime.py` | partial and real | These mutators do not all reuse the same declared-read/write verification used by the operator runtime. | Extend operator-style boundary verification or equivalent pre-mutation checks to these surfaces. |
| Undeclared mutation outside the governed operator path | `signal_agent/operator/runtime.py`; `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py` | partial and real | The invariant is strongest where observed writes are compared to declared writes. Outside that path, proof weakens. | Add boundary-evidence checks or transactional wrappers to non-operator mutators. |
| Routing contract-resolution fall-through | `shared/contract.py`; `app/hq/capture/router.py`; `tests/test_phase2_improvements.py` | partial and real | Inference-only routing is now blocked, but broad exception fall-through in `shared/contract.py` can still demote lookup failures into weaker sources before the final routing decision. | Narrow exception handling and add authoritative-source precedence tests around contract resolution. |
| Policy incompleteness between normative graph and current flows | `config/state_machine.yaml`; `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py`; `tests/test_publication_pipeline_end_to_end.py` | real | The bundle now proves one named end-to-end publication path, but `config/state_machine.yaml` still declares a broader lifecycle than the repo proves across all lanes and emission surfaces. | Add more lane-specific end-to-end proofs and tighten implementation parity with the declared graph. |
| Documentation-only control claims | `docs/publications/v0.1.0_deterministic_constraint_kernel_technical_note.md`; `services/concept_formalization_spine/README.md`; this bundle | real risk if overclaimed | Publication files are evidence of publication surfaces, not enforcement by themselves. | Keep major claims attached to code, config, and tests. |
| Legacy or inferred downstream lineage | `signal_agent/content/lineage_status.py`; `signal_agent/operator/routing_lineage_drilldown.py` | real | Downstream linkage can remain `inferred`, and `signal_agent/operator/routing_lineage_drilldown.py` still discloses legacy catalog use. | Add canonical downstream identifiers and retire inferred joins. |
| Publication/release boundary verification remains weaker than the operator path | `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py`; contrast: `signal_agent/operator/runtime.py`; `tests/test_curate_publication_gate.py`; `tests/test_release_orchestrator.py` | real | Curation and release now use stronger atomic persistence, but they still do not prove declared-vs-observed mutation verification on their write surfaces. | Add operator-style boundary evidence or an equivalent declared-write verification layer to publication/release mutators. |
| Hardcoded path coupling | `app/hq/curation/curate.py` | real | Hardcoded absolute paths weaken portability and bounded-write reasoning. | Convert to repo-root-relative path resolution. |

## Top 3 Proof-Hardening Targets

| Rank | Type | Exact target path | Current gap | Proof gain if hardened |
|---|---|---|---|---|
| 1 | implementation surface | `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py` | One named end-to-end publication path is now proven, but neither surface proves operator-style declared-vs-observed boundary verification. | Moves publication/release surfaces closer to the operator-path invariant without changing their overall architecture. |
| 2 | implementation surface | `shared/contract.py` | Inference-only routing is now blocked, but `resolve_bundle_contract()` still uses broad exception fall-through that weakens source-precedence proof. | Makes routing authority precedence explicit and reduces ambiguity when registry lookup fails. |
| 3 | missing proof surface | `signal_agent/operator/runtime.py::_tool_observation_scope_paths`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | The operator path is the strongest live proof, but clause 5 still depends on an observation scope whose completeness is not fully proven. | Would strengthen the strongest existing invariant surface instead of broadening into new architecture. |

## Highest-Risk Interpretive Mistake

The main interpretive failure would be to claim that the repo proves a universal deterministic-governance invariant on every mutation path. The inspected evidence proves a strong operator write path, a real transition gate, several ledger surfaces, and partial routing, curation, publication, and release surfaces.
