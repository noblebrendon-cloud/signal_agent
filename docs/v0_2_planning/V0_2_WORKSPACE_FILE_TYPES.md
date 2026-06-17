# v0.2 Workspace File Types

Version target:

```text
v0.2-local-authoring-surface
```

## Allowed File Types

The local workspace may contain:

- Static prototype export JSON.
- Backend-compatible source packet JSON.
- Static-import-compatible result JSON.
- `proof_summary.md`.
- Validation report JSON.
- Validation report markdown.
- Optional canonical ledger JSONL.
- Local draft markdown.
- Local draft JSON.
- Run metadata JSON.
- Command metadata JSON.
- Fingerprint JSON.

## File Type Contracts

### Static Prototype Export JSON

Purpose:

- Input from static prototype export/import flow.

Location:

- `inputs/`

### Backend-Compatible Source Packet JSON

Purpose:

- Input for covered Governed Authoring backend proof path.

Location:

- `inputs/`

### Static-Import-Compatible Result JSON

Purpose:

- Output from verified local proof paths.

Location:

- `results/`

### proof_summary.md

Purpose:

- Human-readable summary of local proof output.

Location:

- `summaries/`

### Validation Report JSON/Markdown

Purpose:

- Records validation outcomes and error details.

Location:

- `validation/`

### Optional Canonical Ledger JSONL

Purpose:

- Optional explicit local canonical ledger output.

Location:

- `ledgers/`

Boundary:

- Disabled by default.
- Explicit path only.
- Outside repo `data/`.

### Local Draft Markdown/JSON

Purpose:

- Local provisional draft output.

Location:

- `drafts/`

Boundary:

- Not a production artifact.
- Not a promoted state.

## Forbidden File Uses

Forbidden:

- Production authoring artifact writes.
- Production ledger writes.
- Implicit `data/` writes.
- Generated output used as its own approval authority.
- Hidden background state.
- Untracked default state mutations.
- Result packet treated as production approval.
- Draft treated as promoted artifact.

## Required Preservation

Future workspace output must preserve:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Output status.
- Local reviewer marker when provided.
- Self-certification rejection.
