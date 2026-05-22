# Reflective Pressure Spine Guide

## Purpose

The Reflective Pressure Spine is a local internal recognition engine for captured social and content inputs. It records an input, classifies the pressure inside it, generates a reflective draft, records manual response signals later, and summarizes what the system is learning.

Core doctrine:

```text
Detect pressure -> preserve meaningful tension -> articulate clearly -> observe response -> refine the spine.
```

## What It Is Not

- Not a generic content generator.
- Not a social media assistant.
- Not a virality optimizer.
- Not an influencer tool.
- Not an external posting system.
- Not a platform API collector.
- Not a SaaS surface.

## Local-First Boundary

The module is intentionally local-first because the system needs observable, append-only pressure recognition before it can safely admit automation. All state is stored under local `data/state/` ledgers. Metrics are entered manually. No command connects to Facebook, Instagram, Threads, TikTok, X, LinkedIn, Substack, YouTube, email providers, or any other external platform.

## No Auto-Posting

Generated drafts are drafts only. The module never posts, sends, schedules, scrapes, or marks anything as externally executed. Human approval is explicit and remains outside the v0 command surface. Every record keeps:

- `external_action_allowed: false`
- `irreversible_action_allowed: false`

## Pressure Ontology

The v0 pressure taxonomy includes:

- `recognition_deprivation`
- `role_fatigue`
- `aspiration_reality_gap`
- `moral_contradiction_exposure`
- `belonging_exclusion_tension`
- `public_private_split`
- `sacred_profane_conflict`
- `humor_as_shield`
- `tenderness_under_threat`
- `aftermath_memory`
- `ego_disguised_as_righteousness`
- `shallow_certainty`
- `spiritual_reductionism`
- `authority_confusion`
- `grievance_loop`
- `peace_vs_escalation`
- `unknown`

The v0 classifier is deterministic and keyword-based. It is not trying to be final intelligence. It is a first working pressure spine that can be reconciled, tested, and safely upgraded later.

## Ledgers

The module writes append-only, hash-chained JSONL through the existing retention JSONL store helper.

- `data/state/reflective_pressure_inputs.jsonl`
- `data/state/reflective_pressure_classifications.jsonl`
- `data/state/reflective_pressure_drafts.jsonl`
- `data/state/reflective_pressure_observations.jsonl`
- `data/state/reflective_pressure_events.jsonl`

Ledgers may be absent when no data has been recorded. Malformed ledgers fail reconciliation.

## CLI Commands

Run from the repo root.

```powershell
python -m app.reflective_pressure.cli rp-add-input --source-platform facebook_group --source-type comment --raw-text "People keep turning every deeper discussion back into slogans instead of dealing with the actual pressure."
```

```powershell
python -m app.reflective_pressure.cli rp-classify --input-id <input_id>
```

```powershell
python -m app.reflective_pressure.cli rp-generate-draft --input-id <input_id> --classification-id <classification_id> --output-type reply --target-platform facebook_group
```

```powershell
python -m app.reflective_pressure.cli rp-record-observation --input-id <input_id> --draft-id <draft_id> --views 1000 --reactions 25 --comments 18 --shares 4 --saves 0 --profile-clicks 3 --recognition-events 6 --constructive-reply-ratio 0.7 --self-insertion-density 0.5 --delayed-recirculation 0 --contradiction-heat 3
```

```powershell
python -m app.reflective_pressure.cli rp-summary --by pressure_type
```

```powershell
python -m app.reflective_pressure.cli rp-reconcile
```

## Example Workflow

1. Add a Facebook group comment screenshot as raw text:

```powershell
python -m app.reflective_pressure.cli rp-add-input --source-platform facebook_group --source-type comment --raw-text "People keep turning every deeper discussion back into slogans instead of dealing with the actual pressure." --group-or-channel "local discussion group" --tags "slogans,pressure"
```

2. Copy the returned `input_id`, then classify it:

```powershell
python -m app.reflective_pressure.cli rp-classify --input-id <input_id>
```

3. Copy the returned `classification_id`, then generate a reply draft:

```powershell
python -m app.reflective_pressure.cli rp-generate-draft --input-id <input_id> --classification-id <classification_id> --output-type reply --target-platform facebook_group
```

4. Review the draft as a human. If you manually post anything outside the system, that action is not performed by this module.

5. Come back later and record manual observation metrics:

```powershell
python -m app.reflective_pressure.cli rp-record-observation --input-id <input_id> --draft-id <draft_id> --views 1000 --reactions 25 --comments 18 --shares 4 --saves 0 --profile-clicks 3 --recognition-events 6 --constructive-reply-ratio 0.7 --self-insertion-density 0.5 --delayed-recirculation 0 --contradiction-heat 3
```

6. Run summaries:

```powershell
python -m app.reflective_pressure.cli rp-summary --by pressure_type
python -m app.reflective_pressure.cli rp-summary --by spine
python -m app.reflective_pressure.cli rp-summary --by recognition
```

7. Run reconciliation:

```powershell
python -m app.reflective_pressure.cli rp-reconcile
```

## Validation Boundaries

- Invalid taxonomy values fail closed.
- Empty `raw_text` is allowed only when `media_refs` exists through the model layer.
- Classification, draft, and observation references must resolve.
- Numeric observation metrics must be non-negative.
- Scores must be integers from 0 to 5.
- `external_action_allowed` must remain `false`.
- `irreversible_action_allowed` must remain `false`.
- Malformed JSONL fails reconciliation.

## Verification

```powershell
python -m pytest tests/test_reflective_pressure_models_store.py tests/test_reflective_pressure_flow.py tests/test_reflective_pressure_cli.py -q
```

## v0.2 Corpus Seeding And Human Correction

v0.2 adds the corpus-building loop:

```text
Capture real pressure -> classify -> review -> correct -> preserve golden examples -> export reusable prompt/eval material.
```

Corrections are append-only because the original heuristic classification is evidence. If a human improves it, the system records that correction as a new fact instead of rewriting the old one. This makes classifier drift visible: the module can later show where v0 rules keep missing the human reading.

Golden examples matter because they turn lived pressure recognition into reusable training and evaluation material. A golden example ties together the input, classification, optional correction, optional draft, and operator notes about pattern, voice, and risk.

Prompt packs are local markdown exports from approved golden examples. They are not published, posted, sent, or uploaded. They are intended as future LLM prompt and eval material.

### v0.2 Ledgers

- `data/state/reflective_pressure_corrections.jsonl`
- `data/state/reflective_pressure_golden_examples.jsonl`

These are append-only and hash-chained through the same JSONL store.

### v0.2 Commands

```powershell
python -m app.reflective_pressure.cli rp-import-inputs --path data/inputs/reflective_seed.jsonl --classify
```

```powershell
python -m app.reflective_pressure.cli rp-review --input-id <input_id>
```

```powershell
python -m app.reflective_pressure.cli rp-correct-classification --classification-id <classification_id> --input-id <input_id> --pressure-type peace_vs_escalation --correction-reason "Human read sees escalation pressure."
```

```powershell
python -m app.reflective_pressure.cli rp-mark-golden --input-id <input_id> --classification-id <classification_id> --correction-id <correction_id> --draft-id <draft_id> --pressure-type peace_vs_escalation --title "Accusation pressure without escalation" --why-it-matters "Preserves tension without amplifying conflict." --reusable-pattern "Name the pressure, then refuse the slogan." --approved-for-prompt-export true
```

```powershell
python -m app.reflective_pressure.cli rp-export-prompt-pack --path data/outputs/reflective_pressure/prompt_pack.md --approved-only true
```

Additional summaries:

```powershell
python -m app.reflective_pressure.cli rp-summary --by corrections
python -m app.reflective_pressure.cli rp-summary --by golden
python -m app.reflective_pressure.cli rp-summary --by drift
python -m app.reflective_pressure.cli rp-summary --by prompt_export
python -m app.reflective_pressure.cli rp-summary --by next_actions
```

### Seed JSONL Format

Each line is one JSON object:

```json
{"source_platform":"facebook_group","source_type":"comment","raw_text":"People keep turning every deeper discussion back into slogans.","tags":["slogans","pressure"]}
```

Supported fields:

- `source_platform`
- `source_type`
- `raw_text`
- `source_context`
- `group_or_channel`
- `intended_spine`
- `tags`
- `notes`

### Facebook Group Manual Workflow

1. Create a local seed JSONL file with 10 manually copied posts or comments.
2. Import with classification:

```powershell
python -m app.reflective_pressure.cli rp-import-inputs --path data/inputs/facebook_group_seed.jsonl --classify
```

3. Review one input:

```powershell
python -m app.reflective_pressure.cli rp-review --input-id <input_id>
```

4. Correct the classification if the heuristic missed the pressure.
5. Generate or inspect a draft. Manual posting, if any, happens outside this module.
6. Mark the strongest corrected example as golden.
7. Export the prompt pack locally.
8. Run summaries, especially `drift` and `next_actions`.
9. Run reconciliation.

No step connects to Facebook, reads Facebook automatically, or posts back to Facebook.
