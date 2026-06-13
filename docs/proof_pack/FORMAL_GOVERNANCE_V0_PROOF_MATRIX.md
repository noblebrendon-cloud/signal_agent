# Formal Governance V0 Proof Matrix

This matrix maps V0 proof obligations to the isolated formal-governance proof pack.

This proves the isolated formal-governance proof pack V0. It does not yet prove repo-wide integration across HQ, operator, Governed Authoring, or claim runtime paths.

| Proof obligation | Evidence files | Test evidence | V0 status | Repo-wide status |
| --- | --- | --- | --- | --- |
| Package imports cleanly | `signal_agent/formal_governance/__init__.py` | Import command returned `formal_governance_import_ok` | Proven in isolation | Not an integration claim |
| Typed primitives exist | `signal_agent/formal_governance/models.py` | `tests/test_formal_governance_models.py` | Proven in isolation | Not yet wired into active runtimes |
| Decision outcomes are typed | `DecisionOutcome`, `PromotionDecision` in `models.py`; `decision.py` | `tests/test_formal_governance_models.py`, `tests/test_formal_governance_decision.py` | Proven in isolation | Active HQ/operator decisions still use existing subsystem shapes |
| Deterministic decision id is stable | `decision.py`, `hashing.py` | `test_duplicate_fixture_has_same_deterministic_transition_identity_as_valid_fixture`, ledger determinism test | Proven in isolation | Repo-wide deterministic identity not yet adopted |
| Timestamped ledger entry id is separate | `ledger.py` | `test_deterministic_decision_id_is_separate_from_timestamped_ledger_entry_id` | Proven in isolation | Existing subsystem ledgers still use their own ids |
| Lineage gate | `gates.py`, `missing_lineage.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Existing runtime lineage remains subsystem-specific |
| Invariant gate | `gates.py`, `missing_invariant.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Active promotion paths do not yet require formal invariant objects |
| Branch vector gate | `gates.py`, `branch_vector.v1.schema.json` | `tests/test_formal_governance_models.py`, `tests/test_formal_governance_decision.py` | Proven in isolation | Branch vectors are not yet required by HQ/operator paths |
| Raw artifact self-promotion rejection | `gates.py`, `raw_artifact_self_promotion.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | HQ promotion artifact/state separation still needs integration work |
| Evidence gate | `gates.py`, `missing_evidence.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Active claim engine still needs enforcement integration |
| Unresolved tension gate | `gates.py`, `unresolved_tension_blocking.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | No repo-wide unresolved tension gate yet |
| Human authority gate | `gates.py`, `missing_human_authority.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Human authority is not yet required across active promotions |
| Self-certification rejection | `gates.py`, `generator_self_certification.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Governed shell has related proof; repo-wide application remains future work |
| Rollback gate | `gates.py`, `rollback_required_missing.json` | `tests/test_formal_governance_decision.py` | Proven in isolation | Operator snapshots remain separate from formal rollback primitive |
| Duplicate transition block | `gates.py`, `duplicate_transition.json`, `ledger.py` | `tests/test_formal_governance_decision.py`, CLI proof-pack test | Proven in isolation | Existing duplicate blocking remains bounded to selected paths |
| Canonical ledger entry fields | `ledger.py`, `governed_transition_ledger_entry.v1.schema.json` | `tests/test_formal_governance_ledger.py` | Proven in isolation | Production ledgers are not yet canonical formal ledger entries |
| Hash chaining | `ledger.py` | `test_ledger_hash_chain_links_subsequent_entries` | Proven in isolation | Existing governed-shell hash chain remains separate |
| CLI temporary proof output | `cli.py` | `tests/test_formal_governance_cli.py` | Proven in isolation | No production CLI integration claim |
| Existing transition/operator proof remains intact | Existing transition/operator files | 80 existing tests passed | No regression observed | Still bounded to existing paths |
| Existing governed-shell proof remains intact | `app/governed_shell/*` | 31 governed-shell tests passed under `.venv` | No regression observed | Governed-shell remains subsystem proof |

## Matrix Conclusion

V0 closes the high-risk formalization gaps in one isolated proof surface: primitives, gates, deterministic decisions, canonical ledger entries, fixtures, and tests.

It does not close repo-wide integration gaps. The next implementation phase should connect the proof pack to claim evidence enforcement, HQ promotion artifact/state separation, canonical ledger adapters, Governed Authoring backend flow, and repo-wide self-certification boundaries.

