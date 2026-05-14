# HQ Observability Layer

**Status**: evidence-mapped from live repo
**Classification**: each section is marked **[IMPLEMENTED]**, **[EMERGING]**, or **[FUTURE]**

---

## 1. Overview

The HQ (Headquarters) layer is the content pipeline that captures raw artifacts, promotes them through quality gates, routes them to publication lanes, and tracks observability at each stage.

Pipeline flow:

```
capture → promote → route → [curate → transform → compile → stage → emit → audit]
```

The first three stages are fully implemented with ledger evidence. The remaining stages have partial implementation or are future-facing.

---

## 2. Capture Layer

**[IMPLEMENTED]**

| Component | Path | Size | Role |
|---|---|---|---|
| Capture engine | `app/hq/capture/capture.py` | 14,441 bytes | Ingests raw artifacts, classifies content, appends to capture log |
| Decay evaluator | `app/hq/capture/decay.py` | 8,090 bytes | Evaluates content freshness and relevance decay |
| Instability detector | `app/hq/capture/instability.py` | 10,758 bytes | Detects instability patterns in capture behavior |
| Stress evaluator | `app/hq/capture/stress.py` | 10,733 bytes | Evaluates pipeline stress conditions |

### Capture Ledger

| Ledger | Path | Write authority |
|---|---|---|
| `capture_log.jsonl` | `data/capture/capture_log.jsonl` | `app/hq/capture/capture.py` |

### Tests

| Test | Size | Coverage |
|---|---|---|
| `test_capture_layer.py` | 15,174 bytes | Core capture behavior |
| `test_capture_adversarial.py` | 7,863 bytes | Adversarial input rejection |
| `test_capture_falsification.py` | 7,457 bytes | Falsification attempt detection |

---

## 3. Promotion Layer

**[IMPLEMENTED]**

| Component | Path | Size | Role |
|---|---|---|---|
| Promotion engine | `app/hq/capture/promote.py` | 23,655 bytes | Evaluates promotion criteria, advances artifacts through quality gates |

### Promotion Ledger

| Ledger | Path | Write authority |
|---|---|---|
| `promotion_log.jsonl` | `data/capture/promotion_log.jsonl` | `app/hq/capture/promote.py` |

### Operator Reporting

| Report | Path | Status |
|---|---|---|
| Capture routing status | `signal_agent/operator/capture_routing_status.py` (19,133 bytes) | **[IMPLEMENTED]** — operator-facing pipeline view |
| Routing lineage drilldown | `signal_agent/operator/routing_lineage_drilldown.py` (27,103 bytes) | **[IMPLEMENTED]** — per-artifact lineage tracking |
| Routing queue backlog | `signal_agent/operator/routing_queue_backlog.py` (23,745 bytes) | **[IMPLEMENTED]** — queue depth and staleness |

---

## 4. Routing Layer

**[IMPLEMENTED]**

| Component | Path | Size | Role |
|---|---|---|---|
| Content router | `app/hq/capture/router.py` | 20,255 bytes | Routes promoted artifacts to publication lanes |
| Spine router config | `config/spine_router.yaml` | 881 bytes | Keyword and domain-based spine classification |

### Routing Ledger

| Ledger | Path | Write authority |
|---|---|---|
| `routing_log.jsonl` | `data/capture/routing_log.jsonl` | `app/hq/capture/router.py` |

### Routing Status Tests

| Test | Size |
|---|---|
| `test_operator_capture_routing_status.py` | 5,287 bytes |
| `test_operator_routing_lineage_drilldown.py` | 10,337 bytes |
| `test_operator_routing_queue_backlog.py` | 6,600 bytes |

---

## 5. Curation Layer

**[IMPLEMENTED]**

| Component | Path | Size | Role |
|---|---|---|---|
| Curation engine | `app/hq/curation/curate.py` | 14,008 bytes | Applies curation rules to routed content |
| Curation rules | `app/hq/curation/rules.yaml` | 760 bytes | Declarative curation rule definitions |
| Curation CLI commands | `app/hq/curation/brn_cmds.py` | 438 bytes | CLI command surface |

### Tests

| Test | Size |
|---|---|
| `test_curate_publication_gate.py` | 15,056 bytes |
| `test_content_lineage_view.py` | 43,595 bytes |

---

## 6. Publication Pipeline

**[IMPLEMENTED]** — governed publication with operator approval gates

| Component | Evidence | Status |
|---|---|---|
| Publication pipeline end-to-end | `test_publication_pipeline_end_to_end.py` (7,137 bytes) | **[IMPLEMENTED]** |
| Release orchestrator | `test_release_orchestrator.py` (20,647 bytes) | **[IMPLEMENTED]** |
| Release registry | `data/state/release_registry.jsonl` | **[IMPLEMENTED]** — append-only |

---

## 7. Content Lineage View

**[IMPLEMENTED]** — extensive tracking from capture through publication

| Test | Size | Coverage |
|---|---|---|
| `test_content_lineage_view.py` | 43,595 bytes | Full lineage from capture → promotion → routing → curation → publication |

---

## 8. Analytics and Export

**[EMERGING]** — code exists but limited scope

| Component | Path | Size | Status |
|---|---|---|---|
| Analytics | `app/hq/analytics.py` | 887 bytes | Minimal implementation |
| Exporter | `app/hq/exporter.py` | 1,136 bytes | Basic export capability |
| Token export | `app/hq/token_export.py` | 1,119 bytes | Token-level export |

---

## 9. HQ Dashboard

**[EMERGING]** — exists as experimental surface, not governed

| Component | Path | Notes |
|---|---|---|
| FastAPI app | `app/hq/dashboard/hq_dashboard.py` (120 lines) | Social offload dashboard; uses `subprocess.Popen` |
| HTML frontend | `app/hq/dashboard/index.html` (8,442 bytes) | Static HTML |
| Requirements | `app/hq/dashboard/requirements.txt` | `fastapi` dependency |

### Architectural concerns

- Uses `subprocess.Popen` to execute pipeline commands — not governed by transition gate
- Reads JSONL logs directly — no reconciliation
- Not part of the governed write pipeline
- No test coverage found

> **Classification: [EMERGING].** This dashboard exists as an operational convenience for social offload monitoring. It is not part of the governed pipeline and should not be relied upon for system truth.

---

## 10. Runtime Audit Layer

**[IMPLEMENTED]**

| Component | Path | Size | Role |
|---|---|---|---|
| Runtime audit evidence | `app/audit/runtime_audit_evidence.py` | 11,027 bytes | Collects runtime boundary evidence |
| Runtime audit reports | `app/audit/runtime_audit_reports.py` | 6,544 bytes | Generates runtime audit reports |
| Task contract evaluator | `app/audit/task_contract.py` | 8,634 bytes | Evaluates task contract compliance |
| Coherence kernel | `app/audit/coherence_kernel.py` | 9,449 bytes | Quantitative risk scoring (Φ₁–Φ₅, regime classification) |

### Tests

| Test | Size |
|---|---|
| `test_runtime_audit_evidence.py` | 8,535 bytes |
| `test_runtime_audit_reports.py` | 8,959 bytes |

---

## 11. Inference Cache Governance

**[IMPLEMENTED]**

| Component | Evidence |
|---|---|
| Inference cache registry | `data/state/inference_cache_registry.jsonl` |
| Inference cache audit | `test_inference_cache_audit.py` (25,296 bytes) |
| Inference cache audit compare | `test_inference_cache_audit_compare.py` (17,336 bytes) |
| Inference cache audit export | `test_inference_cache_audit_export.py` (10,204 bytes) |
| Inference cache audit render | `test_inference_cache_audit_render.py` (9,199 bytes) |
| Governed replay | `test_governed_inference_cache_replay.py` (8,836 bytes) |

---

## 12. Observability Summary

| Observability Surface | Status | Evidence quality |
|---|---|---|
| Capture → promotion → routing pipeline | **[IMPLEMENTED]** | 3 append-only ledgers, 6+ test files, operator reporting tools |
| Curation → publication | **[IMPLEMENTED]** | Curation rules, end-to-end tests, lineage tracking |
| Runtime audit | **[IMPLEMENTED]** | Evidence collection, reports, coherence kernel |
| Inference cache | **[IMPLEMENTED]** | Registry, audit, compare, export, replay |
| Daily witness | **[IMPLEMENTED]** | 5-stage structured check, append-only witness ledger |
| System health | **[IMPLEMENTED]** | Reconciliation, coherence failures, blocked transitions |
| HQ dashboard | **[EMERGING]** | FastAPI UI exists but ungoverned |
| Spine observability | **[EMERGING]** | Models exist; store and CLI not yet implemented |
| Cross-spine audience tracking | **[FUTURE]** | Planned in convergence plan |

---

## 13. Non-Goals

- This document does not describe future API integrations
- This document does not describe external notification systems
- This document does not describe autonomous metric collection
- The HQ dashboard section describes current state, not recommended architecture
