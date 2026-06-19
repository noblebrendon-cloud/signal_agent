# v0.2 Command Router Release Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Release Boundary

Phase 28 does not create a release by itself.

Phase 28 is a documentation/verification decision point that re-verifies the command-router foundation and approves bounded CLI integration as the next possible runtime step.

## Safe Claim After Phase 28

Use:

```text
v0.2 command-router foundation has been re-verified and is approved for bounded CLI integration planning.
```

This claim is limited to:

- Local command-router foundation.
- Covered explicit local output paths.
- Verification decision.
- Planning for CLI integration only.

## Unsafe Claims

Do not claim:

- v0.2 is production-ready.
- v0.2 includes a local server.
- Browser submission is implemented.
- UI is backend-wired.
- Production authoring writes are governed.
- Default production canonical ledgers are enabled.
- Repo-wide governance is complete.
- Complete IBVM proof exists.

## Current Verified Boundary

The verified boundary remains:

- Local.
- Non-production.
- Covered paths only.
- Explicit output paths only.
- No server behavior.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## What Phase 28 Adds

Phase 28 adds:

- Verification report.
- CLI integration decision.
- Phase 29 scope.
- Release boundary language.

Phase 28 does not add:

- Runtime code.
- CLI code.
- Server code.
- UI wiring.
- Production writes.
- Ledger defaults.

## Release Readiness

v0.2 is not yet release-ready.

Before a v0.2 release candidate, the project still needs:

- Phase 29 implementation decision outcome.
- If CLI integration is implemented, CLI tests.
- Updated status documentation.
- Final v0.2 verification report.
- Release note and tag-prep docs.

## Next Step

Recommended next step:

```text
Phase 29 - command-router CLI integration.
```

Do not move to local server or browser submission before completing the CLI integration boundary.
