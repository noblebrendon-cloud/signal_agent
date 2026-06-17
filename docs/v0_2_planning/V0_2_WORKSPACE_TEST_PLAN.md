# v0.2 Workspace Test Plan

Version target:

```text
v0.2-local-authoring-surface
```

## Purpose

This test plan defines tests that a future workspace-aware command-router implementation must pass. It is documentation/spec only.

## Workspace Path Tests

Future tests must prove:

- Accepts caller-selected temp workspace.
- Rejects repo `data/` as workspace.
- Rejects production ledger paths.
- Rejects parent traversal outside workspace.
- Rejects ambiguous workspace paths.
- Rejects implicit output directories.

## Output Placement Tests

Future tests must prove:

- Writes result JSON only under `workspace/results/`.
- Writes proof summary only under `workspace/summaries/`.
- Writes optional ledger only under `workspace/ledgers/`.
- Writes validation reports only under `workspace/validation/`.
- Writes draft outputs only under `workspace/drafts/`.
- Writes metadata only under `workspace/metadata/`.

## Ledger Tests

Future tests must prove:

- Does not write ledger by default.
- Writes optional ledger only when explicit.
- Rejects ledger path under repo `data/`.
- Skips ledger write on validation failure.

## Preservation Tests

Future tests must prove:

- Evidence refs survive.
- Unresolved tensions survive.
- Review status survives.
- Output status survives.
- Local reviewer marker survives when provided.
- Self-certification is rejected.

## Production Safety Tests

Future tests must prove:

- Production JSONL fingerprint unchanged.
- No server/network behavior introduced.
- No browser-backend submission introduced.
- No production authoring artifact writes.
- No default production canonical ledger writes.

## Draft Boundary Tests

Future tests must prove:

- Drafts are written only under `workspace/drafts/`.
- Drafts are marked local/provisional.
- Drafts are not treated as approved publications.
- Drafts are not canonical state transitions.

## Error Tests

Future tests must prove:

- Missing workspace path fails.
- Forbidden workspace path fails.
- Existing output files are not overwritten by default.
- Invalid input writes no ledger.
- Unsupported packet shape writes no result packet.

## Regression Tests

Future implementation should run existing v0.1 proof-pack tests plus new workspace tests.

## Recommended Phase 24

Phase 24 should be:

```text
Explicit output directory policy.
```

It should turn workspace/path rules into a precise output directory policy and test matrix before runtime implementation.
