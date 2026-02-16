# Meme Offload Module (CONTENT_MEME_OFFLOAD v0.2)

The **Meme Offload** module generates governed meme artifacts from source text, enforced by DOMAIN-scoped constraint packs with deterministic hashing, reprojection, and fail-closed policy evaluation.

## Architecture Tier

**Tier**: Domain Agent (Supporting Subsystem)
**Parent**: `app/agents/`
**Action**: `CONTENT_MEME_OFFLOAD`
**Scope**: `DOMAIN`

### Tier 2 — DOMAIN Action

**CONTENT_MEME_OFFLOAD**
- Spec: `meme_spec_v1` (schema identity, NOT semver)
- Governed by DOMAIN pack (`CONTENT_MEME_OFFLOAD_v1.yaml`)
- Reprojection required — fail-closed
- Deterministic `meme_id` via SHA256
- Optional provider-backed caption expansion (policy-gated, disabled by default)

```
app/agents/meme_offload/
├── __init__.py
├── schema.py              # MemeSpecV1 contract, deterministic meme_id
├── meme_offload.py        # Offload engine (10-step pipeline)
└── render/
    ├── __init__.py
    └── render_memes.py    # Pillow-based PNG renderer

constraints/packs/domain/content_meme/
└── CONTENT_MEME_OFFLOAD_v1.yaml   # ALLOW + LIMIT + DENY + expansion gate

data/meme_offload/
├── specs/    # JSON spec output
└── renders/  # PNG render output

app/cli/
└── brn_cmds_meme.py   # CLI entry point
```

## Data Flow

```
Source Text
  │
  ▼
meme_offload_generate()
  │
  ├─ 1. Emit MEME_OFFLOAD_START (with pack provenance)
  ├─ 2. Load constraint pack YAML
  ├─ 3. Extract candidate frames (deterministic order)
  ├─ 4. Build MemeSpecV1 objects (up to LIMIT)
  ├─ 5. [Optional] Provider expansion (if policy-gated ALLOW)
  │      ├─ call_with_resilience(max_tokens=80, temp≤0.7)
  │      ├─ Reproject expanded text
  │      └─ FAIL → record_constraint_violation(), abort
  ├─ 6. reproject_checkpoint_meme() per spec
  │      ├─ PASS → continue
  │      └─ FAIL → kernel.record_constraint_violation(), raise ConstraintViolation
  ├─ 7. Write spec JSON to data/meme_offload/specs/
  ├─ 8. Render PNG via Pillow to data/meme_offload/renders/
  ├─ 9. Emit MEME_RENDER_DONE per output
  └─ 10. Emit MEME_OFFLOAD_DONE (with pack provenance)
```

## Constraint Pack Rules

| # | Rule ID | Type | Purpose |
|---|---------|------|---------|
| 1 | `MEME_ALLOW_OFFLOAD` | ALLOW | Permit action in content domain |
| 2 | `MEME_LIMIT_MAX_OUTPUTS` | LIMIT | Cap at 5 memes per invocation |
| 3 | `MEME_DENY_NAMED_PERSON` | DENY | Block named individuals |
| 4 | `MEME_DENY_DISALLOWED_TERMS` | DENY | Block violence/hate terms |
| 5 | `MEME_DENY_PANEL_LENGTH` | DENY | Block texts exceeding 120 chars |
| 6 | `MEME_ALLOW_PROVIDER_EXPANSION` | ALLOW | Gate LLM expansion (disabled by default) |

Pack path: `constraints/packs/domain/content_meme/CONTENT_MEME_OFFLOAD_v1.yaml`

## Telemetry Events (JSONL)

All events include pack provenance: `pack_id`, `pack_version`, `pack_hash`, `rule_ids`, `action`.

| Event | Emitted |
|-------|---------|
| `MEME_OFFLOAD_START` | Pipeline entry |
| `MEME_CANDIDATES_EXTRACTED` | After frame extraction |
| `MEME_SPECS_BUILT` | After spec construction |
| `MEME_REPROJECTION_PASS` | Per spec passing reprojection |
| `MEME_REPROJECTION_FAIL` | Per spec failing reprojection |
| `MEME_CAPTION_EXPANDED` | After successful LLM expansion |
| `MEME_CAPTION_EXPANSION_FAILED` | On expansion failure (fail-closed) |
| `MEME_RENDER_DONE` | Per rendered PNG |
| `MEME_OFFLOAD_DONE` | Pipeline exit |

## Determinism Guarantees

*   **spec_version**: `"meme_spec_v1"` (schema identity, NOT semver)
*   **meme_id**: `sha256(pack_hash + frame_id + normalized_text + format)[:12]`
*   **Frame ordering**: Input order preserved (stable)
*   **Pack hash**: `stable_pack_hash()` via `ir.py` — deterministic SHA256
*   **Rendering**: Pillow local-only, no network, deterministic font fallback
*   **No eval()**: All DSL predicates use structured operators

## Provider Expansion (v0.2)

Optional LLM caption expansion is **disabled by default** via:

```yaml
- constraint_id: MEME_ALLOW_PROVIDER_EXPANSION
  predicate: "false"
```

When enabled:
*   Uses `call_with_resilience()` — goes through resilience layer
*   `max_tokens ≤ 80`, `temperature ≤ 0.7`
*   Expanded text is reprojected — all DENY rules enforced
*   FAIL → `record_constraint_violation()` + abort
*   Increments Φ₃/Φ₄ through resilience path

## CLI Usage

```powershell
$env:PYTHONPATH = "e:\signal_agent"
python app/agent.py meme.offload --in <path> --pack CONTENT_MEME_OFFLOAD_v1 --n 5
```

Options:
*   `--in` — Source artifact path or ID (required)
*   `--pack` — Constraint pack name (default: `CONTENT_MEME_OFFLOAD_v1`)
*   `--n` — Max outputs (default: 5, capped by LIMIT rule)
*   `--format` — `two_panel` or `infographic_list`

## Kernel Integration

*   Reprojection FAIL increments **Φ₁** (constraint violations)
*   Provider expansion increments **Φ₃/Φ₄** through resilience path
*   No false signal drift in rule-only mode
*   Regime transitions unaffected in normal operation
*   `SystemHalt` / `LoadShed` paths remain unchanged
