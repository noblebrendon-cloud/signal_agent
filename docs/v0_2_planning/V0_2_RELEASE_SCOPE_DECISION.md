# v0.2 Release Scope Decision

Version target:

```text
v0.2-local-authoring-surface
```

## Decision

Recommended route:

```text
Create a clean v0.2-only release branch excluding unrelated Letters work.
```

Do not tag latest `main` as the v0.2 release unless the release is intentionally described as a broader repository checkpoint.

## History Inspected

Recent `main` history:

```text
ee9fa17 Add v0.2 final verification report
a59140a feat: publish Letters of Light to YouTube
adcb3aa Document v0.2 CLI integration status
d6c214f Add v0.2 command router CLI integration
922e34d Document v0.2 command router verification decision
041caf9 Document v0.2 command router foundation status
a4f3e74 Add v0.2 local command router foundation
```

The unrelated Letters commit is in current `main` ancestry:

```text
a59140a feat: publish Letters of Light to YouTube
```

Files touched by that commit include:

- `app/letters_of_light/cli.py`
- `app/letters_of_light/publishers/base.py`
- `app/letters_of_light/publishers/youtube.py`
- `app/letters_of_light/release_server.py`
- `environment/requirements.lock`
- `tests/test_letters_of_light_cli_boundary.py`
- `tests/test_release_youtube.py`

## Why Latest Main Is Not Ideal For v0.2

Tagging latest `main` would make the v0.2 tag a repository checkpoint that includes concurrent Letters work in its ancestry.

That would not invalidate the v0.2 verification docs, but it would make the tag composition broader than the safe v0.2 claim:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

The Letters commit is unrelated to that claim and should not be silently included in a narrowly scoped v0.2 release artifact.

## Recommended Route

Use a clean v0.2-only release branch.

The clean branch should include:

- v0.2 command-router foundation.
- v0.2 CLI integration.
- v0.2 status and verification docs.
- v0.2 release-scope/tag-prep docs.

The clean branch should exclude:

- `a59140a feat: publish Letters of Light to YouTube`.
- Any unrelated dirty or quarantined workspace files.
- Repo `data/` changes.

## Future Commands To Consider

Do not run these commands during this planning phase.

After the release-scope decision is committed and pushed, a clean release branch could be prepared with a sequence like:

```bash
git switch -c release/v0.2-local-authoring-surface adcb3aa
git cherry-pick ee9fa17
git cherry-pick <phase-32-release-prep-commit>
git tag -a v0.2-local-authoring-surface -m "Verified local CLI authoring surface for covered Governed Authoring proof paths."
git push origin release/v0.2-local-authoring-surface
git push origin v0.2-local-authoring-surface
```

Before using this sequence, verify that `adcb3aa` is still the intended clean base after Phase 30 and that the Phase 32 release-prep commit applies cleanly.

## Alternative Route

If the project intentionally wants a repository checkpoint, tag latest `main` instead.

That route must disclose:

```text
This v0.2 tag is a repository checkpoint and includes concurrent Letters of Light work in history.
```

Recommended only if the release goal is repository-state capture, not a narrow v0.2-only artifact.

## Final Recommendation

Use the clean v0.2-only release branch route.

This keeps the tag composition aligned with the v0.2 safe claim and avoids implying that the Letters work is part of the local authoring surface proof.
