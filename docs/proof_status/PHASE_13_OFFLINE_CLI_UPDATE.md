# Phase 13 Offline CLI Update

Commit: `5ee82a0 Add local Governed Authoring offline verification CLI`

Phase 13 adds a local CLI wrapper around the Governed Authoring offline harness. The command verifies static prototype export packets through the backend proof path and writes static-import-compatible result JSON.

## What Changed

Updated implementation file:

- `signal_agent/governed_authoring/cli.py`

New test file:

- `tests/test_governed_authoring_offline_cli.py`

## CLI Flow

The covered local-only flow is:

```text
static prototype export JSON file
-> local CLI command
-> offline Governed Authoring harness
-> backend Governed Authoring proof path
-> static-import-compatible result JSON file
```

Command:

```bash
python -m signal_agent.governed_authoring.cli verify-static-export \
  --input <static export json> \
  --output <static import result json>
```

Optional explicit-path canonical ledger output:

```bash
python -m signal_agent.governed_authoring.cli verify-static-export \
  --input <static export json> \
  --output <static import result json> \
  --canonical-ledger <explicit path>
```

## Covered Outcomes

Phase 13 proves:

- Valid provisional export -> static-import-compatible provisional result.
- Valid approved export -> static-import-compatible approved result.
- Missing evidence -> static-import-compatible rejected result.
- Blocking unresolved tension -> static-import-compatible deferred result.
- Generator/model self-approval -> static-import-compatible rejected result.
- Optional canonical ledger write -> explicit temp/caller path only.
- Missing input file -> nonzero exit and no result file.

## What Survives

CLI execution preserves:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Output status.

## What Is Now Proven

Phase 13 proves:

- A local CLI can verify static export packets through the backend proof path.
- Backend proof results can be emitted as static-import-compatible JSON files.
- Optional canonical ledger output is explicit-path only.
- The CLI adds no server code.
- The CLI adds no browser-backend submission.
- The CLI adds no network behavior.
- The CLI adds no production writes.
- The CLI does not change production JSONL ledgers in tests.

## Verification

Phase 13 verification included:

- `python -m pytest tests/test_governed_authoring_offline_cli.py -q`
- `python -m pytest tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q`
- `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q`
- `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q`
- Production JSONL fingerprint checks.

## What Phase 13 Does Not Prove

Phase 13 does not prove:

- Static UI submits to backend.
- A server/app surface exists.
- A production authoring artifact write path exists.
- A default production canonical authoring ledger write exists.
- UI is production-governed.
- Repo-wide promotion governance is complete.

## Proof Status Change

Before Phase 13:

```text
The offline packet loop was proven for covered fixtures, but there was no user-facing local command that accepted static export JSON and wrote static-import-compatible result JSON.
```

After Phase 13:

```text
A local CLI can verify static export packets through the backend proof path and write static-import-compatible result JSON.
```

Boundary remains:

```text
The static UI still does not submit to a backend.
No server/app surface exists.
No production authoring artifact write path exists.
No production canonical authoring ledger write is enabled by default.
The UI is still not production-governed.
Repo-wide promotion governance is not proven.
```
