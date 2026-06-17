# v0.2 Risk Register

Version target:

```text
v0.2-local-authoring-surface
```

## Summary

v0.2 moves toward a controlled local authoring surface. The main risk is claim inflation: a local surface can easily be mistaken for a production app, backend-wired UI, or repo-wide governance system.

## Architecture Options

| Option | Proof value | Risks | Boundary risk |
| --- | --- | --- | --- |
| Keep CLI-only | Lowest runtime risk; reuses v0.1 proof paths | Less ergonomic; still manual | Low |
| Local server surface | Better workflow; can support local UI experiments | Could be mistaken for production backend | High |
| Static UI plus manual import/export | Preserves current boundary; no server | Still manual; limited interactivity | Low to medium |
| Desktop/local app later | Strong local UX without hosted claims | Larger surface area; packaging complexity | Medium to high |

## Risk Register

| Risk | Description | Mitigation |
| --- | --- | --- |
| Production-readiness confusion | Local surface may be described as production app | Require release language review |
| Backend-wired UI claim | Browser submission may imply production backend | Require Phase 25 decision gate |
| Production write leakage | Outputs could land in `data/` or production paths | Explicit output directory policy |
| Default ledger writes | Canonical ledger writes could become implicit | Explicit `--ledger` or configured path only |
| Self-certification | Generated content could approve itself | Require evidence, review status, and authority gate |
| Human authority ambiguity | Local review may be mistaken for real authority source | Define local authority representation |
| Artifact-store confusion | Draft outputs may be treated as production artifacts | Keep outputs local and explicitly provisional |
| Repo-wide claim inflation | Covered path proof may be overstated | Keep proof matrix/path list updated |
| IBVM overclaim | v0.2 may be framed as complete proof | State complete IBVM remains out of scope |

## Safety Gates Before Implementation

Before runtime work, v0.2 must decide:

- Where outputs may be written.
- Whether a local server is allowed.
- Whether browser-backend submission is allowed.
- How human authority is represented.
- Whether canonical ledger writes are allowed, and only where.
- Whether generated outputs can become artifacts.
- How to block self-certification.

## Required Pre-Implementation Answers

1. What exact paths are allowed for output?
2. What paths are forbidden?
3. Is the surface CLI-only, static exchange, local server, or desktop-local?
4. What is the local authority model?
5. Is ledger writing disabled by default?
6. Are generated outputs provisional unless reviewed?
7. What tests prove no production writes occur?

## Residual Risk

Even with v0.2 planning complete, production readiness remains unproven. v0.2 should be treated as local workflow improvement over v0.1 proof surfaces, not as a production launch path.
