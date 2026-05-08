# Raspberry Pi Daily Witness Node Decision Log

## 2026-05-07: Do Not Deploy Full Dirty `main`

Decision:
Do not push or deploy the full local `main` branch for Raspberry Pi witness setup.

Reason:
Local `main` is ahead of `origin/main` by multiple commits and the worktree is broadly dirty. Only the daily witness package is required for Pi deployment.

Consequence:
Use a narrow deployment branch rather than pushing all local commits.

## 2026-05-07: Use a Narrow Deployment Branch

Decision:
Create a deployment branch from `origin/main` and cherry-pick the witness package commit when explicitly approved.

Reason:
This keeps Pi deployment reviewable, reversible, and separated from unrelated governed-shell, demo, and local dirty work.

Consequence:
The Pi should clone or pull the deployment branch, not workstation `main`.

## 2026-05-07: Pi Is a Witness/Checker First

Decision:
The Pi observes, checks, and records evidence. It does not act as an autonomous executor.

Reason:
The system identity is deterministic governance and operational continuity, not unrestricted automation.

Consequence:
No auto-repair, auto-commit, auto-push, auto-merge, unrestricted agent execution, or production mutation belongs in the Pi witness path.

## 2026-05-07: No External Actions by Default

Decision:
The Pi manual witness script must not contact external services, push to GitHub, send notifications, or upload receipts.

Reason:
Manual local evidence should be proven before any network sync or delivery surface is considered.

Consequence:
All network behavior remains operator-initiated until a later documented phase.

## 2026-05-07: Local Receipts Before Network Sync

Decision:
The first proof surface is a local timestamped receipt under `data/state/pi_witness_receipts/`.

Reason:
Receipts create observable continuity without giving the Pi publication or mutation authority.

Consequence:
Future observability should read receipts first, then propose any sync/export behavior separately.
