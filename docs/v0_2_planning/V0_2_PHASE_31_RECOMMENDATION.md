# v0.2 Phase 31 Recommendation

Version target:

```text
v0.2-local-authoring-surface
```

## Recommendation

Phase 31 should be:

```text
Final v0.2 verification report covering router CLI integration plus all prior proof surfaces.
```

Do not move to local server work, browser-backend submission, production authoring writes, or release tagging before the final verification report.

## Verification Scope

Phase 31 should verify:

- Command-router CLI integration.
- Local command-router foundation.
- Path policy behavior.
- Workspace validation.
- Offline harness behavior.
- Offline CLI behavior.
- Demo proof bundle behavior.
- Static export/import behavior.
- Prototype bridge behavior.
- Governed Authoring backend proof path.
- Formal governance proof-pack behavior.
- Claim evidence enforcement.
- HQ promotion separation for the covered path.
- Canonical ledger adapter behavior.
- Operator canonical ledger linkage.

## Required Evidence

The final v0.2 verification report should record:

- Test commands.
- Pass/fail counts.
- Production JSONL fingerprint before and after verification.
- Whether source/runtime files changed during verification.
- Whether production ledgers changed.
- Whether server/network behavior was added.
- Whether browser-backend submission was added.
- Whether production authoring writes were added.
- Whether default production canonical ledger writes were added.
- Whether staged changes remain.

## Expected Boundary

The expected v0.2 verification boundary remains:

- Local.
- Non-production.
- Explicit-workspace only.
- Covered paths only.
- No default production writes.
- No repo-wide governance claim.
- No complete IBVM claim.

## Phase 32 Gate

Only after Phase 31 passes should Phase 32 prepare:

- v0.2 release note.
- v0.2 tag prep.
- Optional tag and prerelease steps.

Phase 32 should still preserve the non-production release boundary.
