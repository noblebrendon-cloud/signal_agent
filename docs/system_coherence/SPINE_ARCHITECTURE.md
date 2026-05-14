# Spine Architecture

**Status**: evidence-mapped from live repo
**Classification**: each section is marked **[IMPLEMENTED]**, **[EMERGING]**, or **[FUTURE]**

---

## 1. What Is a Spine?

A spine is a thematic content and audience grouping that organizes platform presence, metric tracking, and content routing around a coherent identity or domain — not around individual social media accounts.

The system tracks audiences and content **by spine**, enabling cross-platform observability and under-tracked detection.

---

## 2. Spine Taxonomy

**[EMERGING]** — defined in convergence plan; initial model code exists

### Content Spines

| Spine | Platforms | Topics |
|---|---|---|
| Governance Spine | LinkedIn, X, Substack, YouTube (AI/system), TikTok (conceptual) | Deterministic governance, AI orchestration, execution integrity, fail-closed systems, diagnostics, infrastructure critique |
| Reflective Spine | Facebook, Threads, Instagram, YouTube (reflection), TikTok (reflective) | Faith, witness, reflection, peace, humor with meaning, scripture, relational trust, human presence |

### Operational Layers

| Layer | Domains |
|---|---|
| Retention Layer | Contacts, replies, subscribers, intake, relationship continuity |
| Commercial Layer | Audits, diagnostics, services, future offers, website conversion paths |

---

## 3. Spine Router

**[IMPLEMENTED]** — config exists but operates in content intake classification, not audience tracking

| Evidence | Path |
|---|---|
| Spine router config | `config/spine_router.yaml` |

Current defined spines in `config/spine_router.yaml`:

```yaml
spines:
  - name: ai_stability_diagnostic
    keywords: [stability, friction, ops, adoption, workflow, automation, client, diagnostic, readiness, scoring]
    domains: [openai.com, anthropic.com, xda-developers.com, arxiv.org]
  - name: social_field_theory
    keywords: [boundary, attractor, coherence, field, escalation, invariants, governance, entropy, topology]
  - name: content_publishing
    keywords: [youtube, newsletter, outline, script, post, substack, linkedin, facebook, social, content]
    domains: [youtube.com, substack.com]
  - name: logistics_ops
    keywords: [warehouse, packing, slip, discrepancy, inventory, receiving, dock, shipping, logistics]
  - name: misc
  - name: wtpu_content
    keywords: [wtpu, grounded, observation, short-form, video, mask, anonymous, united]
```

> **Note:** These spines classify *inbound content* for routing. The audience-facing spine taxonomy (Governance, Reflective, Retention, Commercial) is a separate, higher-level concept defined in the convergence plan. They may converge in a future stage.

---

## 4. Spine Observability Model

**[IMPLEMENTED]** — local Spine Observability Stage 1 is implemented.

This implementation records and summarizes local spine/platform/metric state only. It does not ingest from external platforms, scrape, post, message, call APIs, or integrate with a dashboard.

### Implemented Code

| File | Status | Content |
|---|---|---|
| `app/spine_observability/__init__.py` | Implemented | Module docstring |
| `app/spine_observability/models.py` | Implemented | `build_spine_record`, `build_platform_account_record`, `build_metric_snapshot_record`, deterministic IDs, validation |
| `app/spine_observability/store.py` | Implemented | Append-only local JSONL store for spines, platform accounts, and metric snapshots |
| `app/spine_observability/summary.py` | Implemented | Summary by spine and under-tracked platform detection |
| `app/spine_observability/cli.py` | Implemented | Deterministic JSON CLI output for local Stage 1 commands |
| `tests/test_spine_observability.py` | Implemented | Targeted coverage; commit `6501ba6` result: 11 passed |

### Record Types Defined

| Record | Builder | ID prefix | Fields |
|---|---|---|---|
| `spine` | `build_spine_record` | `spn_` | name, description, created_at, active |
| `platform_account` | `build_platform_account_record` | `spa_` | spine_id, platform, account_label, content_lane, created_at, active |
| `metric_snapshot` | `build_metric_snapshot_record` | `sms_` | platform_account_id, captured_at, metric_window_start/end, metrics, notes, source_type, external_action_allowed |

### Allowed Platforms

```python
ALLOWED_PLATFORMS = (
    "linkedin", "x", "substack", "youtube_ai", "youtube_reflection",
    "tiktok_conceptual", "tiktok_reflective", "facebook", "threads", "instagram",
)
```

### Safety Enforcement (already implemented in models.py)

- `source_type` must be `"manual"` — line 137–138
- `external_action_allowed` must be `False` — line 139–140
- Datetime validation on all timestamp fields
- `metric_window_start` must be before `metric_window_end`
- Platform values validated against `ALLOWED_PLATFORMS`

### Pattern Reuse

| Pattern | Source | Used by spine models |
|---|---|---|
| `sha256_hex` | `app/retention/identity.py` | ✅ Spine, platform, snapshot ID generation |
| `normalize_token` | `app/retention/identity.py` | ✅ Platform name normalization |
| `utc_now_iso` | `app/retention/identity.py` | ✅ Default timestamps |
| `stable_json_dumps` | `app/retention/jsonl_store.py` | ✅ Snapshot ID generation |

---

## 5. Local Ledger Files

**[IMPLEMENTED]** — created on demand under `data/state/` by the local append-only store.

| Ledger | Path | Record type |
|---|---|---|
| Spine definitions | `data/state/spine_observability_spines.jsonl` | `spine` |
| Platform accounts | `data/state/spine_observability_platforms.jsonl` | `platform_account` |
| Metric snapshots | `data/state/spine_observability_metric_snapshots.jsonl` | `metric_snapshot` |
| Laviathon observations | Not implemented in this module | **[FUTURE]** / separate evaluator boundary |

---

## 6. CLI Commands

**[IMPLEMENTED]** — local-only commands in `app/spine_observability/cli.py`.

```
python -m app.spine_observability.cli add-spine --name <name> --description <desc>
python -m app.spine_observability.cli list-spines
python -m app.spine_observability.cli add-platform --spine-name <name> --platform <platform> --account-label <label> --content-lane <lane>
python -m app.spine_observability.cli list-platforms
python -m app.spine_observability.cli add-metric --platform-account-id <id> --captured-at <ts> --metric-window-start <ts> --metric-window-end <ts> --metric KEY=VALUE
python -m app.spine_observability.cli spine-summary --format text|json
python -m app.spine_observability.cli under-tracked --days 7
```

---

## 7. Relationship to Retention Subsystem

**[IMPLEMENTED]** — retention is the proven pattern; spine observability reuses it

| Retention pattern | Spine observability usage |
|---|---|
| `app/retention/jsonl_store.py` → `append_record` | Used for all spine ledger writes |
| `app/retention/identity.py` → deterministic IDs | Used in `spine_observability/models.py` |
| `app/retention/cli.py` → argparse pattern | Reused for `spine_observability/cli.py` |
| Hash-chained records (`prev_hash` → `record_hash`) | Used through `append_record` |
| Test isolation via `SIGNAL_AGENT_ROOT` | Used in `tests/test_spine_observability.py` |

---

## 8. Non-Goals for Stage 1

- No API integrations
- No automated metric collection
- No scraping or polling
- No external posting or scheduling
- No dashboard UI
- No network calls of any kind
- No modifications to existing retention or governance code
