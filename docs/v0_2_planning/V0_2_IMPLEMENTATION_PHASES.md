# v0.2 Implementation Phases

Version target:

```text
v0.2-local-authoring-surface
```

This file proposes a bounded phase sequence. Phase 20 is planning only. Later runtime phases require explicit approval.

## Phase Sequence

| Phase | Name | Deliverable | Commit mode |
| --- | --- | --- | --- |
| Phase 20 | v0.2 planning package | Planning docs | Documentation only |
| Phase 21 | Local authoring surface architecture spec | Architecture decision record | Documentation only |
| Phase 22 | Local-only command router/design | Command contract and routing design | Documentation/spec first |
| Phase 23 | Local file workspace contract | Input/output path contract | Documentation/schema planning |
| Phase 24 | Explicit output directory policy | Write policy and test plan | Documentation/policy |
| Phase 25 | Local UI/server decision gate | Decision: CLI-only, static exchange, or local server | Documentation/checkpoint |
| Phase 26 | Minimal local server prototype, only if approved | Local-only prototype | Runtime, explicit approval required |
| Phase 27 | Docs/status update | Updated claims boundary | Documentation |
| Phase 28 | v0.2 verification report | Test/demo results and boundaries | Verification/documentation |
| Phase 29 | v0.2 release note/tag prep | Release note and tag plan | Documentation only |

## Phase 21: Architecture Spec

Purpose:

- Define whether v0.2 remains CLI-only or allows a local server prototype later.
- Identify local surface shape.
- Define proof value and boundary risk.

Must not:

- Add server code.
- Wire browser UI to backend.
- Modify runtime.

## Phase 22: Local Command Router Design

Purpose:

- Design a local command router that can call existing offline proof paths.
- Keep all outputs explicit-path.
- Avoid production data paths.

Must decide:

- Command names.
- Inputs.
- Output directory behavior.
- Error handling for forbidden paths.

## Phase 23: Local File Workspace Contract

Purpose:

- Define allowed local workspace layout.
- Separate source packets, result packets, proof summaries, optional ledgers, and draft outputs.

Must specify:

- Inputs are explicit files.
- Outputs go only to caller-selected directories.
- `data/` is forbidden unless a future phase explicitly changes policy.

## Phase 24: Explicit Output Directory Policy

Purpose:

- Make write boundaries testable before runtime expansion.

Required policy:

- No default production writes.
- No default canonical ledger writes.
- No writes under repo `data/`.
- No overwrite without explicit policy.

## Phase 25: Local UI/Server Decision Gate

Purpose:

- Decide whether to continue CLI-only, use static import/export, or permit a minimal local server.

Required questions:

- Is a local server allowed?
- Is browser-backend submission allowed?
- Is local-only authentication needed?
- How is human authority represented?
- Where can ledgers be written?

## Phase 26: Minimal Local Server Prototype

Only if explicitly approved.

Must remain:

- Local-only.
- Non-production.
- Explicit-path.
- No default production ledger writes.
- No repo-wide governance claim.

## Phase 27-29: Verification And Release Prep

Purpose:

- Update status docs.
- Run v0.2 verification.
- Prepare release note/tag only after evidence exists.

No production claim should be made unless a later proof pack supports it.
