# v0.2 Release Candidate Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Safe Release-Candidate Claim

Use:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

## Required Qualifiers

Every v0.2 release-candidate claim must preserve these qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Covered Surfaces

The v0.2 release-candidate boundary covers:

- Governed Authoring command-router CLI group.
- Explicit local workspace validation.
- Fail-closed path validation.
- Static export verification through the router CLI.
- Demo proof bundle execution through the router CLI.
- Proof-output summarization through the router CLI.
- Result-packet inspection through the router CLI.
- Optional canonical ledger output only when an explicit workspace ledger path is provided.
- Prior v0.1 proof-pack surfaces that remain part of the verification chain.

## Explicitly Unsafe Claims

Do not claim:

- v0.2 is a production app.
- v0.2 is a local server.
- The UI is backend-wired.
- Browser submission is implemented.
- Production authoring writes are implemented.
- Default production canonical ledger writes are enabled.
- Repo-wide governance is complete.
- Complete IBVM proof exists.

## Production Write Boundary

v0.2 CLI-router verification writes only to an explicit temporary workspace outside the repo.

It does not write to:

- Repo `data/`.
- Production ledgers.
- Production artifact stores.
- Static prototype UI files.
- Any default canonical ledger path.

## Server And Browser Boundary

v0.2 release-candidate evidence does not include:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Network behavior.
- Browser-backend submission.
- Backend-wired static UI behavior.

## Ledger Boundary

Canonical ledger output is supported only through explicit caller-selected paths under the validated workspace `ledgers/` directory.

No default production canonical authoring ledger write is enabled.

## Release Candidate Status

The Phase 31 evidence is sufficient to prepare v0.2 release-note and tag-prep documentation.

It is not sufficient to claim production readiness, repo-wide governance, or complete IBVM proof.
