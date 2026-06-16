# Commit Scope Guide

This guide defines safe commit planning for the proof-pack consolidation layer.

## Intended Phase 17 Files

Phase 17 intended files:

- `docs/proof_pack/RELEASE_PROOF_PACK_INDEX.md`
- `docs/proof_pack/PROOF_CHAIN.md`
- `docs/proof_pack/TEST_COMMANDS.md`
- `docs/proof_pack/DEMO_COMMANDS.md`
- `docs/proof_pack/SAFE_CLAIMS.md`
- `docs/proof_pack/BOUNDARIES_AND_GAPS.md`
- `docs/proof_pack/COMMIT_SCOPE_GUIDE.md`

## Quarantine From Commit Planning

Keep these out of proof-pack commits unless a future prompt explicitly names them:

- `data/`
- Generated outputs.
- Temporary demo output directories.
- Lock files.
- Processed PDFs or copied intake files.
- Unrelated dirty source files.
- Unrelated untracked tests.
- Static prototype UI files unless the phase explicitly targets them.

## Staging Rule

Do not use broad staging commands for this proof-pack layer.

Avoid:

```bash
git add .
git add docs/
git add data/
git add -A
```

Use exact paths only:

```bash
git add docs/proof_pack/RELEASE_PROOF_PACK_INDEX.md
git add docs/proof_pack/PROOF_CHAIN.md
git add docs/proof_pack/TEST_COMMANDS.md
git add docs/proof_pack/DEMO_COMMANDS.md
git add docs/proof_pack/SAFE_CLAIMS.md
git add docs/proof_pack/BOUNDARIES_AND_GAPS.md
git add docs/proof_pack/COMMIT_SCOPE_GUIDE.md
```

## Pre-Commit Checks

Run:

```bash
git status --short -- docs/proof_pack docs/proof_status docs/governed_authoring data
git diff --check -- docs/proof_pack docs/proof_status docs/governed_authoring
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
```

Because new files may be untracked before staging, also use no-index whitespace checks when needed:

```bash
git diff --no-index --check -- /dev/null docs/proof_pack/RELEASE_PROOF_PACK_INDEX.md
```

## Boundary Statement

A proof-pack commit should say:

```text
This is documentation-only and does not change runtime behavior, production ledgers, server surfaces, or production authoring writes.
```
