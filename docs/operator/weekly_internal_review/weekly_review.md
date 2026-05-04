# Weekly Internal Review

## 1. Current System State

`signal_agent` currently behaves like a repo-native governance and operator-control system with three relatively strong proof surfaces: the operator runtime write boundary, the transition gate lifecycle controls, and the local-only retention subsystem. The repository is large and mixed-purpose, but those surfaces are backed by code, ledgers, and focused tests rather than by documentation alone. The strongest verified claim is not global repo determinism; it is bounded, fail-closed behavior for specific operator-controlled write paths.

## 2. What Got Stronger This Week

The module registry and `docs/operator/module_artifact_index.md` now give a materially clearer view of reviewed module status, including 15 active reviewed records and one deprecated historical record. The retention subsystem was formalized with a registration report and subsystem guide, which makes its local-only boundary much easier to reason about. The governed-shell proof surface is also now easier to trust because the focused schema/policy/log-replay suite passed cleanly during this review rather than being accepted on documentation alone.

## 3. What Is Now Verifiable

The governed-shell normalization, schema, policy, and log-replay path is test-backed and passed this review's focused run. The retention appointment summaries, worklists, and aging alerts are likewise test-backed and passed focused verification. `tools/verify_system.py` currently succeeds and exercises imports, invariant checks, and curation smoke behavior. The transition gate rejects invalid or forbidden transitions before operator-side handler dispatch, and the module registry is live enough to be consumed by invariant tooling.

## 4. What Is Still Unclear

The practical canonical root is still unclear because high-authority docs say `signal_agent/` is canonical while current governance implementation still lives heavily under `app/`. It is also unclear whether `tools/verify_system.py` is intended to be a read-only verifier or an allowed mutating smoke script. `governed_shell` remains technically mature enough to discuss seriously, but its module-governance status is unresolved because it does not appear in the active module registry. The canonical artifact-registry path is also still ambiguous because both `data/artifact_registry.jsonl` and `data/state/artifact_registry.jsonl` appear in real surfaces.

## 5. Highest-Risk Drift Points

- `tools/verify_system.py` mutates live repository state while presenting itself as system verification.
- Determinism claims in docs are stronger than the current time-based run IDs, transaction IDs, and transition timestamps justify.
- Canonical-root authority is split between `signal_agent/` documentation and `app/` runtime reality.
- Several older review and remediation docs now lag the active module registry and can mislead status reconstruction.
- Shared atomic/append-only IO discipline is strong but not yet universal because some runtime and curation paths still use bespoke write helpers.

## 6. Best Next Work

1. `verify_system` boundary. Why it matters: the current verifier changes live data, which makes repeated verification less trustworthy and raises operator surprise risk. Smallest safe next action: add a default read-only mode or an explicit `--mutating-smoke` flag and update the operator docs to match. Files likely involved: `tools/verify_system.py`, `docs/operator/verify_system_stabilization_report.md`, and any docs that tell operators to run the verifier. Test or verification gate: a focused test proving that default verification leaves curated artifact registries and processed-doc roots unchanged.
2. Determinism language cleanup. Why it matters: the current architecture is defendable, but the repo should not claim stronger determinism than the code actually enforces. Smallest safe next action: align docs to say which boundaries are deterministic and which identifiers are merely stable enough for audit. Files likely involved: `README.md`, `ARCHITECTURE.md`, `docs/publications/deterministic_governance/*.md`, `signal_agent/operator/runtime.py`, and `app/hq/governance/transition_gate.py`. Test or verification gate: targeted assertions around run ID and transaction ID construction plus a doc review against those tests.
3. IO contract unification. Why it matters: a single write discipline is easier to audit than several almost-equivalent atomic-write patterns. Smallest safe next action: inventory bespoke write helpers and migrate the lowest-risk callers first, especially snapshot writers that do not need special behavior. Files likely involved: `app/utils/io_contract.py`, `signal_agent/operator/runtime.py`, and `app/hq/curation/curate.py`. Test or verification gate: existing operator write-contract and curation tests plus one new regression that interrupts a snapshot write path.
4. `governed_shell` status decision. Why it matters: this module is mature enough to attract dependence, but its governance status is unresolved. Smallest safe next action: explicitly decide whether it stays an unregistered proof surface or enters the module registry with a clearly bounded status. Files likely involved: `data/state/module_artifacts.jsonl`, `docs/operator/module_artifact_index.md`, `docs/operator/governed_shell_mvp_acceptance.md`, and `docs/operator/governed_shell_integration_plan.md`. Test or verification gate: the governed-shell focused pytest suite plus invariant-check tooling if the module is registered.
5. Status-document reconciliation. Why it matters: stale promotion and remediation docs make restart and operator review slower than they need to be. Smallest safe next action: update or annotate the most misleading docs to point back to the current module artifact index rather than silently diverging. Files likely involved: `docs/operator/*.md` review and remediation files, especially older promotion reviews around capture, retention, and task-contract surfaces. Test or verification gate: rerun `tools/verify_system.py` after doc updates and confirm that the module index still parses consistently.

## 7. Do Not Touch Yet

- Broad migration of runtime code from `app/` into `signal_agent/`.
- Real outbound sender/network execution for retention.
- Large-scale cleanup across legacy `leviathan`, `laviathon`, and adjacent compatibility namespaces.
- Module status churn beyond evidence-backed doc alignment and explicit registration decisions.
- Any broad rewrite of the curation or operator runtime flow during a diagnostic week.

## 8. Operator Note

Resume from the executive summary, then decide the `verify_system` boundary first. After that, settle the `governed_shell` registration question and clean up determinism language before attempting any broader architectural tidy-up. Those three decisions will remove most of the current ambiguity without forcing a risky refactor.
