# Raspberry Pi Daily Witness Node Project

Status: proposed
Last updated: 2026-05-07
Scope: tracked implementation project

## Purpose

The Raspberry Pi Daily Witness Node is a small local witness/check machine for Signal Agent. Its first job is to make the existing Daily Witness Runtime repeatable from a low-power host without expanding authority or pushing the whole local worktree.

The project turns the Pi witness idea into a tracked operational path with a plan, task ledger, decision log, scripts, and tests.

## Scope

In scope:
- narrow deployment branch planning
- manual Pi clone or pull setup
- deterministic witness health checks
- local timestamped receipt generation
- operator-readable status and evidence
- future-ready hooks for state tracking and lightweight observability

Out of scope for this phase:
- cron
- systemd timers
- dashboards
- notifications
- auto-repair
- auto-commit
- auto-push
- auto-merge
- unrestricted agent execution
- external service delivery

## Operating Model

The Pi is a witness/checker first. It observes repository state, runs narrow checks, writes local receipts, and gives the operator evidence to review.

The Pi does not own governance decisions. It does not modify production state. It does not publish, merge, deploy, or repair code.

## Expected Pi Responsibilities

- clone or pull a narrow deployment branch chosen by the operator
- run `scripts/run_pi_witness_check.sh` manually during the preparation phase
- run the Daily Witness Runtime indirectly through the existing witness package when configured
- write local receipts under `data/state/pi_witness_receipts/`
- preserve local evidence for operator review
- avoid secrets and external side effects by default

## Expected Laptop and GitHub Responsibilities

- keep broad dirty workstation changes local until intentionally reviewed
- create narrow checkpoint commits for witness work
- push only an explicit deployment branch for Pi use
- preserve GitHub as the source for code, not Pi-generated production mutations
- keep secret-bearing config out of tracked deployment branches

## Success Looks Like

- the Pi can clone or checkout a narrow deployment branch
- the manual Pi witness script runs without committing, pushing, deleting, or contacting external services
- the focused witness test passes or fails visibly
- a timestamped receipt is written locally
- the operator can tell what branch, commit, command, and status were observed
- scheduling is intentionally deferred until manual runs are proven

## Risks

- pushing all of local `main` would publish unrelated governed-shell, demo, and dirty-context work
- untracked local files may include sensitive or generated artifacts
- data/state outputs must remain local evidence, not production source
- Pi execution should not silently become orchestration
- missing dependencies on Pi may classify the run as failed or unverified until setup is complete

## Current Status

Current branch observed during project creation: `main`.

Latest relevant commits:
- `d0698b6 Add daily witness runtime and Pi deployment package`
- `699ea49 Stop tracking Python bytecode caches`
- `6bacbd8 Protect secret-bearing local env and integration config`
- `7d0367f Add controlled failure demo module`

Already implemented:
- `signal_agent/health/daily_check.py`
- `tests/test_daily_witness_check.py`
- `scripts/run_daily_witness_check.sh`
- `scripts/run_daily_witness_check.ps1`
- `docs/operator/daily_witness_runtime_v1.md`
- `docs/operator/raspberry_pi_witness_node_setup.md`
- `docs/operator/pi_manual_deployment_checklist.md`

Partially implemented:
- Pi deployment is documented but not yet performed
- deployment branch strategy is recommended but not yet created
- manual witness execution exists, but Pi-specific receipts need a narrow wrapper path
- scheduling is intentionally absent

Unsafe to touch right now:
- broad dirty worktree entries outside this project slice
- `data/state/` runtime artifacts
- untracked generated docs/assets/artifacts without separate review
- full `main` push for Pi deployment

Narrow path next:
- create a deployment branch from `origin/main`
- cherry-pick the witness package commit only
- run focused witness tests
- push that deployment branch only when explicitly approved
- clone that branch on the Pi and run the manual script once
