# v0.2 Workspace Write Policy

Version target:

```text
v0.2-local-authoring-surface
```

## Core Policy

Future runtime must fail closed before writing if path classification is ambiguous.

It must:

- Create only known output files.
- Never default to production paths.
- Never write a canonical ledger unless an explicit path is provided.
- Never write under repo `data/`.
- Preserve evidence refs, unresolved tensions, review status, and output status.
- Keep local drafts separate from approved or promoted artifacts.

## Allowed Paths

Allowed:

- Caller-selected workspace directories.
- Temp directories.
- Explicit output directory arguments.
- Explicit optional ledger paths inside the workspace.

## Forbidden Paths

Forbidden:

- Repo `data/`.
- Production ledger paths.
- Production authoring artifact paths.
- Implicit output directories.
- Ambiguous paths.
- Parent traversal outside approved workspace.
- Overwrites without explicit policy.

## Known Output Files

Known outputs may include:

- `results/*.json`
- `summaries/proof_summary.md`
- `summaries/*.md`
- `summaries/*.json`
- `ledgers/*.jsonl`
- `validation/*.json`
- `validation/*.md`
- `drafts/*.md`
- `drafts/*.json`
- `metadata/*.json`

## Ledger Policy

Canonical ledger writes must be:

- Disabled by default.
- Explicitly requested.
- Written only to an approved workspace ledger path.
- Skipped on validation failure.

## Draft Policy

Drafts are:

- Local.
- Provisional.
- Non-production.

Drafts are not:

- Promoted artifacts.
- Production authoring artifacts.
- Approved publications.
- Canonical state transitions.
- Proof of repo-wide governance.

## Overwrite Policy

Default:

```text
Do not overwrite known output files.
```

Any overwrite behavior must be:

- Explicit.
- Opt-in.
- Tested.

## Failure Behavior

On validation failure, future runtime must:

- Write no result packet unless a failure report path is explicitly allowed.
- Write no ledger entry.
- Leave existing files unchanged.
- Return a structured error.

## Non-Goals

This policy does not approve:

- Production writes.
- Default canonical ledger writes.
- Hosted storage.
- Browser-backend submission.
- Repo-wide mutation policy.
