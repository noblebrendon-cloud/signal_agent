# v0.2 Workspace Contract

Version target:

```text
v0.2-local-authoring-surface
```

## Workspace Purpose

The local workspace is the caller-selected directory where future v0.2 command-router outputs may be written.

It must remain:

- Local.
- Explicit-path.
- Non-production.
- Outside repo `data/`.
- Separate from production ledgers.
- Separate from production authoring artifacts.

This contract is documentation/spec only. It does not implement a runtime workspace.

## Workspace Contract

The command router should treat the workspace as an isolated local output root:

```text
<workspace>/
  inputs/
  results/
  summaries/
  ledgers/
  validation/
  drafts/
  metadata/
```

The workspace root must be caller-selected. It must not be inferred from production paths.

## Directory Contracts

### inputs/

Purpose:

- Contains copied or referenced input packets.

Allowed contents:

- Static prototype export JSON.
- Backend-compatible source packet JSON.
- Fixture reference metadata.

### results/

Purpose:

- Contains static-import-compatible result packets.

Allowed contents:

- Result JSON produced by covered proof-pack paths.

### summaries/

Purpose:

- Contains proof summaries and workflow summaries.

Allowed contents:

- `proof_summary.md`.
- Local workflow summary markdown or JSON.

### ledgers/

Purpose:

- Contains optional explicit local canonical ledger JSONL.

Allowed contents:

- Canonical ledger JSONL only when explicitly requested.

### validation/

Purpose:

- Contains validation reports and error reports.

Allowed contents:

- Validation report JSON.
- Validation report markdown.
- Router error reports.

### drafts/

Purpose:

- Contains local draft outputs.

Allowed contents:

- Local draft markdown.
- Local draft JSON.

Boundary:

- Drafts are provisional and non-production.

### metadata/

Purpose:

- Contains run metadata, command metadata, and fingerprints.

Allowed contents:

- Run metadata JSON.
- Command metadata JSON.
- Fingerprint records.

## Local Draft Boundary

A draft is local, provisional, and non-production.

A draft is not:

- A promoted artifact.
- A production authoring artifact.
- An approved publication.
- A canonical state transition.
- Proof of repo-wide governance.

## Non-Goals

This contract does not define:

- Production artifact storage.
- Production ledger policy.
- Hosted app storage.
- Browser-backend submission.
- Repo-wide mutation governance.
- Complete IBVM proof.
