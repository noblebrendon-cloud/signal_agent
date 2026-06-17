# v0.2 Output Directory Policy

Version target:

```text
v0.2-local-authoring-surface
```

## Policy Purpose

This policy defines the write-boundary contract for a future v0.2 command-router runtime.

It is documentation/spec only. It does not implement path validation, file creation, ledger append behavior, server behavior, browser-backend submission, production authoring writes, or default production canonical ledger writes.

The policy preserves the v0.1 proof-pack boundary while preparing a controlled local authoring surface.

## Core Rule

Future command-router writes must be explicit-path, local, non-production, and classified before any file is created.

If an output target is ambiguous, unknown, forbidden, or cannot be resolved before writing, the runtime must fail closed.

## Allowed Output Targets

The future runtime may allow these targets only after successful path classification:

- Caller-selected workspace directory.
- Temp directory.
- Explicit output directory argument.
- Explicit ledger path inside an approved workspace.
- Explicit result path inside an approved workspace `results/` directory.
- Explicit summary path inside an approved workspace `summaries/` directory.
- Explicit validation path inside an approved workspace `validation/` directory.
- Explicit metadata path inside an approved workspace `metadata/` directory.
- Explicit draft path inside an approved workspace `drafts/` directory.

## Preferred Workspace Layout

Allowed workspace-relative writes should use the Phase 23 workspace layout:

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

The workspace root must be caller-selected. It must not be inferred from repo state, production ledger locations, production artifact locations, browser download folders, or hidden runtime defaults.

## Forbidden Output Targets

The future runtime must reject writes to:

- Repo `data/`.
- Production ledger paths.
- Production authoring artifact paths.
- Implicit output directory.
- Hidden background state.
- Parent traversal outside approved workspace.
- Generated default paths not provided by caller.
- Ambiguous paths.
- Paths that resolve into forbidden directories after normalization.

## No Implicit Output Directory

Commands must not invent a default output directory.

Required behavior:

- A command that writes files must receive an explicit output directory or explicit output file path.
- A command that does not receive a required output path must fail before writing.
- A command must not fall back to repo `data/`, production ledgers, production artifacts, current working directory, or browser download paths.

## Result Output Policy

Static-import-compatible result packets may be written only to:

- An explicit result path under approved workspace `results/`.
- Another explicitly approved local output path outside forbidden directories.
- A temp output path selected for the run.

Result packets are local verification artifacts. They are not promoted artifacts, production authoring artifacts, publication approval, or proof of repo-wide governance.

## Summary Output Policy

Proof summaries and workflow summaries may be written only to:

- An explicit summary path under approved workspace `summaries/`.
- Another explicitly approved local output path outside forbidden directories.
- A temp output path selected for the run.

Summaries must not be treated as authority to approve their own generated claims.

## Validation Output Policy

Validation and error reports may be written only to:

- An explicit validation path under approved workspace `validation/`.
- Another explicitly approved local output path outside forbidden directories.
- A temp output path selected for the run.

Validation output may describe a decision. It must not create production state.

## Metadata Output Policy

Run metadata and fingerprints may be written only to:

- An explicit metadata path under approved workspace `metadata/`.
- Another explicitly approved local output path outside forbidden directories.
- A temp output path selected for the run.

Metadata may record command inputs, resolved output paths, classification results, production JSONL fingerprints, and local reviewer markers.

## Draft Output Policy

Drafts are local, provisional, and non-production.

Draft outputs are not:

- Promoted artifacts.
- Canonical state transitions.
- Publication approval.
- Production authoring artifacts.
- Evidence that all authoring is governed.

Drafts must remain under workspace `drafts/` or another explicitly approved local output path outside forbidden directories.

## Ledger Write Policy

Canonical ledger writing remains disabled by default.

Ledger writes may occur only when:

- The caller explicitly requests ledger output.
- The caller provides an explicit ledger path.
- The path is classified before append.
- The path is inside an approved workspace `ledgers/` directory or a temp directory.
- The path is outside repo `data/`.
- The path is outside production ledger locations.

The future runtime must never append to production ledgers and must never infer a default canonical ledger path.

## Overwrite Boundary

The future runtime must not overwrite existing known bundle files by default.

If an output file already exists, the runtime must fail unless a future explicitly approved overwrite flag is provided and tested.

Production ledger paths, production artifact paths, and repo `data/` paths must never be overwritten or appended to by v0.2 local authoring-surface commands.

## Non-Goals

This policy does not approve:

- Production Governed Authoring app behavior.
- Hosted server behavior.
- Browser-backend submission.
- Production authoring artifact writes.
- Default production canonical ledger writes.
- Repo-wide governance.
- Complete IBVM proof.

## Recommended Phase 25

Phase 25 should be:

```text
Local UI/server decision gate.
```

It should decide whether v0.2 remains CLI/router-only or permits any local server/browser submission work later. It must not add server code by itself.
