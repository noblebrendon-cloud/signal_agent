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

**[EMERGING]** — model code exists, store and CLI do not

### Existing Code

| File | Status | Content |
|---|---|---|
| `app/spine_observability/__init__.py` | Untracked | Module docstring |
| `app/spine_observability/models.py` (313 lines) | Untracked | Full implementation: `build_spine_record`, `build_platform_account_record`, `build_metric_snapshot_record` |

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

## 5. Planned Ledger Files

**[EMERGING]** — defined in convergence plan, not yet created

| Ledger | Path | Record type |
|---|---|---|
| Spine definitions | `data/state/spines.jsonl` | `spine` |
| Platform accounts | `data/state/spine_platforms.jsonl` | `platform_account` |
| Metric snapshots | `data/state/spine_metrics.jsonl` | `metric_snapshot` |
| Laviathon observations | `data/state/laviathon_observations.jsonl` | `laviathon_observation` |

---

## 6. Planned CLI Commands

**[EMERGING]** — defined in convergence plan, not yet implemented

```
python -m app.spine_observability.cli add-spine --name <name> --description <desc>
python -m app.spine_observability.cli list-spines
python -m app.spine_observability.cli add-platform --spine-name <name> --platform <platform> --label <label> --content-lane <lane>
python -m app.spine_observability.cli add-metric --platform-account-id <id> --captured-at <ts> --window-start <ts> --window-end <ts> --metrics <json>
python -m app.spine_observability.cli spine-summary --format text|json
python -m app.spine_observability.cli under-tracked --days 7
```

---

## 7. Relationship to Retention Subsystem

**[IMPLEMENTED]** — retention is the proven pattern; spine observability reuses it

| Retention pattern | Spine observability usage |
|---|---|
| `app/retention/jsonl_store.py` → `append_record` | Will be used for all spine ledger writes |
| `app/retention/identity.py` → deterministic IDs | Already used in `spine_observability/models.py` |
| `app/retention/cli.py` → argparse pattern | Will be replicated for spine CLI |
| Hash-chained records (`prev_hash` → `record_hash`) | Will use same chain via `append_record` |
| Test isolation via `SIGNAL_AGENT_ROOT` | Will follow same monkeypatch fixture pattern |

---

## 8. Non-Goals for Stage 1

- No API integrations
- No automated metric collection
- No scraping or polling
- No external posting or scheduling
- No dashboard UI
- No network calls of any kind
- No modifications to existing retention or governance code
