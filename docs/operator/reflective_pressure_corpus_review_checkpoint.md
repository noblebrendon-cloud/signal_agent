# Reflective Pressure Corpus Review Checkpoint

## Purpose

This checkpoint keeps corpus intake human-gated before any Reddit or Facebook seed batch enters the Reflective Pressure Spine.

The current Reddit batch is a review candidate, not an imported corpus. The work here creates operator-facing review artifacts so a human can inspect, label, approve, skip, correct, and later mark golden examples without changing ontology, classifier rules, or source data.

## Files Created

Reddit review workspace:

- `E:\datasets\reddit\derived\review\reddit_high_score_review_001_table.md`
- `E:\datasets\reddit\derived\review\reddit_high_score_review_001_decisions.template.jsonl`
- `E:\datasets\reddit\derived\review\reddit_high_score_review_001_manifest.json`

Review helper:

- `E:\signal_agent\tools\datasets\reflective_pressure_review_batch.py`

Tests:

- `E:\signal_agent\tests\test_reflective_pressure_review_batch.py`

Facebook review workspace:

- `E:\signal_agent\data\inputs\reflective_pressure\facebook_seed_batch_001.jsonl` was not found, so no Facebook review files were generated.

## Manual Labeling

Open the markdown table first:

```text
E:\datasets\reddit\derived\review\reddit_high_score_review_001_table.md
```

Then edit the decision template:

```text
E:\datasets\reddit\derived\review\reddit_high_score_review_001_decisions.template.jsonl
```

Use only these decisions:

- `KEEP`
- `SKIP`
- `NEEDS_CORRECTION`
- `GOLD_CANDIDATE`

Every row must have a non-blank decision before an approved export can be created.

## Apply Decisions

```powershell
.\.venv\Scripts\python.exe tools\datasets\reflective_pressure_review_batch.py apply-decisions --input-jsonl E:\datasets\reddit\derived\reddit_seed_high_score_review_001.jsonl --decisions-jsonl E:\datasets\reddit\derived\review\reddit_high_score_review_001_decisions.template.jsonl --output-jsonl E:\datasets\reddit\derived\review\reddit_high_score_review_001_approved.jsonl
```

## Summarize Decisions

```powershell
.\.venv\Scripts\python.exe tools\datasets\reflective_pressure_review_batch.py summarize-decisions --decisions-jsonl E:\datasets\reddit\derived\review\reddit_high_score_review_001_decisions.template.jsonl
```

## Copy Approved Reddit Seeds To Repo

Only run this after manual decisions are complete and `summarize-decisions` reports ready for import.

```powershell
.\.venv\Scripts\python.exe tools\datasets\reflective_pressure_review_batch.py copy-approved-to-repo --approved-jsonl E:\datasets\reddit\derived\review\reddit_high_score_review_001_approved.jsonl --repo-output-path E:\signal_agent\data\inputs\reflective_pressure\reddit_high_score_review_001_approved.jsonl
```

## Import Approved Reddit Seeds

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-import-inputs --path data\inputs\reflective_pressure\reddit_high_score_review_001_approved.jsonl --classify
```

## Facebook Seeds

If a Facebook seed batch exists later at:

```text
E:\signal_agent\data\inputs\reflective_pressure\facebook_seed_batch_001.jsonl
```

Build its review workspace before importing:

```powershell
.\.venv\Scripts\python.exe tools\datasets\reflective_pressure_review_batch.py build-review --input-jsonl E:\signal_agent\data\inputs\reflective_pressure\facebook_seed_batch_001.jsonl --review-dir E:\signal_agent\data\inputs\reflective_pressure\review\facebook_seed_batch_001
```

Do not import Facebook seeds until the decisions template is filled and an approved JSONL has been created.

## Summary And Reconcile

Run these immediately after importing an approved batch:

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-summary --by next_actions
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-summary --by drift
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-reconcile
```

## Review Five Imported Inputs

Review only five imported records first:

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-review --input-id INPUT_ID_HERE
```

Watch for repeated drift patterns, but do not add new pressure types yet.

## Correct Drift

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-correct-classification --classification-id CLASSIFICATION_ID_HERE --input-id INPUT_ID_HERE --pressure-type spiritual_reductionism --hidden-pressure "The frame was collapsed into a narrower claim, preventing the deeper pressure from being addressed." --recognition-potential 5 --risk-of-tribal-escalation 4 --correction-reason "Manual operator review found the extractor label was close but needed sharper hidden-pressure articulation."
```

## Mark Golden Example

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-mark-golden --input-id INPUT_ID_HERE --classification-id CLASSIFICATION_ID_HERE --correction-id CORRECTION_ID_HERE --draft-id DRAFT_ID_HERE --pressure-type spiritual_reductionism --title "Frame collapsed into slogan" --why-it-matters "This shows how a deeper pressure can be reduced into a narrower claim that stops discernment." --reusable-pattern "Name the reduction without attacking the person; preserve the deeper frame." --voice-notes "Calm, direct, not smug, not over-explaining." --risk-notes "High risk of sounding superior if handled carelessly." --approved-for-prompt-export true
```

## Export Prompt Pack

```powershell
.\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-export-prompt-pack --path data\outputs\reflective_pressure\prompt_pack_001.md --approved-only true
```

## Do Not Do Yet

- Do not change ontology.
- Do not add pressure types.
- Do not tune classifier rules.
- Do not import unreviewed Reddit seeds.
- Do not import all 25 if the manual keep threshold is not met.
- Do not auto-post or connect platform APIs.
- Do not treat extractor labels as truth; use corrections to expose drift first.
