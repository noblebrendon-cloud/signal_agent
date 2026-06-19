# v0.2 Phase 32 Recommendation

Version target:

```text
v0.2-local-authoring-surface
```

## Recommendation

Phase 32 should be:

```text
v0.2 release note, tag preparation, tag, push, and GitHub prerelease creation.
```

Phase 32 should start only after the Phase 31 verification docs are committed.

## Suggested Tag

Recommended tag name:

```text
v0.2-local-authoring-surface
```

Recommended tag message:

```text
Verified local CLI authoring surface for covered Governed Authoring proof paths.
```

## Release Title

Recommended release title:

```text
v0.2-local-authoring-surface
```

## Required Release Claim

Use:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

## Required Boundary

The release must state:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.
- Not repo-wide governance.
- Not complete IBVM proof.

## Required Evidence To Cite

Phase 32 should cite:

- `156 passed`.
- Real CLI-router exercise into a temp workspace outside the repo.
- Six static-import-compatible result packets.
- Proof summaries produced.
- Explicit workspace ledger paths only.
- Production JSONL fingerprint unchanged.
- No source/runtime mutation during verification.
- No server/network behavior added.
- No static prototype UI changes.
- No production writes.

## Forbidden Phase 32 Scope

Do not add:

- Runtime/source changes.
- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Static prototype UI wiring.
- Production authoring artifacts.
- Default production ledger writes.

## Phase 32 Verification

Before tag or prerelease commands, Phase 32 should confirm:

- Release-note docs are the only staged files.
- `data/` remains quarantined.
- No source/runtime files are staged.
- No production ledgers are staged.
- Release language matches the Phase 31 boundary.
