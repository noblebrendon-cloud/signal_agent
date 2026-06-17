# v0.2 Output Policy Test Matrix

Version target:

```text
v0.2-local-authoring-surface
```

## Matrix Purpose

This matrix defines future runtime tests for v0.2 output directory, path classification, overwrite, and ledger policies.

It is documentation/spec only. It does not add tests, runtime behavior, server behavior, browser-backend submission, production writes, or default production canonical ledger writes.

## Acceptance Cases

| Case | Candidate target | Expected classification | Expected result |
| --- | --- | --- | --- |
| Temp workspace | Explicit temp output directory for local proof run. | `allowed_temp_path` | Accept after classification. |
| Explicit workspace outside repo data | Caller-selected workspace outside repo `data/`. | `allowed_workspace_path` | Accept as workspace root. |
| Result path under workspace | `<workspace>/results/result.json`. | `allowed_workspace_path` | Accept for result output. |
| Summary path under workspace | `<workspace>/summaries/proof_summary.md`. | `allowed_workspace_path` | Accept for summary output. |
| Validation path under workspace | `<workspace>/validation/report.json`. | `allowed_workspace_path` | Accept for validation output. |
| Ledger path under workspace | `<workspace>/ledgers/canonical.jsonl`. | `allowed_explicit_ledger_path` | Accept only when ledger output is explicitly requested. |
| Draft path under workspace | `<workspace>/drafts/draft.md`. | `allowed_workspace_path` | Accept as local provisional draft output. |

## Rejection Cases

| Case | Candidate target | Expected classification | Expected result |
| --- | --- | --- | --- |
| Repo data workspace | `data/` or any path under repo `data/`. | `forbidden_repo_data_path` | Reject before writing. |
| Repo data result path | `data/outputs/result.json`. | `forbidden_repo_data_path` | Reject before writing. |
| Production ledger path | Known production JSONL or production ledger path. | `forbidden_production_ledger_path` | Reject before writing or appending. |
| Default implicit ledger path | No ledger path provided, but command tries to append one. | `unknown_path` | Reject before writing. |
| Parent traversal outside workspace | `<workspace>/results/../../outside.json`. | `forbidden_parent_traversal` | Reject before writing. |
| Ambiguous path | Path cannot be safely normalized or has symlink-like ambiguity where detectable. | `ambiguous_path` | Fail closed before writing. |
| Overwrite without policy | Existing local result file and no explicit overwrite flag. | `allowed_workspace_path` with existing target | Reject before overwrite. |
| Generated self-approval | Generated output attempts to act as its own approval authority. | Depends on path, governance failure | Reject approval claim. |

## Proof Cases

| Proof requirement | Expected test assertion |
| --- | --- |
| No production JSONL fingerprint change | Fingerprint production JSONL files before and after command. Values must match. |
| No default ledger write | Run command without explicit ledger path. No ledger file is created or appended. |
| No server/network behavior | Command runs locally without opening ports, network calls, or browser-backend submission. |
| No production authoring artifact write | Production artifact paths remain unchanged and no production artifact is created. |
| Explicit path required | Command without required output path fails before writing. |
| Classification before write | Denied path produces no file and returns structured path error. |
| Existing files preserved by default | Existing output file content remains unchanged when overwrite is not explicitly allowed. |

## Future Test Groups

Future implementation should group tests around:

- Path normalization.
- Workspace acceptance.
- Temp output acceptance.
- Forbidden repo `data/` rejection.
- Production ledger rejection.
- Production artifact rejection.
- Parent traversal rejection.
- Ambiguous path fail-closed behavior.
- No implicit output paths.
- No default ledger writes.
- No overwrite by default.
- Generated output self-certification rejection.
- Production JSONL fingerprint preservation.

## Required Fixtures

Future tests should create temp-only fixtures for:

- Static export input packet.
- Backend-compatible source packet.
- Existing result output file.
- Existing summary output file.
- Existing validation output file.
- Existing local ledger file.
- Parent traversal candidate path.
- Candidate path that resolves under repo `data/`.

Fixtures must not use production ledgers or production authoring artifact paths as writable targets.

## Non-Goals

This matrix does not prove:

- Production app readiness.
- Hosted server readiness.
- Browser-backend submission.
- Production authoring writes.
- Repo-wide governance.
- Complete IBVM proof.
