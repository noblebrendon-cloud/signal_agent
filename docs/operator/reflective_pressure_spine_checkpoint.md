# Reflective Pressure Spine Checkpoint

## Current Scope

Reflective Pressure Spine v0.2 is a local internal recognition spine. It supports:

- Manual input capture.
- Bulk JSONL seed import.
- Deterministic pressure classification.
- Deterministic reflective draft generation.
- Manual observation recording.
- Append-only human corrections.
- Append-only golden examples.
- Local prompt-pack markdown export.
- Deterministic summaries.
- Read-only reconciliation.
- Append-only local ledgers.

It does not connect to external platforms or post content.

## Invariants

- `external_action_allowed` is always `false`.
- `irreversible_action_allowed` is always `false`.
- Raw text can be empty only when media refs exist in the model layer.
- Invalid taxonomy values fail closed.
- Classification records must reference an existing input.
- Draft records must reference an existing input and classification.
- Observation records must reference an existing input and draft.
- Correction records must reference an existing input and target record.
- Golden examples must reference existing input and classification records.
- Optional golden correction and draft references must exist when provided.
- Prompt pack exports must remain under `data/outputs/reflective_pressure/`.
- Numeric observation metrics are non-negative.
- Scored classification fields are integers from 0 to 5.
- Ledgers are append-only and hash-chained through the existing JSONL store.

## Ledgers

- `data/state/reflective_pressure_inputs.jsonl`
- `data/state/reflective_pressure_classifications.jsonl`
- `data/state/reflective_pressure_drafts.jsonl`
- `data/state/reflective_pressure_observations.jsonl`
- `data/state/reflective_pressure_corrections.jsonl`
- `data/state/reflective_pressure_golden_examples.jsonl`
- `data/state/reflective_pressure_events.jsonl`

## Commands

- `rp-add-input`
- `rp-import-inputs`
- `rp-classify`
- `rp-review`
- `rp-generate-draft`
- `rp-correct-classification`
- `rp-mark-golden`
- `rp-record-observation`
- `rp-summary`
- `rp-export-prompt-pack`
- `rp-reconcile`

All commands print JSON to stdout.

## Tests

Targeted tests:

- `tests/test_reflective_pressure_models_store.py`
- `tests/test_reflective_pressure_flow.py`
- `tests/test_reflective_pressure_cli.py`
- `tests/test_reflective_pressure_corpus.py`

Expected verification:

```powershell
python -m pytest tests/test_reflective_pressure_models_store.py tests/test_reflective_pressure_flow.py tests/test_reflective_pressure_cli.py tests/test_reflective_pressure_corpus.py -q
```

## Module Registration

The module remains a `candidate` governed internal spine in `data/state/module_artifacts.jsonl`, because v0.2 is local and test-backed but should not yet be treated as an active external-facing or automation-capable surface.

## Next Safe Expansion

1. Add an explicit human approval ledger for drafts without enabling posting.
2. Add richer non-LLM rules using correction drift as the evidence source.
3. Add optional local model/provider hooks only behind the repo's existing provider abstractions and with network restrictions documented.
4. Add cross-spine reporting with `app/spine_observability` only after both ledgers have reconciliation coverage.
5. Keep all external API ingestion, scraping, posting, scheduling, and irreversible action out of scope until a separate governance admission path exists.
