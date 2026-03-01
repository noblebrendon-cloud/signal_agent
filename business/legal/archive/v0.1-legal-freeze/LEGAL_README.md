# Signal Agent / Laviathon — Legal Freeze Evidence (v0.1)

Legal Freeze Tag: v0.1-legal-freeze
Legal Freeze Commit: 40486fc39463fdf9d6d85900a6f5eb2e05d36470

## What this folder contains
- Copyright registration packet (MASTER + WORK_*.md)
- SNAPSHOT_HASH.txt (SHA256 evidence record)
- SYSTEM_FREEZE_v0.1.md (freeze declaration)

## How to verify (local)
Run:
- powershell -ExecutionPolicy Bypass -File tools\verify_legal_freeze.ps1

Or manually:
- git rev-parse v0.1-legal-freeze
- git show v0.1-legal-freeze --name-only
