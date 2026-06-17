# v0.2 Forbidden Path Policy

Version target:

```text
v0.2-local-authoring-surface
```

## Policy Purpose

This policy defines path rules for a future local command router. It is documentation/spec only.

## Core Rule

Writes must fail closed if path classification is ambiguous.

## Forbidden Paths

The router must reject writes to:

- Repo `data/`.
- Production ledger paths.
- Production authoring artifact paths.
- Implicit/default production paths.
- Hidden side-effect paths.

## Allowed Paths

Allowed:

- Temp directories.
- Explicit user-selected output directories.
- Explicit result packet paths outside repo `data/`.
- Explicit optional canonical ledger paths outside repo `data/`.
- Local summary paths inside an allowed output directory.

## Repo data/ Rule

Repo `data/` is forbidden for v0.2 local command-router writes.

Examples:

- `data/`
- `data/outputs/`
- `data/operator/`
- `data/claims/`
- `data/intake/`
- Any nested path under repo `data/`.

## Production Ledger Rule

Production ledger paths are forbidden.

Canonical ledger writes may occur only when:

- Ledger writing is explicitly requested.
- A safe explicit path is provided.
- The path is outside repo `data/`.
- The path is local/temp or caller-selected.

## Output Directory Rule

Output directories must be caller-selected.

The router must not infer:

- Repo production paths.
- Default ledger paths.
- Default artifact paths.
- Browser download paths as authority.

## Ambiguous Paths

Ambiguous path examples:

- Relative paths that resolve under `data/`.
- Symlinked paths that resolve under `data/`.
- Paths with unclear normalization.
- Paths that cannot be resolved before writing.

Required behavior:

- Fail before writing.
- Return structured forbidden or ambiguous path error.
- Leave existing files unchanged.

## Overwrite Rule

Default:

```text
Do not overwrite known output files.
```

Any overwrite policy must be explicit, opt-in, and tested.

## Non-Goals

This policy does not approve:

- Production artifact stores.
- Production canonical ledger defaults.
- Hosted storage.
- Repo-wide write governance.
- Complete IBVM write coverage.
