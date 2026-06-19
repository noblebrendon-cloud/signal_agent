# v0.2 Release Repair Options

Target branch:

```text
release/v0.2-local-authoring-surface at 322455d
```

## Required Recommendation

Do not tag v0.2 until the committed test suite is source-control complete on a clean checkout.

## Option A - Source-Control Repair First

Description:

```text
Create a separate audited commit that adds only the required operator runtime source files, plus any necessary focused tests/docs, then rebuild the clean v0.2 release branch with that repair included.
```

Candidate files for repair:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`

Potentially related files must be reviewed separately and added only if the focused tests prove they are required.

Correctness:

```text
High.
```

This repairs the actual source-control gap: committed runtime/test files import modules that are not committed.

Release integrity:

```text
High.
```

A clean checkout would be able to collect and run the committed verification suite without relying on local untracked files.

Scope risk:

```text
Moderate.
```

The untracked modules are real runtime source and should be reviewed before committing. The repair must stay narrow and must not sweep unrelated operator files, `data/`, or dirty workspace changes.

Recommendation:

```text
Recommended.
```

## Option B - Exclude Operator Tests

Description:

```text
Remove, skip, or omit tests/test_operator_canonical_ledger_adapter.py from the v0.2 release verification.
```

Correctness:

```text
Low unless a separate audit proves the operator canonical ledger test is obsolete or unrelated.
```

The test is part of the advertised proof chain and Phase 31 verification suite.

Release integrity:

```text
Low.
```

Excluding the test would make the release pass by narrowing the proof surface after the blocker was discovered.

Scope risk:

```text
High.
```

This risks weakening the proof claim and obscuring source-control incompleteness.

Recommendation:

```text
Not recommended.
```

Only consider this if a future audit proves the operator adapter surface is no longer supported or should be explicitly removed from the release claim.

## Option C - Depend On Untracked Local Files

Description:

```text
Let the release branch or verification environment depend on the dirty main worktree's untracked operator files.
```

Correctness:

```text
Unacceptable.
```

Tagged releases must be reproducible from committed source.

Release integrity:

```text
Unacceptable.
```

The release would depend on local files that are not present in a clean checkout.

Scope risk:

```text
Very high.
```

This creates a non-reproducible release and hides the source-control gap.

Recommendation:

```text
Reject.
```

## Recommended Repair Sequence

Recommended next sequence:

1. Audit the untracked operator source files in main.
2. Create a narrowly scoped source-control repair commit that adds only required operator runtime source.
3. Run focused operator tests on that repair.
4. Rebuild the clean v0.2 release branch with the repair included.
5. Re-run the full Phase 31 verification suite on the clean branch.
6. Re-run the real CLI-router temp-workspace exercise.
7. Confirm the clean-branch JSONL fingerprint is unchanged.
8. Push and tag only after the full clean-branch suite passes.

## Current Release Status

The release branch remains blocked.

Do not push or tag `release/v0.2-local-authoring-surface` until Option A or another audited source-control-complete repair is completed and verified.
