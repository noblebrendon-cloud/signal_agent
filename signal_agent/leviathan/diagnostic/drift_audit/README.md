# Drift Audit — README

Deterministic, offline log-drift diagnostic for the Signal Agent / Laviathon system.

## Prerequisites

```powershell
# From repo root (Python 3.11+)
$env:PYTHONPATH = "E:\signal_agent"
```

Jinja2 is already in `environment/requirements.lock` — no extra installs required.

## Quick start

```powershell
$env:PYTHONPATH = "E:\signal_agent"

python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case01_small_chatlog\input `
  --out .tmp\drift_demo_out `
  --format both
```

Outputs written to `.tmp\drift_demo_out\`:

```
run_manifest.json   — run_id, version, config_hash, status
output.json         — full audit report (metrics + signals + policy + recs)
report.html         — styled HTML report (Jinja2 or stdlib fallback)
recommendations.txt — plain-text bullet recommendations
logs.txt            — execution log (always written, even on error)
```

## All demo fixture commands

```powershell
$env:PYTHONPATH = "E:\signal_agent"

# Case 01 — small chat log (stable)
python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case01_small_chatlog\input `
  --out .tmp\case01_out --format both

# Case 02 — mixed JSONL sources
python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case02_mixed_sources\input `
  --out .tmp\case02_out --format both

# Case 03 — empty / noise input
python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case03_empty_or_noise\input `
  --out .tmp\case03_out --format json

# Case 04 — prompt injection signals
python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case04_prompt_injection_signals\input `
  --out .tmp\case04_out --format both

# Case 05 — ground-truth stable regression
python -m signal_agent.laviathon.cli.drift_audit_cli analyze `
  --input tests\drift_audit\fixtures\case05_regression_stable\input `
  --out .tmp\case05_out --format both
```

## Run tests

```powershell
$env:PYTHONPATH = "E:\signal_agent"
python -m pytest tests/drift_audit/ -v
```

## CLI reference

```
python -m signal_agent.laviathon.cli.drift_audit_cli analyze
  --input PATH      Input directory with .txt / .jsonl / .md logs (required)
  --out   PATH      Output directory; created if absent (required)
  --policy PATH     Optional policy file — enables policy evaluation
  --format          html | json | both (default: both)
  --strict          Return exit code 2 if policy evaluation fails
```

Exit codes:
- `0` — OK
- `2` — Policy failed under `--strict`
- `10` — Runtime error (partial artifacts still written)

## Accepted log formats

| Extension | Parsing rules |
|---|---|
| `.txt` / `.md` | One event per line. Optional `[ISO-timestamp]` prefix. Optional `Actor: text` prefix. |
| `.jsonl` | One JSON object per line. Keys: `text`/`message`/`content`, `timestamp`/`time`/`ts`, `source`/`actor`. Fallback to raw line if not valid JSON. |

## Adding a new log format

1. Add a `_load_<format>` function in `loader.py` following the existing `_load_text` / `_load_jsonl` pattern.
2. Return a `List[LogEvent]` with deterministic `event_id` via `_event_id(fp, line_index, text)`.
3. Register the extension in `load_input_dir` by adding `elif suf == ".yourext":`.
4. Add a fixture + test case.

## Metrics (V0)

| Metric | Range | Meaning |
|---|---|---|
| `stability_score` | 0–1 | 1 = fully stable |
| `drift_score` | 0–1 | 1 = maximum drift (1 − lexical_similarity) |
| `lexical_similarity` | 0–1 | TF cosine: first half vs last half |
| `volume_drift` | −1..+1 | Signed relative change in event count |
| `repetition_score` | 0–1 | Fraction of near-duplicate consecutive pairs |
| `instability_spike_count` | integer | Terms with ≥5x frequency spike in second half |
| `risk_level` | LOW/MED/HIGH/CRIT | Composite risk band |

## Module layout

```
signal_agent/leviathan/diagnostic/drift_audit/
  __init__.py    package marker
  schema.py      stdlib dataclasses: LogEvent, DriftMetrics, AuditReport, ...
  loader.py      file loading + event normalization
  analyzer.py    deterministic drift metrics (stdlib only)
  renderer.py    Jinja2 HTML + stdlib fallback; recommendations.txt
  run.py         end-to-end orchestrator; artifact writer

signal_agent/leviathan/cli/
  drift_audit_cli.py   argparse CLI entry point

tests/drift_audit/
  __init__.py
  test_drift_audit_golden.py   5 golden test cases
  fixtures/
    case01_small_chatlog/
    case02_mixed_sources/
    case03_empty_or_noise/
    case04_prompt_injection_signals/
    case05_regression_stable/
```
