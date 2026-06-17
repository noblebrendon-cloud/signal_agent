# v0.2 Path Classification Policy

Version target:

```text
v0.2-local-authoring-surface
```

## Policy Purpose

This policy defines the path classification model for future v0.2 command-router write behavior.

It is documentation/spec only. It does not implement a classifier, create files, append ledgers, add server behavior, or wire any browser UI to a backend.

## Classification Requirement

Every future write target must be classified before file creation or append.

Classification must happen after path normalization and before any side effect.

If classification returns `ambiguous_path` or `unknown_path`, the runtime must fail closed before writing.

## Path Classifications

| Classification | Meaning | Required behavior |
| --- | --- | --- |
| `allowed_workspace_path` | Path resolves inside the approved caller-selected workspace. | Allow only if command type permits the target directory. |
| `allowed_temp_path` | Path resolves inside a temp directory selected for the run. | Allow only for local proof outputs and temp-only demo outputs. |
| `allowed_explicit_ledger_path` | Path resolves to an explicit ledger path inside approved workspace `ledgers/` or an approved temp directory. | Allow append only when ledger output is explicitly requested. |
| `forbidden_repo_data_path` | Path resolves under repo `data/`. | Reject before writing. |
| `forbidden_production_ledger_path` | Path resolves to a production ledger location or known production JSONL path. | Reject before writing or appending. |
| `forbidden_production_artifact_path` | Path resolves to a production authoring artifact path. | Reject before writing. |
| `forbidden_parent_traversal` | Path uses traversal or normalization to escape the approved workspace. | Reject before writing. |
| `ambiguous_path` | Path cannot be safely normalized, has symlink-like ambiguity where detectable, or has unclear ownership. | Fail closed before writing. |
| `unknown_path` | Path is outside known allowed and forbidden classes. | Fail closed before writing. |

## Fail-Closed Rule

The classifier must treat uncertainty as a denial.

Denied classifications:

- `forbidden_repo_data_path`
- `forbidden_production_ledger_path`
- `forbidden_production_artifact_path`
- `forbidden_parent_traversal`
- `ambiguous_path`
- `unknown_path`

## Path Normalization Rules

Future runtime implementation must:

- Resolve absolute paths before classification.
- Normalize relative paths against the caller-approved workspace or explicit command context.
- Reject parent traversal escaping the approved workspace.
- Compare resolved paths against the forbidden repo `data/` path.
- Reject symlink-like ambiguity where detectable.
- Perform classification before file creation.

## Repo Root Detection

The future classifier must use an explicit repo root for forbidden `data/` detection.

Required behavior:

- Resolve the repo root before classification.
- Resolve the repo `data/` directory path from that root.
- Reject candidate paths that equal or descend from repo `data/`.
- Reject paths that normalize into repo `data/` even if provided as relative paths.

## Workspace Root Detection

The approved workspace root must be explicit.

Required behavior:

- Resolve the approved workspace root before classification.
- Require output paths to remain inside the approved workspace unless they are approved temp paths.
- Reject paths that escape the approved workspace after normalization.
- Reject paths that rely on implicit current working directory behavior.

## Temp Path Detection

Temp output directories may be allowed for local proof runs.

Required behavior:

- The temp directory must be explicit in the command context.
- The candidate path must resolve under that temp directory.
- Temp writes must remain local and non-production.
- Temp writes must not be treated as production artifacts.

## Ledger Path Detection

Ledger paths must be explicit and classified separately from ordinary result paths.

Allowed:

- Approved workspace `ledgers/` path.
- Approved temp ledger path.

Forbidden:

- Repo `data/`.
- Production JSONL paths.
- Default canonical ledger paths.
- Implicit ledger paths.

## Production Artifact Detection

Future implementation must maintain a list or predicate for production authoring artifact paths before enabling writes.

Until that predicate exists, any uncertain artifact-like path must classify as `unknown_path` and fail closed.

## Classification Result Shape

A future classifier should return structured information similar to:

```text
classification
resolved_path
workspace_root
repo_data_root
reason
may_write
may_append
```

This shape is advisory for implementation planning. It does not create runtime behavior.

## Non-Goals

This policy does not prove:

- Repo-wide write governance.
- All state-mutating paths are gated.
- Universal self-certification prevention.
- Production identity or human authority.
- Complete IBVM proof.
