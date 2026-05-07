# Daily Witness Runtime V1

Generated: 2026-05-07
Scope: minimal runtime hardening
Runtime surface: `python -m signal_agent.health.daily_check`
Scheduling status: manual only

## Purpose

The Daily Witness Runtime v1 is the manual execution surface for the Signal Agent witness-node contract.

It exists to:
- observe repo, config, ledger, test, and runtime-health state
- verify compact governance surfaces
- reconcile declared authority against observed drift
- report one final operational status
- archive timestamped witness artifacts

It does not approve transitions, repair state, merge code, push code, run autonomous agents, or perform external delivery.

## Authority Boundaries

Read-only operations:
- git metadata inspection
- required authority file checks
- invariant checker execution
- bounded pytest execution
- canonical JSONL parse validation
- runtime health inspection

Witness-owned writes:
- `data/state/witness/reports/`
- `data/state/witness/snapshots/`
- `data/state/witness/manifests/`
- `data/state/witness/logs/`
- `data/state/witness/markers/`
- `data/state/witness/locks/`
- `data/state/witness/witness_daily.jsonl`

Prohibited operations:
- auto-commit
- auto-push
- auto-merge
- autonomous refactor
- unrestricted agent execution
- automatic repair
- production-state mutation
- external delivery

## Canonical Command

Use the module command as the canonical v1 surface. No CLI alias is added yet; keeping the command explicit avoids expanding the operator surface before scheduling is designed.

PowerShell:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
E:\signal_agent\.venv\Scripts\python.exe -B -m signal_agent.health.daily_check --repo-root E:\signal_agent
```

Portable shape:

```text
python -B -m signal_agent.health.daily_check --repo-root <repo-root>
```

## Expected Console Output

The console output is compact key-value text for daily review:

```text
final_status=<healthy|degraded|failed|unverified>
daily_witness_status=<healthy|degraded|failed|unverified>
status_meaning=<operator readable status meaning>
next_operator_action=<operator action token>
run_id=<timestamped witness run id>
git_revision=<observed git revision>
git_dirty_count=<changed or untracked path count>
hard_failures=<count>
soft_degradations=<count>
drift_warnings=<count>
unverified_stages=<count>
degraded_stages=<count>
failed_stages=<count>
snapshot=<witness snapshot path>
report=<witness report path>
manifest=<witness manifest path>
```

The operator should be able to decide the next action from these lines in under 60 seconds.

## Status Meanings

| Status | Meaning | Operator action |
|---|---|---|
| `healthy` | No hard failures, no unverified stages, no soft degradation, and no known drift warnings. | Review summary. No intervention required. |
| `degraded` | Review required, not emergency. Core authority is readable, but drift or soft degradation exists. | Read the report and plan remediation if repeated. |
| `failed` | A hard failure occurred. The run cannot be trusted as a clean daily witness. | Inspect failures before trusting downstream automation. |
| `unverified` | Visibility is incomplete. This is not success. | Rerun or inspect the environment before trusting the result. |

Degraded status includes:
- dirty worktree degradation
- content registry split degradation
- runtime drift degradation
- missing optional evidence when core authority remains readable
- non-fatal verification gaps

Classification rules:
- hard failures always classify the run as `failed`
- `unverified` does not hide hard failure
- `degraded` means review required, not emergency
- `healthy` means no hard failures or known drift warnings

## Artifact Locations

Witness root:

```text
data/state/witness/
```

Layout:

```text
data/state/witness/reports/YYYYMMDDTHHMMSSZ.md
data/state/witness/snapshots/YYYYMMDDTHHMMSSZ.json
data/state/witness/manifests/YYYYMMDDTHHMMSSZ.manifest.json
data/state/witness/logs/YYYYMMDDTHHMMSSZ.stdout.txt
data/state/witness/logs/YYYYMMDDTHHMMSSZ.stderr.txt
data/state/witness/witness_daily.jsonl
data/state/witness/locks/
data/state/witness/markers/
```

Retention notes:
- `witness_daily.jsonl` is append-only.
- Timestamped reports, snapshots, manifests, and logs are evidence artifacts.
- Existing production ledgers are never rotated, repaired, or rewritten by the witness runtime.
- The current repo ignores `data/state/`, so local witness archives are not shown as normal git changes.

## How To Read A Report

Start with:
1. `Status`
2. `Meaning`
3. `Next operator action`
4. `Compact Summary`
5. `Findings`
6. `Safe Execution Boundaries`

For `healthy`, the compact summary is usually enough.

For `degraded`, review each finding. Current expected degradation examples include dirty worktree, known artifact-registry split, and runtime health drift.

For `failed`, inspect hard failures before trusting downstream automation.

For `unverified`, rerun or inspect environment visibility before using the result.

## Raspberry Pi Readiness Status

Current status: manually executable and scheduling-ready in shape, but not scheduled.

Deployment-readiness runbook:
- `docs/operator/raspberry_pi_witness_node_setup.md`

Manual runner scripts:
- `scripts/run_daily_witness_check.sh`
- `scripts/run_daily_witness_check.ps1`

Ready:
- single module command
- explicit repo root
- lock file for overlapping run prevention
- timestamped artifacts
- append-only witness continuity ledger
- bounded test profile
- no network requirement
- no production mutation path

Not added yet:
- cron
- systemd
- notifications
- dashboards
- external delivery
- autonomous loops

Before Raspberry Pi scheduling, confirm:
- Python environment path
- repo path
- storage budget for `data/state/witness/logs/`
- daily timeout policy
- operator review cadence
- backup policy for witness artifacts
