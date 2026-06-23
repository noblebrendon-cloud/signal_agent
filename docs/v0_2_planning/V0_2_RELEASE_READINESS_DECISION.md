# v0.2 Release Readiness Decision

Target branch:

```text
release/v0.2-local-authoring-surface
```

## Decision

After the Phase 35 documentation is committed locally and the branch is rechecked clean, the branch is eligible for push/tag preparation.

Do not push, tag, or create a GitHub prerelease until the Phase 35 docs are committed and the checks below are re-run.

## Current Evidence

Current repair commit:

```text
745745f Restore operator runtime source-control closure
```

Current verified result:

```text
158 passing tests
```

Clean release branch tracked JSONL baseline:

```text
6 0b01cec041f2e54b4dcc1467f89019bbcd5ab5eb0a5a4e6d34ff02e426c9da0d
```

## Readiness Criteria

Approve push/tag preparation only if all of the following are true:

- Release worktree is clean.
- All 158 tests pass.
- No excluded Letters commits are in ancestry.
- No `data/` files are in the branch diff.
- No local or remote `v0.2-local-authoring-surface` tag already exists.
- No remote `release/v0.2-local-authoring-surface` branch already exists unless intentionally updating it.
- No server, browser, or production-write boundary changed.
- Phase 35 docs are committed locally.

## Excluded Commits

The clean release branch must continue to exclude:

- `0560eac feat: update Letters collection during site publish`
- `532d9fb fix: keep Letters collection timestamps stable`
- `a59140a feat: publish Letters of Light to YouTube`

## Branch-Diff Boundary

The release branch should include only:

- v0.2 planning docs.
- v0.2 release docs.
- Governed Authoring command-router files and tests.
- Operator source-control closure repair needed by committed operator proof tests.

The branch diff should not include:

- `data/`.
- Static prototype UI changes beyond already committed v0.2 surfaces.
- Letters release-site or YouTube work.
- Server code.
- Browser-backend submission.
- Production authoring writes.
- Default production ledger writes.

## Safe Claim

Use:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces, fail-closed path validation, and a source-control-complete operator dependency closure.
```

Required qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Remaining Release Actions

After this decision package is committed and the branch is clean:

1. Push `release/v0.2-local-authoring-surface`.
2. Create annotated tag `v0.2-local-authoring-surface` from the clean release branch, not from `main`.
3. Push the tag.
4. Create a GitHub prerelease, not a production release.
