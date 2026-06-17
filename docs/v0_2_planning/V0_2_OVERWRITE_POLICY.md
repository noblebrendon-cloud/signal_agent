# v0.2 Overwrite Policy

Version target:

```text
v0.2-local-authoring-surface
```

## Policy Purpose

This policy defines default overwrite and append behavior for future v0.2 command-router outputs.

It is documentation/spec only. It does not implement overwrite checks, file writes, ledger appends, server behavior, browser-backend submission, or production authoring writes.

## Default Rule

Do not overwrite existing output files by default.

If a target output file exists, the future runtime must fail before writing unless a future explicitly approved overwrite flag is provided, documented, and tested.

## Known Bundle Files

Future commands must not overwrite existing known bundle files by default.

Known bundle files include local proof bundle outputs, static-import-compatible result packets, summaries, validation reports, metadata files, drafts, and optional local ledgers created by prior runs.

## Future Explicit Overwrite Flag

A future overwrite flag may be considered only after a separate implementation gate.

Minimum requirements:

- The flag must be explicit.
- The target path must still pass path classification.
- The target must not be under repo `data/`.
- The target must not be a production ledger.
- The target must not be a production artifact.
- The behavior must be covered by tests.
- The command output must record that overwrite was requested.

## Never-Overwrite Targets

The future runtime must never overwrite:

- Repo `data/` paths.
- Production ledger paths.
- Production authoring artifact paths.
- Production JSONL files.
- Paths classified as ambiguous or unknown.
- Paths that resolve outside the approved workspace through parent traversal.

## Ledger Append Policy

Canonical ledger append behavior is disabled by default.

Ledger append may occur only when:

- Ledger output is explicitly requested.
- An explicit ledger path is provided.
- The ledger path passes path classification.
- The ledger path is inside approved workspace `ledgers/` or an approved temp directory.
- The target is not a production ledger.
- The target is not under repo `data/`.

The future runtime must never append to production ledgers and must never infer a default canonical ledger path.

## Result Packet Policy

Static-import-compatible result packets must not overwrite existing files by default.

If a result packet path already exists, the command must fail unless a future explicit overwrite policy allows that specific local path.

## Summary Policy

Summary files must not overwrite existing files by default.

Future implementation may support explicit summary overwrite only for approved workspace or temp paths after tests cover the behavior.

## Validation Policy

Validation reports and error reports must not overwrite existing files by default.

If validation output cannot be written safely, the command should return a structured error rather than silently changing the output path.

## Draft Policy

Draft files are local and provisional.

Draft output must not overwrite existing drafts by default. Draft output must not be promoted into production artifact storage by overwrite or append behavior.

## Self-Certification Boundary

Generated output cannot act as its own approval authority.

Overwrite metadata, summaries, drafts, and result packets may describe a local decision. They must not self-certify publication readiness, human authority, production approval, or repo-wide governance.

## Required Future Tests

Future runtime tests must prove:

- Existing result files are not overwritten by default.
- Existing summary files are not overwritten by default.
- Existing validation files are not overwritten by default.
- Existing ledger files are not appended unless explicit ledger output is requested.
- Production ledger paths are never overwritten or appended.
- Repo `data/` paths are never overwritten or appended.
- Generated output cannot approve itself.

## Non-Goals

This policy does not approve:

- Production overwrite behavior.
- Production artifact mutation.
- Production ledger mutation.
- Hosted storage.
- Browser-backend submission.
- Repo-wide governance.
