# v0.2 Command Router Design

Version target:

```text
v0.2-local-authoring-surface
```

## Router Purpose

The local command router is a local-only interface over existing covered proof-pack paths:

- Offline harness.
- Local offline CLI.
- Demo proof bundle.
- Static export/import packet flow.
- Governed Authoring backend proof path.
- Optional explicit-path canonical ledger behavior.

The router should make covered local workflows easier to run without adding server behavior, browser-backend submission, production writes, default canonical ledger writes, or production-governed UI claims.

## Non-Goals

The router design does not approve:

- Server code.
- Browser-backend submission.
- Production writes.
- Default canonical ledger writes.
- Production authoring artifact store.
- Production-governed UI.
- Repo-wide governance.
- Complete IBVM proof.

## Proposed Command Groups

| Command group | Purpose | Existing proof-pack relationship |
| --- | --- | --- |
| `verify-static-export` | Verify one static prototype export packet. | Routes to offline harness or existing offline CLI behavior. |
| `run-demo-bundle` | Run representative fixtures into an explicit output directory. | Routes to demo proof bundle behavior. |
| `inspect-result-packet` | Inspect a static-import-compatible result packet. | Reads local result packet output only. |
| `validate-output-directory` | Classify an output path before writing. | Enforces write boundary and forbidden path policy. |
| `summarize-proof-output` | Produce or refresh local summary over result files. | Reads explicit local output directory. |

## Command: verify-static-export

Purpose:

- Convert and verify a static prototype export JSON file through covered proof-pack paths.

Required inputs:

- Static prototype export JSON path.
- Explicit output result JSON path or output directory.

Optional inputs:

- Explicit canonical ledger JSONL path outside repo `data/`.
- Local reviewer marker for local summary metadata.

Output path behavior:

- Must write to a caller-selected path.
- Must reject implicit production paths.

Allowed writes:

- Static-import-compatible result JSON.
- Optional explicit ledger JSONL if configured.

Forbidden writes:

- Repo `data/`.
- Production authoring artifact paths.
- Default canonical ledger paths.

Expected result codes:

- `0`: verification succeeded.
- `2`: input error.
- `3`: forbidden path.
- `4`: governed decision rejected or deferred.

## Command: run-demo-bundle

Purpose:

- Run representative fixtures through the local proof path.

Required inputs:

- Explicit output directory.

Optional inputs:

- Enable explicit canonical ledger inside the output directory.

Output path behavior:

- Must reject repo `data/`.
- Must not overwrite known outputs without explicit policy.

Allowed writes:

- Result JSON packets.
- `proof_summary.md`.
- Optional canonical ledger JSONL inside output directory.

Forbidden writes:

- Production ledgers.
- Production authoring artifacts.
- Implicit output paths.

Expected result codes:

- `0`: all fixture outcomes matched expectations.
- `3`: forbidden path.
- `5`: fixture verification mismatch.

## Command: inspect-result-packet

Purpose:

- Read and summarize an existing static-import-compatible result packet.

Required inputs:

- Result packet JSON path.

Optional inputs:

- Markdown report output path.

Allowed writes:

- Optional local inspection report.

Forbidden writes:

- Ledger writes.
- Production artifact writes.

Expected result codes:

- `0`: packet inspected.
- `2`: missing or invalid input.
- `6`: unsupported packet shape.

## Command: validate-output-directory

Purpose:

- Classify an output directory before another command writes.

Required inputs:

- Candidate output directory.

Allowed writes:

- None by default.

Expected result codes:

- `0`: allowed.
- `3`: forbidden.
- `7`: ambiguous path, fail closed.

## Command: summarize-proof-output

Purpose:

- Summarize local proof output files in an explicit directory.

Required inputs:

- Explicit local output directory.

Optional inputs:

- Markdown summary output path inside the same output directory.

Allowed writes:

- Local summary markdown or JSON.

Forbidden writes:

- Repo `data/`.
- Production artifact paths.
- Default ledger paths.

Expected result codes:

- `0`: summary produced.
- `2`: missing output directory.
- `3`: forbidden path.

## Local Authority Integration

Router commands must preserve:

- Local reviewer marker.
- Review status.
- Evidence refs.
- Output status.
- Unresolved tensions.
- Self-certification rejection.

Local reviewer markers are not production identity, authentication, legal authority, or publication approval.

## Recommended Phase 23

Phase 23 should be:

```text
Local file workspace contract.
```

It should define the workspace layout for inputs, results, summaries, optional ledgers, draft outputs, and forbidden paths before router runtime implementation.
