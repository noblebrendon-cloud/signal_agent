# v0.2 Command Router Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Boundary Purpose

This document defines the claim boundary after Phase 26 added the local command-router runtime foundation.

## Supported Claim

Allowed:

```text
v0.2 has a local command-router foundation with fail-closed path classification for covered explicit local output paths.
```

Required qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit output paths only.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Covered Runtime Surface

Phase 26 covers:

- Path classification before writes.
- Workspace validation.
- Explicit output validation.
- Optional explicit ledger path validation.
- Overwrite denial by default.
- Local command-router delegation to existing Governed Authoring proof paths.

## Covered Router Commands

The covered router commands are:

- `verify-static-export`
- `run-demo-bundle`
- `inspect-result-packet`
- `validate-output-directory`
- `summarize-proof-output`

## Covered Path Outcomes

The path policy represents:

- `allowed_workspace_path`
- `allowed_temp_path`
- `allowed_explicit_ledger_path`
- `forbidden_repo_data_path`
- `forbidden_production_ledger_path`
- `forbidden_production_artifact_path`
- `forbidden_parent_traversal`
- `ambiguous_path`
- `unknown_path`

The denied and uncertain classes fail closed before writing.

## Write Boundary

Allowed writes are local and explicit only:

- Result packets under approved workspace `results/`.
- Summaries under approved workspace `summaries/`.
- Validation reports under approved workspace `validation/`.
- Metadata under approved workspace `metadata/`.
- Drafts under approved workspace `drafts/`.
- Optional explicit ledgers under approved workspace `ledgers/`.
- Approved temp paths only when explicitly provided.

Forbidden writes:

- Repo `data/`.
- Production ledgers.
- Production authoring artifact paths.
- Default canonical ledger paths.
- Implicit output directories.
- Parent traversal outside approved workspace.
- Ambiguous or unknown paths.
- Existing outputs by default.

## UI And Server Boundary

Phase 26 does not add:

- Local server.
- HTTP endpoint.
- Websocket behavior.
- Browser-backend submission.
- Browser-to-Python submission.
- Hosted app behavior.
- Backend-wired UI.

Manual static export/import remains the safe browser-adjacent path.

## Production Boundary

Phase 26 does not create production artifacts, production ledgers, production app behavior, or production identity/authority behavior.

Local reviewer markers and result packets remain local proof/workflow fields only.

## Still Out Of Scope

Do not claim:

- v0.2 is production-ready.
- v0.2 includes a local server.
- Browser submission is implemented.
- The UI is backend-wired.
- Production authoring writes are governed.
- Repo-wide governance is complete.
- Complete IBVM proof exists.

## Next Boundary Decision

Phase 28 should decide whether the command-router foundation is ready for CLI exposure, or whether it should remain internal for one more verification phase.
