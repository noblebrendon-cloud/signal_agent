# Meme Offload Module (CONTENT_MEME_OFFLOAD v0.3) — INTERNAL TOOLING ONLY

The **Meme Offload** module generates governed meme artifacts from source text, enforced by DOMAIN-scoped constraint packs with deterministic hashing, reprojection, and fail-closed policy evaluation.

> [!CAUTION]
> This is internal tooling. NOT for public exposure.

## Architecture Tier

**Tier**: Domain Agent (Supporting Subsystem)
**Parent**: `app/agents/`
**Action**: `CONTENT_MEME_OFFLOAD`
**Scope**: `DOMAIN`

### Tier 2 — DOMAIN Action

**CONTENT_MEME_OFFLOAD**
- Spec: `meme_spec_v1` (schema identity, NOT semver)
- Governed by DOMAIN pack (`CONTENT_MEME_OFFLOAD_v1.yaml`) or template packs
- Reprojection required — fail-closed
- Deterministic `meme_id` via SHA256
- Optional provider-backed caption expansion (policy-gated, disabled by default)
- SVG render mode (v0.3 — CI-safe, deterministic)
- Artifact registry auto-ingest (v0.3)

```
app/agents/meme_offload/
├── __init__.py
├── schema.py              # MemeSpecV1 contract, deterministic meme_id
├── meme_offload.py        # Offload engine
├── artifact_registry.py   # Auto-ingest to JSONL registry (v0.3)
└── render/
    ├── __init__.py
    ├── render_memes.py    # Pillow-based PNG renderer
    └── render_svg.py      # Pure-Python SVG renderer (v0.3)

app/hq/
└── social_signal_pipeline.py  # Internal signal queue (v0.3)

constraints/packs/domain/content_meme/
├── CONTENT_MEME_OFFLOAD_v1.yaml   # Base pack
├── reddit_deadpan_v1.yaml         # Template (v0.3)
├── linkedin_clean_v1.yaml         # Template (v0.3)
└── youtube_thumbnail_v1.yaml      # Template (v0.3)
```

## Data Flow

```
Source Text
  │
  ▼
meme_offload_generate(render_mode="png"|"svg")
  │
  ├─ 1. Emit MEME_OFFLOAD_START (with pack provenance)
  ├─ 2. Load constraint pack YAML
  ├─ 3. Extract candidate frames (deterministic order)
  ├─ 4. Build MemeSpecV1 objects (up to LIMIT)
  ├─ 5. [Optional] Provider expansion (policy-gated)
  ├─ 6. meme_id recomputed from FINAL text (v0.3)
  ├─ 7. reproject_checkpoint_meme() per spec — fail-closed
  ├─ 8. Write spec JSON
  ├─ 9. Render (PNG or SVG based on render_mode)
  ├─ 9b. Artifact registry auto-ingest (v0.3)
  └─ 10. Emit MEME_OFFLOAD_DONE
```

## Template Packs (v0.3)

| Pack | Platform | Format | Canvas | Limits |
|------|----------|--------|--------|--------|
| `reddit_deadpan_v1` | Reddit | two_panel | 1080×1080, #0d0d0d | 80 char panels |
| `linkedin_clean_v1` | LinkedIn | infographic_list | 1200×1200, #f5f5f5 | 60 char bullets, max 3 |
| `youtube_thumbnail_v1` | YouTube | two_panel | 1280×720, #ff0000 | 6 words top, 40 char |

## Constraint Pack Rules (Base)

| # | Rule ID | Type | Purpose |
|---|---------|------|---------|
| 1 | `MEME_ALLOW_OFFLOAD` | ALLOW | Permit action |
| 2 | `MEME_LIMIT_MAX_OUTPUTS` | LIMIT | Cap at 5 |
| 3 | `MEME_DENY_NAMED_PERSON` | DENY | Block named individuals |
| 4 | `MEME_DENY_DISALLOWED_TERMS` | DENY | Block violence/hate |
| 5 | `MEME_DENY_PANEL_LENGTH` | DENY | Block >120 chars |
| 6 | `MEME_ALLOW_PROVIDER_EXPANSION` | ALLOW | Gate LLM expansion (disabled) |

## Artifact Registry (v0.3)

After successful render:
1. SHA256 of output file computed
2. Canonical rename: `<stem>__<hash12>.<ext>`
3. Entry appended to `data/meme_offload/artifact_registry.jsonl`

```json
{"artifact_type":"meme_render","artifact_id":"abc123def456","path":"...","pack_id":"...","pack_hash":"sha256:...","created_at":"UTC"}
```

Idempotent, file-locked, no duplicates.

## Social Signal Queue (v0.3) — Internal Only

```
data/social_queue/<platform>/<timestamp>_<meme_id>.json
```

Platforms: `reddit`, `linkedin`, `youtube`
No network calls. Queue payloads only.

## SVG Renderer (v0.3)

- Pure Python — no Pillow, no external fonts
- CI-safe: identical output on any platform
- Fixed font stack: `monospace`
- Formats: `two_panel`, `infographic_list`

## Determinism Guarantees

*   **spec_version**: `"meme_spec_v1"` (enforced in `__post_init__`)
*   **render_mode**: validated to `"png"` or `"svg"`
*   **meme_id**: `sha256(pack_hash + frame_id + FINAL_text + format)[:12]`
*   **Frame ordering**: Input order preserved
*   **Pack hash**: `stable_pack_hash()` — deterministic SHA256
*   **SVG rendering**: No system fonts, no network
*   **Artifact registry**: Idempotent, sorted-key JSON

## Kernel Integration

*   Reprojection FAIL → Φ₁ increment
*   Provider expansion → Φ₃/Φ₄ via resilience
*   Rule-only mode → kernel STABLE, no drift
