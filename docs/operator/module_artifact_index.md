# Module Artifact Index

**Generated**: 2026-04-30  
**Scope**: Final documentation refresh of the module artifact registry  
**Source files**:
- `data/state/module_artifacts.jsonl`
- `docs/operator/blocked_module_remediation_queue.md`

## module_count_summary

| Metric | Count |
|---|---:|
| Total module artifact records | 16 |
| `active` | 15 |
| `candidate` | 0 |
| `deprecated` | 1 |
| `merged` | 0 |
| `rejected` | 0 |
| Promotion or registration reviewed modules | 15 |
| Active reviewed modules | 15 |
| Blocked candidate modules | 0 |

| Source | Count |
|---|---:|
| `self_identification_sweep` | 8 |
| `missing_module_domain_sweep` | 3 |
| `runtime_audit_split_phase1` | 1 |
| `letters_of_light_split_plan` | 3 |
| `retention_internal_registration` | 1 |

## modules_by_type

| module_type | Total | Active | Candidate | Deprecated | Modules |
|---|---:|---:|---:|---:|---|
| `governance_module` | 7 | 7 | 0 | 0 | `hq_transition_gate`, `activation_governor`, `runtime_audit`, `coherence_kernel`, `runtime_audit_evidence`, `letters_of_light_diagnostic_loop`, `retention` |
| `content_module` | 3 | 2 | 0 | 1 | `hq_curation`, `letters_of_light_pipeline_core`, `letters_of_light_core` |
| `domain_module` | 2 | 2 | 0 | 0 | `intake_pipeline`, `hq_capture` |
| `utility_module` | 1 | 1 | 0 | 0 | `io_contract` |
| `integration_module` | 2 | 2 | 0 | 0 | `task_contract`, `letters_of_light_merch_bridge` |
| `registry_module` | 1 | 1 | 0 | 0 | `provider_registry` |

## modules_by_readiness

| Readiness bucket | Count | Modules | Basis |
|---|---:|---|---|
| `active_reviewed_modules` | 15 | `hq_transition_gate`, `hq_curation`, `activation_governor`, `runtime_audit`, `io_contract`, `intake_pipeline`, `coherence_kernel`, `task_contract`, `hq_capture`, `provider_registry`, `runtime_audit_evidence`, `letters_of_light_pipeline_core`, `letters_of_light_merch_bridge`, `letters_of_light_diagnostic_loop`, `retention` | Promotion or registration reviews completed and the registry now reflects those active boundaries |
| `no_open_candidate_modules` | 0 | none | No candidate modules remain in the registry |
| `deprecated_historical_records` | 1 | `letters_of_light_core` | Historical umbrella record preserved as superseded by the split successor records |

## active_modules

| module_id | module_type | Active boundary |
|---|---|---|
| `hq_transition_gate` | `governance_module` | Canonical lifecycle governance spine |
| `hq_curation` | `content_module` | Deterministic curation, registry append, and staged artifact publication surface |
| `activation_governor` | `governance_module` | Runtime activation bounds and operator control surface |
| `runtime_audit` | `governance_module` | Report/orchestration facade for preflight, postflight, contract-eval outputs, and CLI dispatch |
| `io_contract` | `utility_module` | Atomic write and governed append utility surface |
| `intake_pipeline` | `domain_module` | Batch file-ingestion and normalized text snapshot surface |
| `coherence_kernel` | `governance_module` | Structural integrity validation kernel |
| `task_contract` | `integration_module` | Canonical shared contract validation authority |
| `hq_capture` | `domain_module` | Capture lifecycle, promotion, routing, decay, and instability surface |
| `provider_registry` | `registry_module` | Deterministic provider profile resolution surface |
| `runtime_audit_evidence` | `governance_module` | Read-only evidence collection surface for runtime audit |
| `letters_of_light_pipeline_core` | `content_module` | Letters-of-Light generation and create-pipeline core surface |
| `letters_of_light_merch_bridge` | `integration_module` | Merch candidate lifecycle and design-asset bridge surface |
| `letters_of_light_diagnostic_loop` | `governance_module` | Scoring, constraints, weekly diagnostic reporting, and governed derivative-output surface |
| `retention` | `governance_module` | Append-only retention ledgers, reconciliation, local dispatch gating, queue projection, sender preview validation, and explicit local authorization surface. See `docs/operator/retention_pre_external_v1_checkpoint.md` and `docs/operator/retention_subsystem_guide.md`. |

Retention operator guide: [Retention Subsystem Guide](retention_subsystem_guide.md)

## candidate_modules

No candidate modules remain.

## deprecated_modules

| module_id | status | Role |
|---|---|---|
| `letters_of_light_core` | `deprecated` | Historical/superseded umbrella record retained for lineage and split-history traceability; replaced by `letters_of_light_pipeline_core`, `letters_of_light_merch_bridge`, and `letters_of_light_diagnostic_loop` |

## subsystem_guides

- Retention checkpoint: `docs/operator/retention_pre_external_v1_checkpoint.md`
- Retention subsystem guide: `docs/operator/retention_subsystem_guide.md`

## known_boundary_conflicts

No active promotion-blocking boundary conflicts remain in the registry.  
Ongoing maintenance boundaries still matter:

1. `runtime_audit` must remain a thin facade over `runtime_audit_reports`, `runtime_audit_evidence`, and `task_contract`.
2. `hq_capture`, `hq_curation`, and `intake_pipeline` must preserve their explicit handoff boundaries.
3. The three active Letters-of-Light split modules must preserve their shared CLI branch ownership and avoid re-forming the deprecated umbrella boundary.
4. `retention` must preserve the distinction between retention ledgers, projection artifacts, preview artifacts, and authorization artifacts while keeping all external sending blocked.

## recommended_next_operator_decisions

1. Treat the promotion queue as closed unless a new module is discovered or an active boundary is materially widened.
2. Preserve `letters_of_light_core` as a deprecated historical/superseded record and do not return it to the live remediation queue.
3. Require focused re-review for any future change that adds new write surfaces, expands public interfaces, or blurs the established split boundaries of the active modules.
4. Keep `retention` registered as one governed module unless a later real sender admission boundary creates a distinct authoritative module surface.
