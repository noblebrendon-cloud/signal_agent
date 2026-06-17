# v0.2 Workstream Plan

Version target:

```text
v0.2-local-authoring-surface
```

## v0.1 Baseline

The v0.1 release is complete:

- Commit: `bb1d349 Add local proof-pack release note and tag prep`
- Tag: `v0.1-local-proof-pack`
- GitHub prerelease: `https://github.com/noblebrendon-cloud/signal_agent/releases/tag/v0.1-local-proof-pack`

Safe v0.1 public claim:

```text
v0.1-local-proof-pack verifies a local proof pack for formal governance and covered Governed Authoring paths.
```

Hard v0.1 boundary:

```text
Not a production Governed Authoring app.
Not a backend-wired UI.
Not repo-wide governance.
Not complete IBVM proof.
```

## v0.2 Goal

v0.2 should move from:

```text
local proof pack
-> controlled local authoring surface
```

The goal is a local controlled authoring surface that can use the already-proven offline harness, CLI, and demo proof-bundle paths through a deliberate local interface.

The surface must remain:

- Local.
- Non-production.
- Explicit-path only.
- No default production writes.
- No repo-wide governance claim.
- No complete IBVM claim.

## Non-Goals

v0.2 does not aim to prove:

- Production app readiness.
- Public hosted app.
- Backend-wired production UI.
- Production artifact store.
- Default production canonical ledgers.
- Repo-wide governance.
- All state mutations gated.
- Complete IBVM proof.

## Workstream Principle

v0.2 should preserve the v0.1 proof-pack boundary while making the covered local authoring workflow easier to run, inspect, and repeat.

Any implementation phase must make write paths explicit before code changes begin.

## Candidate Phase Sequence

| Phase | Purpose | Mode |
| --- | --- | --- |
| Phase 20 | v0.2 planning package | Documentation only |
| Phase 21 | Local authoring surface architecture spec | Documentation only |
| Phase 22 | Local-only command router/design | Design before runtime |
| Phase 23 | Local file workspace contract | Documentation/schema planning |
| Phase 24 | Explicit output directory policy | Policy and tests plan |
| Phase 25 | Local UI/server decision gate | Decision checkpoint |
| Phase 26 | Minimal local server prototype, only if approved | Runtime, local-only |
| Phase 27 | Docs/status update | Documentation |
| Phase 28 | v0.2 verification report | Verification/documentation |
| Phase 29 | v0.2 release note/tag prep | Documentation only |

## Recommended Next Step

The next implementation-adjacent step should be Phase 21:

```text
Local authoring surface architecture spec.
```

It should decide whether v0.2 stays CLI-only or permits a local server prototype later. It should not add runtime behavior by itself.
