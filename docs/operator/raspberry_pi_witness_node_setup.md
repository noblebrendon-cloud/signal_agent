# Raspberry Pi Witness Node Setup

Generated: 2026-05-07
Scope: deployment-readiness package only
Scheduling status: not enabled
Runtime surface: `python -B -m signal_agent.health.daily_check`

## Deployment Surface Review

The Daily Witness Runtime v1 is ready for manual Raspberry Pi trial runs, not unattended scheduling.

Canonical command:

```text
python -B -m signal_agent.health.daily_check --repo-root <repo-root>
```

Repo root assumption:
- The command must receive the local Signal Agent repository root with `--repo-root`.
- Manual runner scripts resolve the repo root from their own location unless an override is passed.

Python assumptions:
- Python `>=3.11`, matching `pyproject.toml`.
- Use `python -B` and `PYTHONDONTWRITEBYTECODE=1` to avoid runtime bytecode writes.

Dependency assumptions:
- Install the repo package in a local virtual environment.
- Install runtime dependencies from `pyproject.toml`.
- Install `pytest` for the bounded witness test slice.

Witness-owned write paths:
- `data/state/witness/reports/`
- `data/state/witness/snapshots/`
- `data/state/witness/manifests/`
- `data/state/witness/logs/`
- `data/state/witness/markers/`
- `data/state/witness/locks/`
- `data/state/witness/witness_daily.jsonl`

Ignored runtime artifacts:
- The repo currently ignores `data/state/`, so generated witness artifacts are local operational evidence, not normal git changes.

No production mutation:
- The witness runtime must not mutate production ledgers, source code, config, docs, external services, or deployment state.
- The runtime does not auto-commit, auto-push, auto-merge, repair ledgers, run unrestricted agents, notify operators, or deliver externally.

## Purpose

The Raspberry Pi witness node is a low-power local observer for daily continuity checks.

It should:
- observe
- verify
- reconcile
- report
- archive witness-owned evidence

It must not:
- approve transitions
- repair failures
- write outside witness-owned paths
- merge or push code
- send notifications
- perform external delivery
- become autonomous orchestration

Scheduling is not enabled in this phase.

## Hardware And Software Assumptions

Recommended hardware:
- Raspberry Pi 4 or newer
- 4 GB RAM preferred
- reliable power supply
- storage with enough free space for repo, venv, and witness archives
- local network access only if used for clone/update by a human operator

Software assumptions:
- Raspberry Pi OS 64-bit preferred
- Git installed
- Python 3.11 or newer installed
- `venv` support installed
- shell access for manual command execution

Suggested OS packages:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
python3 --version
git --version
```

Do not install cron jobs, systemd timers, notification senders, dashboards, or external delivery adapters for this phase.

## Git Clone Strategy

Clone strategy options:

```bash
mkdir -p ~/signal-agent
cd ~/signal-agent
git clone <repo-url> signal_agent
cd signal_agent
```

If the repository is transferred offline, place it at a stable path such as:

```text
/home/pi/signal-agent/signal_agent
```

Operator rules:
- Keep a single local repo root for witness runs.
- Do not let the witness runtime perform git pulls.
- Pull or transfer updates manually before a run when needed.
- Inspect `git status --short` before trusting a daily result.

## Python Venv Setup

From the repo root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If editable install is not desired, install the minimum known dependencies:

```bash
python -m pip install Jinja2 "pytest>=9"
```

The editable install is preferred because the runtime imports local `signal_agent`, `app`, and `shared` modules from the repo.

## Manual Witness Command

Linux or Raspberry Pi:

```bash
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -B -m signal_agent.health.daily_check --repo-root "$(pwd)"
echo "exit_code=$?"
```

Windows workstation:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m signal_agent.health.daily_check --repo-root E:\signal_agent
echo "exit_code=$LASTEXITCODE"
```

Manual runner scripts are available:

```bash
sh scripts/run_daily_witness_check.sh
```

```powershell
.\scripts\run_daily_witness_check.ps1
```

These scripts do not schedule anything. They only call the canonical module command and print the exit code.

For first-run deployment, use the step-by-step checklist:

```text
docs/operator/pi_manual_deployment_checklist.md
```

## Expected Output

Console output is key-value text:

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

Exit code meanings:
- `0`: healthy
- `1`: degraded
- `2`: failed
- `3`: unverified

`degraded` is review required, not emergency.

## Artifact Locations

Witness artifacts are written under:

```text
data/state/witness/
```

Expected layout:

```text
data/state/witness/reports/
data/state/witness/snapshots/
data/state/witness/manifests/
data/state/witness/logs/
data/state/witness/markers/
data/state/witness/locks/
data/state/witness/witness_daily.jsonl
```

The append-only witness continuity ledger is:

```text
data/state/witness/witness_daily.jsonl
```

The runtime must not write to production ledgers such as:
- `data/state/module_artifacts.jsonl`
- `data/state/transition_gate_events.jsonl`
- `data/state/artifact_registry.jsonl`
- `data/operator/`

## Pi Readiness Checklist

Before calling a Pi witness node ready for manual daily use:

- [ ] repo cloned or transferred to a stable path
- [ ] Python 3.11 or newer available
- [ ] venv created
- [ ] dependencies installed
- [ ] manual command runs
- [ ] report generated
- [ ] snapshot generated
- [ ] manifest generated
- [ ] witness ledger appended
- [ ] no production mutations observed
- [ ] no external delivery configured
- [ ] no scheduler installed
- [ ] no notification sender installed
- [ ] degraded and failed status meanings understood
- [ ] operator reviewed report manually

## Troubleshooting

Python too old:
- Install Python 3.11 or newer.
- Recreate `.venv`.

Import failure:
- Confirm the command runs from the repo root or passes the correct `--repo-root`.
- Prefer `python -m pip install -e ".[dev]"` in the venv.

Pytest unavailable:
- Install `pytest>=9` in the venv.
- Treat missing test runner as visibility failure, not success.

Lock file present:
- Check `data/state/witness/locks/`.
- Ensure no witness run is active.
- Remove a stale lock only after confirming no process is running.

Status is `degraded`:
- Read the generated report.
- Common expected causes include dirty worktree, content registry split, and runtime drift observations.

Status is `failed`:
- Inspect hard failures first.
- Do not trust downstream daily automation until the failure is understood.

Status is `unverified`:
- Treat as blocked visibility.
- Rerun after inspecting environment and dependencies.

## Rollback And Uninstall

Manual rollback:
- Stop using the runner scripts.
- Remove the Pi clone if it is no longer needed.
- Remove the venv:

```bash
rm -rf .venv
```

Witness artifacts:
- Keep `data/state/witness/` if audit continuity matters.
- If removing a test clone, archive `data/state/witness/` first if reports are operational evidence.

No scheduler rollback is needed in this phase because scheduling is not enabled.

## Git Hygiene And Checkpoint Guidance

The current workstation repo is broadly dirty. Do not commit unrelated worktree state as part of the witness package.

Task-specific files to include:
- `docs/operator/raspberry_pi_witness_node_setup.md`
- `docs/operator/daily_witness_runtime_v1.md`
- `docs/operator/OPERATOR_INDEX.md`
- `signal_agent/health/__init__.py`
- `signal_agent/health/daily_check.py`
- `tests/test_daily_witness_check.py`
- `scripts/run_daily_witness_check.sh`
- `scripts/run_daily_witness_check.ps1`

Files not to include:
- unrelated modified source files
- unrelated generated PDFs/text dumps
- root debug outputs
- historical migration artifacts unrelated to witness packaging
- `data/state/witness/` runtime artifacts

Witness artifacts to exclude:
- `data/state/witness/reports/*`
- `data/state/witness/snapshots/*`
- `data/state/witness/manifests/*`
- `data/state/witness/logs/*`
- `data/state/witness/witness_daily.jsonl`

Review staged files before committing:

```bash
git diff --cached --name-status
git status --short
```

Safe checkpoint pattern:

```bash
git add docs/operator/raspberry_pi_witness_node_setup.md
git add docs/operator/daily_witness_runtime_v1.md
git add docs/operator/OPERATOR_INDEX.md
git add signal_agent/health/__init__.py signal_agent/health/daily_check.py
git add tests/test_daily_witness_check.py
git add scripts/run_daily_witness_check.sh scripts/run_daily_witness_check.ps1
git diff --cached --name-status
```

Do not commit unrelated dirty worktree items to make the witness package look cleaner than it is.
