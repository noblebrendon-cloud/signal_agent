# v0.2 Write Boundary Spec

Version target:

```text
v0.2-local-authoring-surface
```

## Purpose

This spec defines allowed and forbidden write behavior for v0.2 planning before any runtime implementation begins.

## Core Rule

All v0.2 writes must be explicit-path and non-production.

No v0.2 command or surface may write to repo `data/` by default.

## Allowed Writes

Allowed:

- Explicit caller-selected output directory.
- Temp output directories.
- Explicit optional ledger path outside repo `data/`.
- Local proof summaries.
- Static-import-compatible result packets.
- Local draft files only when the caller selects the output path.

## Forbidden Writes

Forbidden:

- Repo `data/` writes.
- Production authoring artifact writes.
- Default canonical ledger writes.
- Implicit output paths.
- Overwriting known outputs without explicit policy.
- Hidden side-effect writes.
- Browser-triggered writes without a local decision gate.

## Optional Ledger Rule

Canonical ledger writes must remain:

- Disabled by default.
- Explicitly configured.
- Written only to caller-selected paths.
- Outside repo `data/` unless a future phase explicitly changes policy.

## Output Directory Rule

The output directory must be:

- Caller-selected.
- Visible in command output.
- Recorded in proof summary.
- Rejected if it is inside repo `data/`.

## Overwrite Policy

Default policy:

```text
Do not overwrite known output files.
```

Any overwrite support must be explicit and tested.

## Forbidden Path Behavior

If a forbidden path is supplied, the command should:

- Fail before writing.
- Return a clear error message.
- Leave existing files unchanged.
- Record no ledger entry.

## Required Tests Before Runtime

Any runtime implementation should include tests proving:

- Output under repo `data/` is rejected.
- Missing explicit output path is rejected.
- Optional ledger writes do not occur by default.
- Optional ledger path under repo `data/` is rejected.
- Known outputs are not overwritten by default.
- Production JSONL fingerprint remains unchanged.

## Non-Goals

This write boundary does not define:

- Production artifact store.
- Production ledger policy.
- Hosted storage.
- Repo-wide mutation policy.
- Complete IBVM write coverage.

## Phase 22 Requirements

Phase 22 command-router design must include:

- Required output arguments.
- Forbidden path checks.
- Optional ledger arguments.
- No-overwrite behavior.
- Test plan for production write prevention.
