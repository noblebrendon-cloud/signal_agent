# v0.2 Runtime Implementation Gate

Version target:

```text
v0.2-local-authoring-surface
```

## Gate Purpose

This gate lists decisions that must be answered before implementing output directory or command-router write behavior.

It is documentation/spec only. It does not add server code, runtime path classification, browser-backend submission, production authoring writes, production ledger writes, or default canonical ledger writes.

## Required Gate Decision

No Phase 24 runtime behavior is approved.

Before implementation, the project must explicitly decide which local command-router behavior is allowed and where outputs may be written.

## Path Classification Questions

The next implementation plan must answer:

- What exact path-classification function will be implemented?
- What input fields does the classifier require?
- What structured result does the classifier return?
- Which classifications allow writes?
- Which classifications allow appends?
- How are ambiguous or unknown paths represented?
- How does the caller see a denied path error?

## Repo Root and Forbidden Path Questions

The next implementation plan must answer:

- What repo root is used for forbidden `data/` detection?
- How is the repo `data/` path resolved?
- Which production ledger paths are forbidden?
- Which production authoring artifact paths are forbidden?
- What test proves a normalized path under repo `data/` is denied?
- What test proves production JSONL fingerprint stays unchanged?

## Workspace Questions

The next implementation plan must answer:

- How is the caller-selected workspace provided?
- Is the workspace required to exist before command execution?
- May the runtime create workspace subdirectories?
- Which subdirectories are allowed for each output type?
- How does the runtime reject parent traversal outside the workspace?

## Output Location Questions

The next implementation plan must answer:

- Where are result packets written?
- Where are summaries written?
- Where are validation reports written?
- Where are metadata records written?
- Where are drafts written?
- Where are optional ledgers written?
- Are temp output directories allowed for every command or only selected commands?

## Overwrite Questions

The next implementation plan must answer:

- What overwrite behavior is allowed?
- Is overwrite disabled entirely for v0.2?
- If an overwrite flag is permitted later, what exact flag name is used?
- What file types may be overwritten, if any?
- What file types are never overwritten?
- How is overwrite behavior recorded in run metadata?

## Symlink and Ambiguity Questions

The next implementation plan must answer:

- Are symlinks allowed or rejected?
- If symlinks are allowed, how are resolved paths compared with forbidden paths?
- What counts as symlink-like ambiguity where detectable?
- What platform-specific path behavior must be covered on Windows?
- What platform-specific path behavior must be covered on POSIX?

## Ledger Questions

The next implementation plan must answer:

- Are canonical ledger writes allowed in the first runtime phase?
- If allowed, are they explicit path only?
- Must ledger paths live under workspace `ledgers/`?
- Are temp ledger paths allowed?
- What proves no default ledger write occurs?
- What proves production ledger paths are denied?
- What proves repo `data/` paths are denied?

## Human Authority Questions

The next implementation plan must answer:

- How is local human authority represented?
- Is the local reviewer marker required for all commands or only approval-like commands?
- How is self-certification blocked?
- How does generated output avoid becoming its own approval authority?
- How are unresolved tensions preserved in output packets?

## Local UI and Server Questions

The next implementation plan must answer:

- Does v0.2 remain CLI/router-only?
- Is any local server allowed later?
- Is browser-backend submission allowed later?
- If local server work is allowed, what prevents production claims?
- What extra verification would be required before adding server code?

## Required Pre-Implementation Evidence

Before runtime implementation, the project should have:

- Output directory policy.
- Path classification policy.
- Overwrite policy.
- Output policy test matrix.
- Local UI/server decision gate.
- Explicit decision on whether v0.2 remains CLI/router-only.

## Recommended Phase 25

Phase 25 should be:

```text
Local UI/server decision gate.
```

It should decide whether v0.2 remains CLI/router-only or permits any local server/browser submission work later.

Phase 25 must not add server code by itself.

## Non-Goals

This gate does not approve:

- Production app readiness.
- Hosted app behavior.
- Browser-backend submission.
- Production authoring artifact writes.
- Default production canonical ledger writes.
- Repo-wide governance.
- Complete IBVM proof.
