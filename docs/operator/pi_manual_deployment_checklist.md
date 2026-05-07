# Pi Manual Deployment Checklist

Generated: 2026-05-07
Scope: manual Raspberry Pi deployment preparation
Scheduling status: not enabled
Runtime surface: `python -B -m signal_agent.health.daily_check`

## Purpose

Use this checklist to perform the first manual Raspberry Pi run of the Daily Witness Runtime v1.

This is deployment-preparation only. Do not add cron, systemd timers, schedulers, notifications, dashboards, external delivery, auto-repair, auto-commit, auto-push, auto-merge, or autonomous agents.

## 1. Pre-Deployment Assumptions

Confirm before touching the repo:

- [ ] Raspberry Pi is powered on.
- [ ] Raspberry Pi OS is installed.
- [ ] Network access exists for the human operator's clone/update step.
- [ ] Git is installed.
- [ ] Python 3 is installed.
- [ ] Python is version 3.11 or newer.
- [ ] Repo access is available.
- [ ] Operator understands that this phase is manual only.
- [ ] Operator understands that scheduling is prohibited in this phase.

Recommended checks:

```bash
hostname
uname -a
git --version
python3 --version
```

## 2. Clone Or Update Repo

Fresh Pi clone:

```bash
mkdir -p ~/signal-agent
cd ~/signal-agent
git clone <repo-url> signal_agent
cd signal_agent
```

Existing Pi repo:

```bash
cd ~/signal-agent/signal_agent
git status --short
git branch --show-current
git rev-parse HEAD
```

Manual update if appropriate:

```bash
git pull --ff-only
git status --short
git branch --show-current
git rev-parse HEAD
```

Operator rules:

- [ ] Confirm current branch.
- [ ] Confirm current commit.
- [ ] Confirm whether worktree is clean or intentionally dirty.
- [ ] Do not let the witness runtime pull the repo.
- [ ] Do not commit, push, merge, or repair anything as part of the witness run.

## 3. Python Environment Setup

From the repo root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If editable install is not possible, install the minimum known dependencies:

```bash
python -m pip install Jinja2 "pytest>=9"
```

Confirm:

```bash
python --version
python -m pytest --version
```

Checklist:

- [ ] venv created.
- [ ] venv activated.
- [ ] pip upgraded.
- [ ] repo installed or dependencies installed.
- [ ] pytest available.
- [ ] no scheduler installed.
- [ ] no notification sender installed.

## 4. Manual Witness Run

Preferred manual runner:

```bash
sh scripts/run_daily_witness_check.sh
```

Direct command:

```bash
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -B -m signal_agent.health.daily_check --repo-root "$(pwd)"
echo "exit_code=$?"
```

The runner and direct command are equivalent in authority. The runner does not schedule anything; it only calls the canonical module command and prints the exit code.

Checklist:

- [ ] command executed manually by the operator.
- [ ] command printed an exit code.
- [ ] report path was printed.
- [ ] snapshot path was printed.
- [ ] manifest path was printed.
- [ ] no external delivery occurred.
- [ ] no production mutation occurred.

## 5. Expected Outputs

Console summary:

```text
final_status=<healthy|degraded|failed|unverified>
daily_witness_status=<healthy|degraded|failed|unverified>
status_meaning=<meaning>
next_operator_action=<action>
run_id=<timestamped id>
git_revision=<sha>
git_dirty_count=<count>
hard_failures=<count>
soft_degradations=<count>
drift_warnings=<count>
unverified_stages=<count>
degraded_stages=<count>
failed_stages=<count>
snapshot=data/state/witness/snapshots/<run>.json
report=data/state/witness/reports/<run>.md
manifest=data/state/witness/manifests/<run>.manifest.json
```

Expected files:

- [ ] Markdown report in `data/state/witness/reports/`.
- [ ] JSON snapshot in `data/state/witness/snapshots/`.
- [ ] Manifest in `data/state/witness/manifests/`.
- [ ] Test stdout/stderr logs in `data/state/witness/logs/`.
- [ ] Append-only row added to `data/state/witness/witness_daily.jsonl`.

## 6. Status Interpretation

| Status | Exit code | Meaning | Operator response |
|---|---:|---|---|
| `healthy` | 0 | Required checks passed with no known drift warnings. | Record the run. No remediation required. |
| `degraded` | 1 | Review required, not emergency. Core authority remains readable, but drift or soft degradation exists. | Read findings. Decide whether remediation should happen later. |
| `failed` | 2 | Hard failure. Daily witness result is not clean or trusted. | Inspect hard failures before trusting downstream automation. |
| `unverified` | 3 | Visibility incomplete. This is not success. | Rerun or inspect environment before trusting the result. |

Common `degraded` examples:

- dirty worktree
- known content artifact registry split
- runtime reconciliation drift
- blocked or failed transition observations
- optional evidence unavailable while core authority remains readable

## 7. Failure Response

Inspect first:

- generated Markdown report
- hard failures in the compact summary
- `data/state/witness/logs/`
- git branch and commit
- venv/Python availability
- pytest availability
- malformed canonical JSONL details, if any

Do not fix automatically:

- do not repair ledgers
- do not commit or push
- do not merge
- do not delete historical artifacts
- do not edit production state to make the run pass
- do not bypass transition gates
- do not launch autonomous agents

Return to the workstation when:

- Pi dependency setup is unclear
- canonical ledgers appear malformed
- the repo path or branch is wrong
- the first run is `failed`
- repeated runs are `unverified`
- the operator cannot explain the degradation reason

## 8. Proof Of Safe Behavior

After the run, confirm:

- [ ] `network_actions` is empty in the JSON snapshot.
- [ ] `production_state_mutations` is empty in the JSON snapshot.
- [ ] `safe_execution_boundaries.witness_owned_root` is `data/state/witness`.
- [ ] witness-owned writes are under `data/state/witness`.
- [ ] no external delivery occurred.
- [ ] no auto-commit occurred.
- [ ] no auto-push occurred.
- [ ] no auto-merge occurred.
- [ ] no autonomous agent execution occurred.
- [ ] no scheduler was installed.

Useful readback:

```bash
tail -n 1 data/state/witness/witness_daily.jsonl
ls -lt data/state/witness/reports data/state/witness/snapshots data/state/witness/manifests | head
```

## 9. Readiness Gate

Do not schedule until:

- [ ] at least one manual Pi run completed.
- [ ] the operator recorded the first manual run.
- [ ] generated report was reviewed manually.
- [ ] generated snapshot was checked for safe execution boundaries.
- [ ] degraded/failed/unverified status is understood.
- [ ] no production mutation was observed.
- [ ] no external delivery was observed.

Still prohibited after this checklist:

- cron
- systemd timers
- schedulers
- notifications
- dashboards
- external delivery
- auto-repair
- auto-commit
- auto-push
- auto-merge
- autonomous agents

## First Manual Pi Run Record

Fill this out after the first Pi run:

```text
date_time:
pi_hostname:
repo_path:
git_branch:
git_commit:
command_used:
exit_code:
status:
hard_failures:
soft_degradations:
drift_warnings:
degradation_reasons:
report_path:
snapshot_path:
manifest_path:
witness_ledger_tail_checked: yes/no
safe_boundaries_checked: yes/no
production_mutation_observed: yes/no
external_delivery_observed: yes/no
operator_notes:
```

Do not mark the Pi as scheduling-ready until this record is complete and understood.

