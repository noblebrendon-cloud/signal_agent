# v0.2 Tag Preparation

Version target:

```text
v0.2-local-authoring-surface
```

## Recommended Tag

```text
v0.2-local-authoring-surface
```

## Recommended Tag Message

```text
Verified local CLI authoring surface for covered Governed Authoring proof paths.
```

## Recommended Release Route

Use a clean v0.2-only release branch excluding unrelated Letters work.

Reason:

```text
Latest main includes a59140a feat: publish Letters of Light to YouTube.
```

A latest-main tag would be truthful only as a repository checkpoint. A clean release branch better matches the v0.2 safe claim.

## Future Clean-Branch Commands

Do not run these commands during Phase 32 documentation prep.

Potential clean-branch sequence after the release-scope decision is committed:

```bash
git switch -c release/v0.2-local-authoring-surface adcb3aa
git cherry-pick ee9fa17
git cherry-pick <phase-32-release-prep-commit>
git tag -a v0.2-local-authoring-surface -m "Verified local CLI authoring surface for covered Governed Authoring proof paths."
git push origin release/v0.2-local-authoring-surface
git push origin v0.2-local-authoring-surface
```

## Future Repository-Checkpoint Commands

Do not run these commands unless the release is intentionally a repository checkpoint that includes concurrent Letters work.

```bash
git tag -a v0.2-local-authoring-surface -m "Verified local CLI authoring surface for covered Governed Authoring proof paths."
git push origin v0.2-local-authoring-surface
```

## GitHub Prerelease Recommendation

Create a GitHub prerelease, not a production release.

Future command shape:

```bash
gh release create v0.2-local-authoring-surface --title "v0.2-local-authoring-surface" --notes-file docs/v0_2_planning/RELEASE_NOTE_v0.2-local-authoring-surface.md --prerelease
```

Do not run this command until the tag strategy is chosen and the tag exists.

## Required Boundary In Release Body

Include:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

Also include:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.
- Not repo-wide governance.
- Not complete IBVM proof.
