# Stage 1 Spine Observability Guide

## Purpose

Stage 1 Spine Observability gives the operator a small local ledger for tracking content-platform presence and manually captured metrics by thematic spine. It is intended to answer basic questions such as:

- Which spines exist?
- Which platform accounts are assigned to each spine?
- What is the latest manually entered metric snapshot for each platform?
- Which platforms are under-tracked because they have no recent snapshot?

This is an observability foundation only. It is not a dashboard, collector, posting system, or automation agent.

## What Stage 1 Does

- Adds and lists spine records.
- Adds platform accounts under an existing spine.
- Adds manual metric snapshots under an existing platform account.
- Produces deterministic summaries grouped by spine.
- Detects under-tracked platforms from missing or stale recent snapshots.
- Stores append-only JSONL ledgers under local `data/state/`.
- Validates references fail-closed before appending records.

## What Stage 1 Does Not Do

- Does not call platform APIs.
- Does not scrape websites or social platforms.
- Does not post content.
- Does not send messages.
- Does not schedule external actions.
- Does not run a dashboard UI.
- Does not implement Laviathon evaluator behavior.
- Does not make autonomous decisions or approvals.

## Safety Contract

- Metrics are manual only.
- State is local only.
- No network calls are allowed.
- No scraping is allowed.
- No posting is allowed.
- No messaging is allowed.
- No autonomous external actions are allowed.
- `external_action_allowed` must remain `false`.
- Summaries are advisory only.
- The human operator remains the approving authority.

## Ledger And State Files

The module writes append-only, hash-chained JSONL records through the existing retention JSONL store pattern.

- `data/state/spine_observability_spines.jsonl`
- `data/state/spine_observability_platforms.jsonl`
- `data/state/spine_observability_metric_snapshots.jsonl`

Each append preserves prior records. The store rejects missing references, unsupported source types, and metric snapshots that attempt to allow external action.

## CLI Command Examples

Run commands from the repository root.

```powershell
py -m app.spine_observability.cli spine-add --name governance_spine --description "Governance, diagnostics, and execution integrity" --created-at 2026-05-14T00:00:00Z
```

```powershell
py -m app.spine_observability.cli spine-list
```

```powershell
py -m app.spine_observability.cli spine-add-platform --spine-name governance_spine --platform linkedin --account-label primary --content-lane governance --created-at 2026-05-14T00:05:00Z
```

```powershell
py -m app.spine_observability.cli spine-add-metric-snapshot --platform-account-id spa_REPLACE_WITH_OUTPUT_ID --captured-at 2026-05-14T12:00:00Z --metric-window-start 2026-05-07 --metric-window-end 2026-05-14 --metrics-json '{"followers":1200,"posts_last_7d":3,"impressions_last_7d":8500}' --notes "Manual weekly snapshot"
```

```powershell
py -m app.spine_observability.cli spine-summary --format json --under-tracked-days 7 --as-of 2026-05-14T12:00:00Z
```

```powershell
py -m app.spine_observability.cli spine-under-tracked --format json --days 7 --as-of 2026-05-14T12:00:00Z
```

## Example Workflow

Add the Governance Spine:

```powershell
py -m app.spine_observability.cli spine-add --name governance_spine --description "Governance, diagnostics, and execution integrity" --created-at 2026-05-14T00:00:00Z
```

Add the Reflective Spine:

```powershell
py -m app.spine_observability.cli spine-add --name reflective_spine --description "Reflection, witness, and relational trust" --created-at 2026-05-14T00:01:00Z
```

Add a platform account under the Governance Spine:

```powershell
py -m app.spine_observability.cli spine-add-platform --spine-name governance_spine --platform linkedin --account-label primary --content-lane governance --created-at 2026-05-14T00:05:00Z
```

Copy the `platform_account_id` from the JSON output, then add a manual metric snapshot:

```powershell
py -m app.spine_observability.cli spine-add-metric-snapshot --platform-account-id spa_REPLACE_WITH_OUTPUT_ID --captured-at 2026-05-14T12:00:00Z --metric-window-start 2026-05-07 --metric-window-end 2026-05-14 --metric followers=1200 --metric posts_last_7d=3 --metric impressions_last_7d=8500 --notes "Manual weekly snapshot"
```

View the grouped summary:

```powershell
py -m app.spine_observability.cli spine-summary --format text --under-tracked-days 7 --as-of 2026-05-14T12:00:00Z
```

Detect under-tracked platforms:

```powershell
py -m app.spine_observability.cli spine-under-tracked --format text --days 7 --as-of 2026-05-14T12:00:00Z
```

## Validation Boundaries

- Missing required fields are rejected.
- Duplicate spine names resolve to the same deterministic `spine_id` and are rejected on append.
- Platform accounts require an existing `spine_id` or `spine_name`.
- Metric snapshots require an existing `platform_account_id`.
- Metric snapshots require `source_type` to be `manual`.
- Metric snapshots reject `external_action_allowed=True`.
- Metrics must be a non-empty flat object of numeric values.
- Under-tracked detection is read-only and advisory.

## Test Commands

```powershell
py -m pytest tests/test_spine_observability.py -q
```

```powershell
C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m pytest tests/test_retention_cli.py -q
```

## Next Recommended Patch

Add a small operator index link after the guide is reviewed, or add a separate Laviathon evaluator contract only when Stage 2 scope is explicitly approved.

