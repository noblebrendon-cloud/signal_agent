# Governed Authoring Offline CLI

This document records the local offline verification CLI added in Phase 13 by commit `5ee82a0`.

The CLI entry point lives in `signal_agent/governed_authoring/cli.py`. It wraps the local offline Governed Authoring harness for static prototype export packets. It does not add server code, browser-to-backend submission, network behavior, production authoring artifact writes, default production canonical ledger writes, or production-governed UI behavior.

## Command

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
  --canonical-ledger <explicit temp or caller-provided jsonl path>
```

The command:

- Accepts a static prototype export JSON file.
- Runs the local offline Governed Authoring harness.
- Verifies the packet through the backend Governed Authoring proof path.
- Writes a static-import-compatible result JSON file to the explicit output path.
- Prints the same static-import-compatible result JSON to stdout.
- Writes canonical ledger output only when `--canonical-ledger` is explicitly provided.

## Primary Files

Implementation:

- `signal_agent/governed_authoring/cli.py`

Tests:

- `tests/test_governed_authoring_offline_cli.py`

Fixtures exercised by CLI tests:

- `tests/fixtures/governed_authoring/static_export_valid_provisional.json`
- `tests/fixtures/governed_authoring/static_export_valid_approved.json`
- `tests/fixtures/governed_authoring/static_export_missing_evidence.json`
- `tests/fixtures/governed_authoring/static_export_blocking_tension.json`
- `tests/fixtures/governed_authoring/static_export_generator_self_approval.json`

## Covered CLI Cases

| Case | Expected CLI result |
| --- | --- |
| Valid provisional static export | Static-import-compatible provisional result |
| Valid approved static export | Static-import-compatible approved result |
| Missing evidence | Static-import-compatible rejected result |
| Blocking unresolved tension | Static-import-compatible deferred result |
| Generator/model self-approval | Static-import-compatible rejected result |
| Optional canonical ledger path | One canonical entry written to explicit temp/caller path only |
| Missing input file | Nonzero exit and no result file |

## What Survives CLI Execution

The Phase 13 tests prove preservation of:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Output status.

When an explicit canonical ledger path is supplied, the resulting static-import-compatible packet also carries the canonical ledger entry id.

## What Is Proven

Phase 13 proves:

- A local CLI can verify static export packets through the backend proof path.
- The CLI writes static-import-compatible result JSON.
- Canonical ledger output is optional and explicit-path only.
- The command works without server code.
- The command works without browser-backend submission.
- The command adds no network behavior.
- The command adds no production writes.
- Production JSONL ledgers remain unchanged during CLI tests.

## What Is Not Proven

Phase 13 does not prove:

- The static UI submits to a backend.
- A server/app surface exists.
- A production authoring artifact write path exists.
- A default production canonical authoring ledger write exists.
- The UI is production-governed.
- Repo-wide promotion governance is complete.

## Publication Boundary

Allowed language:

- "A local CLI can verify static export packets through the backend proof path."
- "The CLI writes static-import-compatible result JSON."
- "Canonical ledger output is optional and explicit-path only."
- "No server, browser-backend submission, or production writes are added."

Disallowed language:

- "The UI is backend-wired."
- "The app is production-ready."
- "The prototype submits to the backend."
- "Production authoring writes are governed."
- "Repo-wide governance is complete."
