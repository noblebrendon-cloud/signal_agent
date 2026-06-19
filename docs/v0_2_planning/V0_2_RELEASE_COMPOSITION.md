# v0.2 Release Composition

Version target:

```text
v0.2-local-authoring-surface
```

## Intended Composition

The v0.2 release should describe the local authoring surface workstream only.

It should include:

- v0.1 proof-pack ancestry.
- v0.2 planning and boundary docs.
- Local command-router foundation.
- Command-router CLI integration.
- Final v0.2 verification docs.
- v0.2 release-scope and tag-prep docs.

It should not silently include unrelated feature work.

## v0.2 Commit Chain Of Interest

Key v0.2 commits:

```text
a4f3e74 Add v0.2 local command router foundation
041caf9 Document v0.2 command router foundation status
922e34d Document v0.2 command router verification decision
d6c214f Add v0.2 command router CLI integration
adcb3aa Document v0.2 CLI integration status
ee9fa17 Add v0.2 final verification report
```

Phase 32 release-prep docs should become the next v0.2 commit of interest.

## Concurrent Work In Main

Current `main` contains an unrelated Letters commit between Phase 30 and Phase 31:

```text
a59140a feat: publish Letters of Light to YouTube
```

This commit is not part of the v0.2 local authoring surface proof claim.

## Tagging Latest Main

Tagging latest `main` would create a repository checkpoint.

That checkpoint would include:

- v0.2 local authoring surface proof work.
- Concurrent Letters work.
- Any other commits already in latest `main`.

If this route is chosen, the release note must say:

```text
This tag is a repository checkpoint and includes concurrent Letters work in history.
```

## Clean v0.2-Only Branch

A clean v0.2-only release branch should be based from the last v0.2 commit before the unrelated Letters commit:

```text
adcb3aa Document v0.2 CLI integration status
```

Then cherry-pick the v0.2 verification and release-prep docs:

```text
ee9fa17 Add v0.2 final verification report
<phase-32-release-prep-commit>
```

This creates a tag target whose ancestry matches the v0.2 local authoring surface release claim.

## Recommended Composition

Use the clean v0.2-only release branch composition.

This keeps the release artifact scoped to:

- Local CLI authoring surface.
- Covered Governed Authoring proof paths.
- Explicit workspaces.
- Fail-closed path validation.
- Non-production boundary.

It avoids implying that unrelated Letters release work is part of v0.2 local authoring surface verification.
