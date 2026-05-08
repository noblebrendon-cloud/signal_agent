# Raspberry Pi Daily Witness Node Implementation Plan

Status: proposed
Last updated: 2026-05-07

## Phase 0: Repo Stabilization and Branch Strategy

Objective:
Keep Pi deployment isolated from the dirty workstation state and unrelated ahead commits.

Files touched:
- `docs/operator/pi_witness_node/PROJECT.md`
- `docs/operator/pi_witness_node/IMPLEMENTATION_PLAN.md`
- `docs/operator/pi_witness_node/TASK_LEDGER.md`
- `docs/operator/pi_witness_node/DECISION_LOG.md`

Commands:
```powershell
git status --short
git log --oneline origin/main..main
git switch -c deploy/daily-witness-v1 origin/main
git cherry-pick d0698b6
```

Tests/checks:
```powershell
git diff --name-only origin/main..HEAD
git status --short
```

Done criteria:
- deployment branch contains only approved witness files
- no generated artifacts are staged
- no unrelated dirty worktree items are committed

## Phase 1: Narrow Witness Runtime Verification

Objective:
Verify the existing Daily Witness Runtime source and focused tests before Pi transfer.

Files touched:
- `signal_agent/health/daily_check.py`
- `tests/test_daily_witness_check.py`
- `scripts/run_daily_witness_check.sh`
- `scripts/run_daily_witness_check.ps1`

Commands:
```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests\test_daily_witness_check.py -q
```

Tests/checks:
- focused witness tests pass
- no `data/state/` files are staged
- no `__pycache__/` or `.pyc` files are staged

Done criteria:
- focused witness tests pass locally
- operator docs identify the canonical command
- deployment branch remains narrow

## Phase 2: Pi Clone/Pull Setup

Objective:
Put the narrow branch onto the Pi without exposing unrelated local work.

Files touched:
- none expected on workstation during Pi setup

Commands:
```bash
git clone --branch deploy/daily-witness-v1 https://github.com/noblebrendon-cloud/signal_agent.git
cd signal_agent
git branch --show-current
git log --oneline -3
```

Tests/checks:
```bash
test -f scripts/run_daily_witness_check.sh
test -f scripts/run_pi_witness_check.sh
test -f tests/test_daily_witness_check.py
```

Done criteria:
- Pi is on the deployment branch
- latest commit matches the approved deployment commit
- no local secrets are present in the cloned repo

## Phase 3: Local Daily Check Script

Objective:
Run a manual Pi witness check without scheduling or external side effects.

Files touched:
- `scripts/run_pi_witness_check.sh`
- `scripts/run_pi_witness_check.ps1`

Commands:
```bash
bash scripts/run_pi_witness_check.sh
```

Tests/checks:
```bash
git status --short -- data/state/pi_witness_receipts
```

Done criteria:
- script prints repo path, branch, commit, and exit code
- script does not commit, push, delete, or contact external services
- script writes one local timestamped receipt

## Phase 4: Receipt Generation

Objective:
Preserve local evidence for manual review before any network sync is considered.

Files touched:
- `data/state/pi_witness_receipts/` local runtime files only

Commands:
```bash
ls -la data/state/pi_witness_receipts
cat data/state/pi_witness_receipts/<receipt>.json
```

Tests/checks:
- receipt includes timestamp, repo path, branch, commit, test command, and status
- receipt path stays under `data/state/pi_witness_receipts/`

Done criteria:
- operator can identify the first manual Pi run
- receipt remains local and ignored unless explicitly exported later

## Phase 5: Optional GitHub Sync

Objective:
Only after manual proof, decide whether Pi should pull code updates from GitHub. No Pi push behavior is allowed by default.

Files touched:
- none expected

Commands:
```bash
git fetch origin
git status --short
git log --oneline HEAD..origin/deploy/daily-witness-v1
```

Tests/checks:
- fetch is operator-initiated
- no push remote action occurs from the Pi
- no receipt upload occurs

Done criteria:
- explicit operator approval exists before any network sync is automated
- Pi remains a witness/checker, not a publisher

## Phase 6: Dashboard/State Summary Later

Objective:
Design lightweight observability only after manual witness behavior is stable.

Files touched:
- not defined yet

Commands:
- none yet

Tests/checks:
- dashboard/state summary must read from receipts and witness artifacts
- no production mutation is allowed

Done criteria:
- dashboard proposal exists as documentation first
- scheduling and external delivery remain separate decisions
