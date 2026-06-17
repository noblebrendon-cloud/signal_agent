# v0.2 Success Criteria

Version target:

```text
v0.2-local-authoring-surface
```

## Definition Of Success

v0.2 succeeds if it makes the covered local Governed Authoring workflow easier to run while preserving the v0.1 proof-pack boundary.

## Required Outcomes

v0.2 should satisfy:

- Local authoring workflow is easier to run.
- Existing proof-pack guarantees are preserved.
- All writes remain explicit-path and non-production.
- Source/runtime changes are tested if implementation proceeds.
- No production claims are introduced.
- v0.1 proof-pack boundary remains intact.

## Write Safety Criteria

Any implementation must prove:

- No default production writes.
- No writes under repo `data/`.
- No default production canonical ledger writes.
- Optional ledger writes use explicit configured paths only.
- Output directories are caller-selected and test-covered.

## Governance Criteria

Any implementation must preserve:

- Evidence-bearing claim requirements.
- Review status propagation.
- Unresolved tension handling.
- Output status preservation.
- Self-certification blocking.
- Clear distinction between local output and production artifact.

## Verification Criteria

Before v0.2 release prep:

- Existing v0.1 proof-pack tests still pass or are intentionally superseded by documented v0.2 tests.
- New source/runtime behavior has focused tests.
- Demo/local workflow runs into temp or explicit output directories.
- Production JSONL fingerprint remains unchanged during tests.
- `data/` remains quarantined unless a future phase explicitly changes policy.
- Claims docs match evidence.

## Release Criteria

v0.2 release prep may proceed only if the release claim stays local and non-production.

Allowed release shape:

```text
v0.2-local-authoring-surface provides a controlled local authoring surface over covered proof-pack paths.
```

Not allowed:

```text
v0.2 is a production Governed Authoring app.
```

## Failure Conditions

v0.2 should not proceed to release if:

- It writes to production ledgers by default.
- It writes authoring artifacts into production paths.
- It claims production readiness.
- It claims repo-wide governance.
- It claims complete IBVM proof.
- It allows generated outputs to self-certify.
- It blurs local draft output with promoted state.
