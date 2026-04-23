# Top 3 Missing Proofs

| rank | missing proof | target path | why it matters |
| --- | --- | --- | --- |
| 1 | Proof that the explicit operator observation scope fully covers every mutation-relevant surface for declared-write tools | `signal_agent/operator/runtime.py::_tool_observation_scope_paths`; `config/operator/tools.yaml`; `config/operator/workflows.yaml` | The runtime now rejects in-scope undeclared writes by declared-write tools, but clause 5 remains partial until the bounded observation scope itself is proven complete for operator mutators. |
| 2 | Operator-style observed-write verification on publication and release surfaces | `app/hq/curation/curate.py`; `services/release_orchestrator/runner.py`; `app/utils/io_contract.py` | One named end-to-end publication path is now proven, but curation and release still do not compare declared versus observed mutation the way `signal_agent/operator/runtime.py` does. |
| 3 | Routing contract-resolution source precedence under registry lookup failure | `shared/contract.py`; `app/hq/capture/router.py`; `tests/test_phase2_improvements.py` | Inference-only routing is now blocked, but `resolve_bundle_contract()` still uses broad exception fall-through before later sources are considered, so authoritative-source precedence remains only partial. |
