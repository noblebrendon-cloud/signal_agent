# Repo Surface Inventory

Repo root inspected: `E:\signal_agent`

Confidence levels:

- `high`: direct code or config authority on a live path.
- `medium`: live surface exists, but claim strength is partial or path-limited.
- `low`: useful supporting context, not primary enforcement authority.

| File path | Invariant concepts | Confidence | Notes |
|---|---|---|---|
| `app/hq/governance/transition_gate.py` | transition gating; policy validation; fail-closed denial; canonical transition events | high | Rejects unknown states, forbidden transitions, undefined transitions, and policy failures; emits gate events. |
| `config/state_machine.yaml` | state machine enforcement; allowed transitions; forbidden transitions; control-state expiry | high | Declares working and control states, gates, forbidden transitions, and notes that some flows remain partial. |
| `config/policies/intake_policy.yaml` | policy validation | high | Declares required conditions and forbidden actions for intake and normalization. |
| `config/policies/promotion_policy.yaml` | policy validation | high | Declares deterministic promotion requirements and append-only promotion logging expectations. |
| `config/policies/routing_policy.yaml` | policy validation | high | Declares deterministic routing and forbids direct external emission during routing. |
| `config/policies/publication_policy.yaml` | policy validation; publication gating | medium | Publication policy exists in code and config, and one named `compiled -> staged -> emitted` path is now proven end to end, but broader publication surfaces remain partial. |
| `config/lanes.yaml` | lane authorization; policy assignment; publication surfaces | high | Declares lane status, governing policies, transform stacks, emission surfaces, and a partial `concept_formalization` lane. |
| `signal_agent/operator/runtime.py` | declared reads/writes enforcement; execute-entrypoint contract binding; observed-vs-declared mutation checking; duplicate prevention; transactional verification; operator run ledger | high | Covers pre-dispatch gate checks, registry-bound ready-plan validation, declared write paths, boundary evidence, and the operator run ledger. |
| `signal_agent/operator/intent.py` | parser non-authority; strict intent binding | high | Write intents are extracted narrowly and malformed write commands fail closed. |
| `signal_agent/operator/registry.py` | declared intent; tool and workflow authority loading | high | Loads workflow, tool, and intent declarations from config. |
| `config/operator/intents.yaml` | declared intent | high | Declares bounded operator intents rather than open-ended natural language authority. |
| `config/operator/tools.yaml` | declared reads/writes; transactional mutation declaration | high | Declares read and write surfaces per tool, plus transactional overwrite semantics. |
| `config/operator/workflows.yaml` | declared authority paths; write boundaries; transition context | high | Declares workflow mode, write paths, authority paths, and transition context. |
| `docs/operator_mutation_contract.md` | declared-write contract; fail-closed semantics | medium | Documentation matches the operator runtime model and is useful as supporting interpretation, not as primary proof. |
| `app/utils/io_contract.py` | append-only ledgers; atomic write discipline | high | Provides atomic text overwrite and locked JSONL append with rollback on failure. |
| `shared/state_registry.py` | append-only registry | high | Canonical artifact-state registry appends through `append_jsonl_atomic`. |
| `app/governor/activation_governor.py` | fail-closed denial; drift blocking; governor event ledger | high | Blocks mutating scopes on invalid state, drift, or unauthorized scope. |
| `app/intake/intake.py` | intake ledger; governed early lifecycle writes | high | Appends `data/intake/intake.jsonl` and emits transition events. |
| `app/hq/capture/promote.py` | promotion gating; promotion ledger | high | Validates transitions and writes `data/capture/promotion_log.jsonl`. |
| `app/hq/capture/router.py` | routing gate; routing ledger; contract resolution | medium | Uses lifecycle resolution and routing logs, and now fails closed on non-authoritative `member_inference`, but broader routing proof remains partial. |
| `shared/contract.py` | contract resolution; parser non-authority risk surface | medium | Resolution order still includes `member_inference` as a low-confidence signal, but it is now non-authoritative for routing. Broad exception fall-through remains a partiality source. |
| `app/hq/curation/curate.py` | curation gate; artifact registration; staged output surface | medium | Uses governor enforcement, transition validation, content-hash verification, atomic registry append, and atomic index rewrite on the named staged surface, and that surface is now exercised in one end-to-end publication-path test. |
| `signal_agent/content/lineage_status.py` | recorded lineage; inferred lineage detection | medium | Explicitly tracks `exact`, `inferred`, `missing`, and `orphaned` lineage quality. |
| `signal_agent/operator/capture_routing_status.py` | observed-vs-configured routing status | medium | Reconstructs observed routes from ledgers and incoming directories. |
| `signal_agent/operator/routing_lineage_drilldown.py` | lineage reconstruction; legacy registry dependency disclosure | medium | Explicitly discloses legacy catalog use and inferred downstream lineage. |
| `app/audit/runtime_audit.py` | audit surface; contract evaluation | low | Useful audit tooling, but not a primary mutation-enforcement surface in this pass. |
| `app/audit/task_contract.py` | contract schema enforcement | medium | Validates task contract structure and acceptance criteria. |
| `task_contract.yaml` | declared acceptance contract | medium | Existing contract artifact, useful for audit and release checks. |
| `tests/test_operator_write_intent_contract.py` | parser rejection proof; runtime plan-contract proof | high | Tests strict, fail-closed write-intent parsing and ready runtime rejection of intent/workflow mismatch. |
| `tests/test_operator_write_contract.py` | mutation-boundary proof | high | Tests consistency classification and declared-vs-observed write behavior. |
| `tests/test_operator_parser_entry.py` | parser entry and denial proof | high | Tests valid execution, denied paths, and invalid-command rejection. |
| `tests/test_operator_compound_parser_entry.py` | multi-step gate proof | high | Tests duplicate denial and step-level hold or rejection in compound workflows. |
| `tests/test_operator_write_denial.py` | fail-closed rejection proof | high | Tests forbidden transitions and missing transition-context rejection. |
| `tests/test_operator_transaction_snapshot.py` | transactional verification proof | high | Tests pre-state snapshots and denied transactional paths. |
| `tests/test_operator_duplicate_gate.py` | read-before-write duplicate prevention | high | Tests duplicate detection with no mutation. |
| `tests/test_activation_governor.py` | drift and scope blocking proof | high | Tests governor lock, override, and fail-closed blocking behavior. |
| `tests/test_phase2_improvements.py` | routing contract-resolution proof | high | Tests stale guard, frontmatter resolution, non-authoritative `member_inference`, and routing log behavior. |
| `tests/test_release_orchestrator.py` | release-local FSM and output-path proof | high | Tests release transition validity, full release run, atomic manifest/constraint persistence, atomic registry append, and append-failure propagation. |
| `tests/test_publication_pipeline_end_to_end.py` | end-to-end publication-path proof | high | Tests one real `compiled -> staged -> emitted` docs-route path across curation and release, plus fail-closed cleanup when the final release registry append fails. |
| `tests/test_curate_publication_gate.py` | curation gate and persistence proof | high | Tests `compiled -> staged` success and rejection paths plus atomic registry append and atomic index rewrite. |
| `tests/security/test_transition_bypass.py` | transition-bypass and prerequisite-skip rejection proof | high | Exercises forbidden transitions, terminal escapes, undefined states, and prerequisite skipping through the real gate. |
| `docs/publications/v0.1.0_deterministic_constraint_kernel_technical_note.md` | prior publication surface | medium | Existing publication artifact; useful as publication evidence, not enforcement proof. |
| `docs/publications/v0.1.0_deterministic_constraint_kernel_framework_sheet.md` | prior publication surface | medium | Existing publication artifact; useful as publication evidence, not enforcement proof. |
| `services/concept_formalization_spine/README.md` | whitepaper and artifact-generation arm | medium | Existing concept-formalization arm exists, but lane status is only `partial`. |
| `services/concept_formalization_spine/examples/sample_project/whitepaper.md` | example whitepaper output | medium | Example output surface demonstrating the arm exists. |
| `services/release_orchestrator/contract.py` | release-local lifecycle FSM | medium | Enforces a local release lifecycle separate from `config/state_machine.yaml`. |
| `services/release_orchestrator/runner.py` | release surface; manifest and registry emission | medium | Writes release manifests through `atomic_write_text`, appends the release registry through `append_jsonl_atomic`, removes the emitted release directory if registry append fails, and still remains partial because it lacks operator-style boundary verification. |
| `app/hq/exporter.py` | export surface | low | Export mechanism exists but is narrow and redacted rather than a full publication pipeline. |

## Inventory Summary

- `signal_agent/operator/runtime.py` plus `config/operator/tools.yaml`, `config/operator/workflows.yaml`, `app/hq/governance/transition_gate.py`, and the operator tests provide the most complete invariant coverage identified in this pass.
- `shared/contract.py`, `app/hq/capture/router.py`, `app/hq/curation/curate.py`, and `services/release_orchestrator/runner.py` are real governance-adjacent surfaces, but their proof quality is lower because they do not all reuse the same explicit boundary-verification and append-discipline pattern.
- Publication files under `docs/publications/` and `services/concept_formalization_spine/` are treated here as publication surfaces only, not enforcement surfaces.
