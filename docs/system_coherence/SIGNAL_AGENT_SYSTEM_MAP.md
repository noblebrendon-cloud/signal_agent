# Signal Agent System Map

**Status**: evidence-mapped from live repo
**Classification**: each entry is marked **[IMPLEMENTED]**, **[EMERGING]**, or **[FUTURE]**

---

## 1. Canonical Package Root

**[IMPLEMENTED]**

| Surface | Path | Evidence |
|---|---|---|
| Python package root | `signal_agent/` | `ARCHITECTURE.md`, `README.md` |
| Operator runtime | `signal_agent/operator/runtime.py` (97,835 bytes) | `GOVERNANCE_KERNEL.md §4.1` |
| Intent parser | `signal_agent/operator/intent.py` | `GOVERNANCE_KERNEL.md §4.1` |
| Workflow planner | `signal_agent/operator/planner.py` | `GOVERNANCE_KERNEL.md §4.1` |
| Tool/workflow registry | `signal_agent/operator/registry.py` | `GOVERNANCE_KERNEL.md §4.1` |
| Invariant checker | `signal_agent/operator/invariant_checker.py` | `docs/operator/OPERATOR_INDEX.md` |
| Capture routing status | `signal_agent/operator/capture_routing_status.py` | Tests: `test_operator_capture_routing_status.py` |
| Routing lineage drilldown | `signal_agent/operator/routing_lineage_drilldown.py` | Tests: `test_operator_routing_lineage_drilldown.py` |
| Routing queue backlog | `signal_agent/operator/routing_queue_backlog.py` | Tests: `test_operator_routing_queue_backlog.py` |
| Operator CLI | `signal_agent/cli/operator_cli` | `docs/operator/OPERATOR_INDEX.md` |

---

## 2. Governance Kernel

**[IMPLEMENTED]**

| Component | Path | Evidence |
|---|---|---|
| Transition gate | `app/hq/governance/transition_gate.py` (17,970 bytes) | `GOVERNANCE_KERNEL.md §3.1, §4.1` |
| State machine | `config/state_machine.yaml` (7,834 bytes) | `GOVERNANCE_KERNEL.md §4.1` |
| Lane registry | `config/lanes.yaml` (5,443 bytes) | `GOVERNANCE_KERNEL.md §4.1` |
| Tool declarations | `config/operator/tools.yaml` | `GOVERNANCE_KERNEL.md §3.5` |
| Workflow definitions | `config/operator/workflows.yaml` | `GOVERNANCE_KERNEL.md §3.5` |
| Policy configs | `config/policies/*.yaml` | `GOVERNANCE_KERNEL.md §4.1` |
| Authority layer | `shared/authority.py` (7,001 bytes) | `GOVERNANCE_KERNEL.md §3.1` |
| Coherence guard | `shared/coherence.py` (4,530 bytes) | `GOVERNANCE_KERNEL.md §3.2` |
| IO contract (atomic writes) | `app/utils/io_contract.py` (5,047 bytes) | `GOVERNANCE_KERNEL.md §3.4` |

### Invariant Tests

| Invariant | Test file(s) |
|---|---|
| No ungoverned mutation | `test_governance_unification.py`, `test_operator_write_denial.py`, `test_casts_closure.py` |
| Fail-closed default | `test_authority_rules.py`, `test_coherence_guard.py`, `test_capture_adversarial.py` |
| Deterministic transformation | `test_constraints.py`, `test_enforcement.py`, `test_clock_basic.py` |
| Append-only observability | `test_operator_write_intake.py`, `test_operator_write_workflow.py`, `test_operator_transaction_snapshot.py` |
| Declared mutation contract | `test_operator_write_contract.py`, `test_operator_write_intent_contract.py` |
| Memory read-only | `tests/memory/test_reader.py` |

---

## 3. Append-Only Ledgers

**[IMPLEMENTED]**

| Ledger | Path | Write authority |
|---|---|---|
| Transition events | `data/state/transition_gate_events.jsonl` | `transition_gate.emit_transition_event()` |
| Operator runs | `data/operator/runs/operator_runs.jsonl` | `OperatorRuntime._append_ledger_entry()` |
| Intake records | `data/intake/intake.jsonl` | `OperatorRuntime._tool_intake_log_append()` |
| Artifact registry v2 | `data/state/artifact_registry_v2.jsonl` | Registry projection from transition events |
| Capture log | `data/capture/capture_log.jsonl` | `app/hq/capture/capture.py` |
| Promotion log | `data/capture/promotion_log.jsonl` | `app/hq/capture/promote.py` |
| Routing log | `data/capture/routing_log.jsonl` | `app/hq/capture/router.py` |
| Module artifacts | `data/state/module_artifacts.jsonl` | Module formalization pipeline |
| Activation events | `data/state/activation_events.jsonl` | `app/governor/activation_governor.py` (deprecated local write) |
| Provider events | `data/state/provider_events.jsonl` | Provider integration layer |
| Release registry | `data/state/release_registry.jsonl` | Release orchestration |
| Inference cache | `data/state/inference_cache_registry.jsonl` | Inference cache governance |
| Retention contacts | `data/state/contacts.jsonl` | `app/retention/jsonl_store.py` |
| Retention events | `data/state/events.jsonl` | `app/retention/jsonl_store.py` |
| Retention transitions | `data/state/transitions.jsonl` | `app/retention/jsonl_store.py` |
| Content dispatch | `data/state/content_dispatch.jsonl` | `app/retention/jsonl_store.py` |
| Witness daily | `data/state/witness/witness_daily.jsonl` | `signal_agent/health/daily_check.py` |

---

## 4. Retention Subsystem

**[IMPLEMENTED]**

| Component | Path | Evidence |
|---|---|---|
| JSONL store (hash-chained) | `app/retention/jsonl_store.py` (5,901 bytes) | `append_record`, `iter_jsonl`, `compute_record_hash` |
| Identity helpers | `app/retention/identity.py` (2,602 bytes) | Deterministic SHA-256 IDs |
| Contact models | `app/retention/models.py` (5,446 bytes) | `build_contact_seed_event`, `build_contact_snapshot` |
| Transition evaluator | `app/retention/transitions.py` (5,532 bytes) | `evaluate_transition` with state machine rules |
| Dispatch planner | `app/retention/dispatch.py` | Dispatch rule evaluation |
| Dispatch gate | `app/retention/dispatch_gate.py` | Readiness evaluation |
| Send queue | `app/retention/send_queue.py` | Queue projection |
| Sender contract | `app/retention/sender_contract.py` | Local-only send preview |
| Outbound authorization | `app/retention/outbound_authorization.py` | Operator authorization gate |
| Execution dry run | `app/retention/execution_dry_run.py` | Stage 7 simulation |
| CLI (856 lines, 20+ commands) | `app/retention/cli.py` | Full argparse CLI |
| Appointments subsystem | `app/retention/appointments/` | Governed lifecycle |
| Substack CSV ingestion | `app/retention/substack_csv.py` | Source batch import |

**Local-only boundary (verified)**: `network_allowed: false`, `external_actions_allowed: false`

---

## 5. HQ Pipeline

**[IMPLEMENTED]**

| Component | Path | Size |
|---|---|---|
| Capture | `app/hq/capture/capture.py` | 14,441 bytes |
| Promotion | `app/hq/capture/promote.py` | 23,655 bytes |
| Routing | `app/hq/capture/router.py` | 20,255 bytes |
| Decay | `app/hq/capture/decay.py` | 8,090 bytes |
| Instability | `app/hq/capture/instability.py` | 10,758 bytes |
| Stress | `app/hq/capture/stress.py` | 10,733 bytes |
| Curation | `app/hq/curation/curate.py` | 14,008 bytes |
| Curation rules | `app/hq/curation/rules.yaml` | 760 bytes |
| Analytics | `app/hq/analytics.py` | 887 bytes |
| Exporter | `app/hq/exporter.py` | 1,136 bytes |

---

## 6. Observability and Health

**[IMPLEMENTED]**

| Component | Path | Evidence |
|---|---|---|
| Daily witness check (925 lines) | `signal_agent/health/daily_check.py` | 5-stage structured report with ledger validation, git state, invariant checking, runtime health |
| System health report | `shared/health.py` | Reconciliation, coherence failures, blocked transitions, unprocessed events |
| Reconciliation | `shared/reconcile.py` | Artifact state vs filesystem consistency |
| Coherence kernel | `app/audit/coherence_kernel.py` (324 lines) | Risk signals (Φ₁–Φ₅), hysteresis-based regime classification (STABLE → PRESSURE → UNSTABLE → FAILURE), coherence score |
| Runtime audit evidence | `app/audit/runtime_audit_evidence.py` | Runtime boundary evidence collection |
| Runtime audit reports | `app/audit/runtime_audit_reports.py` | Runtime audit report generation |
| Task contract evaluator | `app/audit/task_contract.py` | Contract compliance evaluation |

---

## 7. HQ Dashboard

**[EMERGING]** — code exists but is not part of canonical governance pipeline

| Component | Path | Notes |
|---|---|---|
| FastAPI dashboard | `app/hq/dashboard/hq_dashboard.py` (120 lines) | Uses FastAPI + subprocess; social offload oriented |
| Dashboard HTML | `app/hq/dashboard/index.html` | Static HTML frontend |
| Dashboard requirements | `app/hq/dashboard/requirements.txt` | `fastapi` dependency |

> This dashboard is not governed by the transition gate and uses `subprocess.Popen` for execution. It is experimental, not canonical.

---

## 8. Spine Observability

**[EMERGING]** — model code exists but store and CLI are not yet implemented

| Component | Path | Status |
|---|---|---|
| Spine models | `app/spine_observability/models.py` (313 lines) | Untracked; has `build_spine_record`, `build_platform_account_record`, `build_metric_snapshot_record`, full validation, `external_action_allowed: false` enforcement |
| Module init | `app/spine_observability/__init__.py` | Untracked |
| Spine router config | `config/spine_router.yaml` (6 spine definitions) | Tracked; routing keywords and domains |
| Convergence plan | `docs/operator/spine_laviathon_convergence_stage1_plan.md` | Untracked |
| Store, CLI, tests | Not yet created | Planned in convergence plan |

---

## 9. Laviathon / Leviathan

**[IMPLEMENTED]** (canonical namespace) + **[EMERGING]** (evaluator persona)

| Component | Path | Status |
|---|---|---|
| Canonical namespace | `signal_agent/laviathon/` | **Implemented** — daemon, CLI |
| Drift audit CLI | `signal_agent/laviathon/cli/drift_audit_cli` | **Implemented** — console script `drift-audit` |
| Legacy compatibility | `signal_agent/leviathan/` | **Implemented** — backward-compatible import path |
| Legacy static site | `laviathon/` | **Legacy** — marked non-canonical in `LEGACY.md` |
| Legacy site staging | `site_laviathon/` | **Legacy** — marked non-canonical |
| Laviathon evaluator persona | Not yet implemented | **Emerging** — defined in convergence plan |

---

## 10. Memory and Context

**[IMPLEMENTED]**

| Component | Path | Evidence |
|---|---|---|
| Memory reader (read-only enforced) | `signal_agent/memory/reader.py` | Static test verifies zero write-mode file ops |
| Context assembly | `signal_agent/memory/context_assembly.py` | Policy-filtered, frozen context bundles |
| Context policy | `signal_agent/memory/context_policy.py` | YAML-driven allow/deny per memory type |
| Memory types | `signal_agent/memory/types.py` | `@dataclass(frozen=True)` on `ContextBundle` |

---

## 11. Governance Design Specs

**[FUTURE]** — conceptual only, no runtime enforcement

| Spec | Path |
|---|---|
| Deterministic Constraint Engine | `governance/DETERMINISTIC_CONSTRAINT_ENGINE.md` |
| Deterministic Constraint Kernel | `governance/DETERMINISTIC_CONSTRAINT_KERNEL.md` |
| Programmable Policy Layer v1.2 | `governance/PROGRAMMABLE_POLICY_LAYER_v1_2.md` |
| AI Execution Containment | `governance/AI_EXECUTION_CONTAINMENT_LAYER_v1.md` |
| Domain Constraint Packs | `governance/DOMAIN_CONSTRAINT_PACKS.md` |

> Per `GOVERNANCE_KERNEL.md §7`: these specs are conceptual. Implementation requires explicit phase transition to EXECUTION or EXPANSION.

---

## 12. Publications and Public Proof

**[IMPLEMENTED]**

| Component | Path |
|---|---|
| Deterministic governance bundle | `docs/publications/deterministic_governance/` |
| Implementation evidence | `docs/publications/deterministic_governance/implementation_evidence.md` |
| Failure modes | `docs/publications/deterministic_governance/failure_modes.md` |
| Claim audit table | `docs/publications/deterministic_governance/claim_audit_table.md` |
| Repo surface inventory | `docs/publications/deterministic_governance/repo_surface_inventory.md` |
| Controlled failure demo | `app/demo/controlled_failure/` |

---

## 13. Demo Surfaces

**[IMPLEMENTED]**

| Demo | Path | Evidence |
|---|---|---|
| Controlled failure demo | `app/demo/controlled_failure/` | `docs/demo/controlled_failure_demo_script.md` |

---

## 14. Legacy and Experimental

| Surface | Path | Classification |
|---|---|---|
| `leviathan/` (top-level) | Legacy | Non-canonical |
| `laviathon/` (top-level) | Legacy | Non-canonical per `LEGACY.md` |
| `site_laviathon/` | Legacy | Non-canonical per `LEGACY.md` |
| `experiments/` | Experimental | Per `CANONICAL_DIRS.txt`: "explicitly non-canonical" |
| `.tmp/`, `repro_out/`, `tmp_route_debug/` | Scratch | Runtime output; do not commit |
