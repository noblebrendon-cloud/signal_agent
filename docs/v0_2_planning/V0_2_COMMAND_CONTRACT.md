# v0.2 Command Contract

Version target:

```text
v0.2-local-authoring-surface
```

## Contract Scope

This contract defines command inputs, outputs, and boundaries for a future local-only command router. It does not implement the router.

## Accepted Input Types

The router design accepts:

- Static prototype export JSON.
- Backend-compatible source packet JSON.
- Existing Governed Authoring fixtures.
- Explicit output directory.
- Optional explicit canonical ledger path.

## Rejected Inputs

The router must reject:

- Missing files.
- Invalid JSON.
- Unsupported packet type.
- Paths under repo `data/`.
- Implicit or default production paths.
- Attempts to use generated output as its own approval authority.

## Global Required Inputs

All write-capable commands must require:

- Explicit input path or fixture selector.
- Explicit output directory or output file.

No write-capable command may infer a production output path.

## Global Optional Inputs

Optional inputs may include:

- Explicit canonical ledger path.
- Local reviewer marker.
- Output format for local summaries.
- No-overwrite override, only if a future phase approves it.

## Output Contract

Allowed outputs:

- Static-import-compatible result JSON.
- `proof_summary.md`.
- Optional explicit canonical ledger JSONL.
- Validation report JSON or markdown.
- Temp/local output directories.

Forbidden outputs:

- Repo `data/` writes.
- Production authoring artifacts.
- Default production canonical ledger writes.
- Implicit output paths.
- Overwrites without explicit policy.

## Command Contracts

### verify-static-export

Required:

- `--input <static-export-json>`
- `--output <result-json>` or `--out <output-dir>`

Optional:

- `--canonical-ledger <ledger-jsonl>`
- `--reviewer <local-marker>`

Writes:

- Result JSON.
- Optional ledger only when explicit.

### run-demo-bundle

Required:

- `--out <output-dir>`

Optional:

- `--canonical-ledger`

Writes:

- Fixture result JSON files.
- `proof_summary.md`.
- Optional canonical ledger inside output directory.

### inspect-result-packet

Required:

- `--input <result-json>`

Optional:

- `--report <report-path>`

Writes:

- Optional local report only.

### validate-output-directory

Required:

- `--out <candidate-output-dir>`

Writes:

- None.

### summarize-proof-output

Required:

- `--out <proof-output-dir>`

Optional:

- `--summary <summary-path>`

Writes:

- Summary JSON or markdown inside the chosen output directory.

## Result Code Contract

Suggested result codes:

- `0`: success.
- `2`: missing input, invalid JSON, or unsupported packet shape.
- `3`: forbidden path or attempted production write.
- `4`: governed decision rejected or deferred.
- `5`: expected demo outcome mismatch.
- `6`: unsupported result packet.
- `7`: ambiguous path classification.

## Non-Goals

The command contract does not approve:

- Server code.
- Browser-backend submission.
- Production writes.
- Default ledger writes.
- Production-governed UI.
- Repo-wide governance.
- Complete IBVM proof.
