# v0.2 Surface Options Comparison

Version target:

```text
v0.2-local-authoring-surface
```

## Comparison Matrix

| Option | Proof value | Implementation complexity | Boundary risk | Write safety risk | UI/backend confusion risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| CLI-only continuation | Preserves v0.1 proof path and keeps commands simple. | Low | Low | Low | Low | Keep as fallback. |
| Static UI plus manual import/export | Preserves static packet exchange and avoids server behavior. | Low to medium | Low to medium | Low | Low | Keep available, but do not make it primary. |
| Local command router | Creates a more coherent local workflow over existing proof paths. | Medium | Medium | Medium | Low to medium | Recommended first v0.2 architecture. |
| Local server surface | Enables smoother local UI workflows later. | Medium to high | High | High | High | Defer. |
| Desktop/local app later | Could provide a contained local app surface. | High | Medium to high | Medium | Medium | Defer. |

## Option: CLI-Only Continuation

Proof value:

- Directly reuses the offline CLI and demo proof bundle.
- Maintains the v0.1 verification boundary.

Risks:

- Does not substantially improve workflow.
- May leave users stitching commands together manually.

Recommendation:

- Keep as a safe fallback.

## Option: Static UI Plus Manual Import/Export

Proof value:

- Retains static export/import packet compatibility.
- Avoids browser-backend submission.

Risks:

- Manual workflow remains easy to misuse.
- User may assume imported results came from a live backend.

Recommendation:

- Keep as a non-server bridge, not the main v0.2 target.

## Option: Local Command Router

Proof value:

- Wraps existing proof-pack paths behind a deliberate local interface.
- Can standardize inputs, outputs, proof summaries, and optional ledger behavior.
- Can test forbidden paths before any server is introduced.

Risks:

- Needs strong output path rules.
- Needs clear local authority representation.
- Must not imply production app behavior.

Recommendation:

- Use this as the recommended v0.2 architecture.

## Option: Local Server Surface

Proof value:

- Could eventually support a local browser-based workflow.

Risks:

- High risk of backend-wired UI claim inflation.
- Higher risk of implicit writes.
- Requires stronger authority and path controls.

Recommendation:

- Defer until after the command-router contract and write policy are proven.

## Option: Desktop/Local App Later

Proof value:

- Could create a controlled local workflow with less public-hosting ambiguity.

Risks:

- Larger packaging and support surface.
- Still needs careful write and authority boundaries.

Recommendation:

- Defer until the local command-router surface is proven useful.

## Preferred Path

The preferred v0.2 path is:

```text
local command-router design
-> explicit workspace/write contract
-> tests for forbidden paths
-> optional runtime implementation only after approval
```
