# Deterministic Governance / Control Illusion

This bundle maps only repo-demonstrated governance behavior in `E:\signal_agent`. The strongest repo-proven surfaces in this pass are the governed operator write path and one named docs-route publication path from `compiled` to `staged` to `emitted`.

## Claim Legend

- `repo-proven`: implemented on the exact named surface or tested path and backed by code plus tests, or by a canonical runtime path with direct evidence.
- `repo-supported`: implemented or documented on a live path, but only partially enforced, only partially tested, or broader than the exact proven surface.
- `theoretical`: model statement or hardening target, not demonstrated as a live repo invariant.

## Proof Boundary Summary

| Surface | Current proof boundary |
|---|---|
| Governed operator write path | `repo-proven` on exact operator ready-plan and declared mutation surfaces in `signal_agent/operator/runtime.py`. The intended clause-5 contract on this path is a bounded mutation-detection guarantee on explicit operator observation scopes, not a global scope-completeness guarantee. The bounded scope now also covers sibling-file mutation beside declared file surfaces through immediate non-root parent-directory observation. |
| Named docs-route publication path | `repo-proven` for one tested path: compiled markdown input -> `app/hq/curation/curate.py` staged docs artifact -> `services/release_orchestrator/runner.py` emitted manifest, constraints, and registry, with fail-closed cleanup on release registry append failure. |
| Other routing, publication, and release surfaces | `repo-supported`. They do not yet share the operator path's declared-vs-observed boundary verification pattern. |
| Repo-wide invariant across every mutation surface | `theoretical`. This bundle does not claim a universal end-to-end invariant across all lanes, mutators, or emission surfaces. |

## How this repo demonstrates the invariant live

| Major claim | Exact repo files | Enforcement status | Claim label | Notes |
|---|---|---|---|---|
| Forbidden, undefined, or policy-failing transitions are rejected before governed write execution. | `app/hq/governance/transition_gate.py`; `config/state_machine.yaml`; `config/lanes.yaml`; `config/policies/intake_policy.yaml`; `config/policies/promotion_policy.yaml`; `config/policies/routing_policy.yaml`; `config/policies/publication_policy.yaml`; `tests/test_operator_write_denial.py`; `tests/security/test_transition_bypass.py` | enforced on governed transition paths | `repo-proven` | The gate rejects unknown states, forbidden transitions, undefined transitions, and lane or policy failures. |
| Mutating operator actions are bound to declared intents, tools, workflows, and write paths. | `signal_agent/operator/intent.py`; `signal_agent/operator/registry.py`; `signal_agent/operator/runtime.py`; `config/operator/intents.yaml`; `config/operator/tools.yaml`; `config/operator/workflows.yaml`; `tests/test_operator_write_intent_contract.py`; `tests/test_operator_parser_entry.py` | enforced on operator ready-plan entrypoints | `repo-proven` | The write parser is narrow, and `OperatorRuntime.execute()` now rejects ready plans whose workflow, tool chain, requested workflow, or intent binding do not match the registry. |
| Observed operator effects on declared surfaces are checked and mismatch rejects. | `signal_agent/operator/runtime.py`; `tests/test_operator_write_contract.py`; `tests/test_operator_transaction_snapshot.py`; `tests/test_operator_write_denial.py`; `docs/operator_mutation_contract.md` | enforced on declared operator mutation surfaces | `repo-proven` | The runtime now converts `no_effect_observed`, transactional partials, zero-write observed mutation, and in-scope extra undeclared writes by declared-write tools into `contract_violation`. The bounded operator observation scope now also catches sibling-file mutation beside declared file surfaces through immediate non-root parent-directory observation. |
| Atomic append and atomic overwrite primitives already exist and are used on state and operator ledger surfaces. | `app/utils/io_contract.py`; `shared/state_registry.py`; `app/governor/activation_governor.py`; `signal_agent/operator/runtime.py`; `tests/test_activation_governor.py`; `tests/test_operator_write_contract.py` | enforced on those surfaces | `repo-proven` | The operator run ledger now appends through `append_jsonl_atomic`, closing the prior plain-append gap on that surface. |
| Routing contract resolution exists, and inference-only contracts are non-authoritative. | `shared/contract.py`; `app/hq/capture/router.py`; `tests/test_phase2_improvements.py` | enforced on routing eligibility decisions | `repo-proven` | `member_inference` remains a low-confidence signal, but `shared/contract.py` marks it non-routable and `app/hq/capture/router.py` fails closed when no authoritative contract source exists. |
| A release-local lifecycle FSM and release persistence path exist. | `services/release_orchestrator/contract.py`; `services/release_orchestrator/runner.py`; `services/release_orchestrator/feedback.py`; `app/utils/io_contract.py`; `tests/test_release_orchestrator.py` | release-local FSM and named persistence surfaces enforced | `repo-proven` | The release orchestrator proves a local FSM, writes the manifest and next-release constraints through `atomic_write_text`, appends the registry through `append_jsonl_atomic`, and now removes the emitted release directory if registry append fails. |
| One named publication path from `compiled` to `staged` to `emitted` is proven across curation and release. | `app/hq/curation/curate.py`; `app/hq/governance/transition_gate.py`; `config/policies/publication_policy.yaml`; `services/release_orchestrator/runner.py`; `tests/test_publication_pipeline_end_to_end.py` | enforced on one named docs-route publication path | `repo-proven` | The test runs the real curation gate into a staged docs artifact, feeds that staged artifact into `run_release()`, and proves fail-closed cleanup when the final release registry append fails. No broader publication lane or emission-surface claim is made here. |
| Existing publication and whitepaper surfaces are present in the repo. | `docs/publications/v0.1.0_deterministic_constraint_kernel_technical_note.md`; `docs/publications/v0.1.0_deterministic_constraint_kernel_framework_sheet.md`; `services/concept_formalization_spine/README.md`; `services/concept_formalization_spine/examples/sample_project/whitepaper.md`; `app/hq/exporter.py` | existing publication/export files only | `repo-supported` | These are publication surfaces, not proof by themselves. |

## Bundle Contents

- [deterministic_governance.md](deterministic_governance.md)
- [repo_surface_inventory.md](repo_surface_inventory.md)
- [invariant_mapping.md](invariant_mapping.md)
- [control_illusion_test.md](control_illusion_test.md)
- [implementation_evidence.md](implementation_evidence.md)
- [failure_modes.md](failure_modes.md)
- [publication_manifest.yaml](publication_manifest.yaml)
- [formal/definitions.md](formal/definitions.md)
- [formal/invariant.tex](formal/invariant.tex)
- [formal/control_test.tex](formal/control_test.tex)
- [README_patch_proposal.md](README_patch_proposal.md)
- [release/CITATION.cff](release/CITATION.cff)
- [release/zenodo_metadata.json](release/zenodo_metadata.json)
- [release/release_notes_v1.md](release/release_notes_v1.md)

## Diagram Sources

- [diagrams/illusion_model.mmd](diagrams/illusion_model.mmd)
- [diagrams/governed_model.mmd](diagrams/governed_model.mmd)
- [diagrams/invariant_flow.mmd](diagrams/invariant_flow.mmd)
- [diagrams/enforcement_surface_map.mmd](diagrams/enforcement_surface_map.mmd)
- [diagrams/failure_modes_map.mmd](diagrams/failure_modes_map.mmd)

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

## Scope Discipline

- No runtime governance behavior is changed by this bundle.
- No new enforcement abstraction is introduced.
- The most complete invariant proof identified in this pass is the operator write path centered on `signal_agent/operator/runtime.py`.
- The intended long-term clause-5 contract for the operator path is bounded mutation detection on declared and explicitly assembled observation surfaces, not universal mutation-scope completeness.
- The only repo-proven end-to-end publication flow identified in this pass is the docs-route path exercised in `tests/test_publication_pipeline_end_to_end.py`.
- Routing, curation, publication, and release are included only to the extent that code, config, or tests actually demonstrate them.
