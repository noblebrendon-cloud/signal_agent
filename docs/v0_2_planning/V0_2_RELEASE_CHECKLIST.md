# v0.2 Release Checklist

Version target:

```text
v0.2-local-authoring-surface
```

## Required Verification

Before a v0.2 tag or prerelease, confirm:

- Router CLI tests pass.
- Router foundation tests pass.
- Existing local authoring proof-path tests pass.
- Bridge/backend tests pass.
- Existing integration tests pass.
- Formal governance tests pass.
- Real CLI-router commands run against a new temporary workspace outside the repo.
- Production JSONL fingerprint is unchanged before and after verification.
- No source/runtime files changed during verification.
- No production ledgers changed.
- No staged changes remain before release prep begins.

## Phase 31 Verification Result

Phase 31 recorded:

- `156 passed`.
- Five successful CLI-router commands.
- Temporary workspace outside the repo.
- Six static-import-compatible result packets.
- Two explicit workspace canonical ledgers.
- Three proof summary/report files.
- Unchanged production JSONL fingerprint.

## Mandatory Release Boundary

Use this release-candidate claim:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

Include these qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Release Prep Checklist

Before running tag or release commands:

- Commit Phase 31 verification docs only.
- Confirm `data/` remains quarantined from commit planning.
- Confirm no static prototype UI files are staged.
- Confirm no source/runtime files are staged.
- Confirm no production ledgers are staged.
- Confirm the release note does not claim production app readiness.
- Confirm the release note does not claim repo-wide governance.
- Confirm the release note does not claim complete IBVM proof.

## Phase 32 Candidate Actions

Phase 32 may prepare:

- v0.2 release note.
- v0.2 tag-prep summary.
- Recommended tag name.
- Recommended tag message.
- GitHub prerelease body.

Phase 32 should not add runtime behavior.

## Forbidden Release Claims

Do not include:

- Production app.
- Local server.
- Backend-wired UI.
- Browser submission.
- Production authoring writes.
- Repo-wide governance.
- Complete IBVM proof.
