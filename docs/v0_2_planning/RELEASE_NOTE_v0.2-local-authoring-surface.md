# v0.2-local-authoring-surface

Verified local CLI authoring surface over covered Governed Authoring proof paths.

## Safe Release Claim

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

## Required Qualifiers

This release is:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace and output paths only.

This release does not add:

- Server behavior.
- Browser-backend submission.
- Production writes.
- Default production ledger writes.

## Verification Summary

Phase 31 recorded:

- 156 tests passed.
- Local CLI-router exercise passed in a temporary workspace outside the repo.
- Static-import-compatible result packets were produced.
- Proof and inspection summaries were produced.
- Explicit workspace ledger output was used.
- Production JSONL fingerprint remained unchanged.

## Covered Surface

The v0.2 release-candidate evidence covers:

- Local command-router foundation.
- Governed Authoring CLI router command group.
- `router validate-output-directory`.
- `router verify-static-export`.
- `router run-demo-bundle`.
- `router summarize-proof-output`.
- `router inspect-result-packet`.
- Fail-closed path validation.
- Explicit workspace/output path requirements.
- Optional canonical ledger output only under explicit workspace ledger paths.
- Existing v0.1 formal-governance and covered Governed Authoring proof paths.

## Explicitly Unsafe Claims

Do not claim:

- v0.2 is a production app.
- v0.2 is a local server.
- The UI is backend-wired.
- Browser submission is implemented.
- Production authoring writes are implemented.
- Repo-wide governance is complete.
- Complete IBVM proof exists.

## Release Composition Note

Recommended release composition:

```text
clean v0.2-only release branch excluding unrelated Letters work
```

Current `main` includes unrelated Letters work in history:

```text
a59140a feat: publish Letters of Light to YouTube
```

If the tag is created from latest `main`, the release must be described as a repository checkpoint that includes concurrent Letters work.

## Prerelease Status

This should be published as a GitHub prerelease, not a production release.
