# Release Archive Plan

Generated: 2026-05-22
Status: active closeout plan
Scope: commit slicing, GitHub release grouping, and Zenodo archive admission
Behavior changed: no

## Purpose

This plan defines how open endpoint work becomes a verified commit, a GitHub release, and, only when warranted, a stable Zenodo archive.

Use it with `docs/operator/MASTER_ENDPOINT_REGISTER.md`:

- The endpoint register says what remains open and what closes it.
- This plan says which release level an endpoint can enter after it closes.

## Release Levels

| Level | Purpose | Admission floor | Example |
|---|---|---|---|
| Commit | Small verified repo change | Narrow diff, allowed paths, exclusions, targeted verification | Reflective Pressure review gate slice |
| GitHub Release | Coherent public milestone | Pushed commit set, tag, release notes, bounded claims | `v0.2.0-reflective-pressure-spine` |
| Zenodo Archive | Stable citable research/software artifact | Released tag, documentation, leakage review, archive record | Reflective Pressure Spine v0.2 |

Not every commit is release-worthy. Not every release is archive-worthy. Zenodo should contain stable milestone artifacts, not half-related worktree snapshots.

## Commit Gate

A commit slice may proceed only when all of these are true:

1. The endpoint has a bounded file set.
2. Private, generated, runtime-state, and scratch exclusions are named.
3. The exact diff has been reviewed before staging.
4. The staging command names only allowed paths.
5. Targeted verification passes or the commit explicitly records why a non-code slice did not require runtime tests.
6. Remaining dirty work stays unstaged.

Commit records should preserve:

| Field | Meaning |
|---|---|
| Commit name | Imperative message for the bounded outcome. |
| Files allowed | Exact files or path patterns admitted into staging. |
| Files excluded | Private, generated, runtime, scratch, and unrelated paths blocked from staging. |
| Verification | Targeted command and observed result. |
| Release relevance | Whether it belongs in a future GitHub release. |
| Archive relevance | Whether it can contribute to a future Zenodo milestone. |

## GitHub Release Gate

A GitHub release may proceed only when:

- Included commits are pushed and form one coherent public claim.
- A tag names the milestone.
- Release notes state implemented scope, verification evidence, explicit non-claims, and known boundaries.
- The release bundle excludes raw/private/generated leakage unless exact publishable artifacts were approved.
- The endpoint register points from closed commit slices to the release grouping.

GitHub releases should group commit slices by subsystem meaning, not by the order files happened to be found in the dirty tree.

## Zenodo Archive Gate

A slice is Zenodo-worthy only when it is:

- committed
- pushed
- tagged
- documented
- verified
- release-noted
- stable enough to cite
- free of private, raw, and generated-data leakage

Archive records should follow the bounded precedent in `docs/system_coherence/ARCHIVE_RECORD.md`: identifiers, archived scope, test evidence, explicit non-claims, and related docs.

## Never Archive Raw

These are not Zenodo candidates by default:

- raw Reddit export data
- blank or unapproved review batches
- private archives
- runtime ledgers
- local generated JSONL state
- locks, caches, probe workspaces, and scratch outputs
- half-finished dirty worktree snapshots

An archive may include reviewed public derivatives only when provenance, privacy, and release scope are documented.

## Finish Order

### Phase 0: Freeze And Triage

No broad feature work should enter the release pipeline before this phase is closed.

Required outputs:

- dirty worktree classification
- ahead commit review
- private Reddit export disposition boundary
- generated/runtime-state exclusion inventory
- `.gitignore` or `.gitattributes` hygiene proposal if the current tree proves one is needed

Closure condition:

```text
Every dirty file is classified as:
source / test / docs / config / generated / private / runtime-state / scratch / unknown
```

### Phase 1: Near-Ready Commit Slices

| Order | Candidate commit | Primary boundary | Gate |
|---|---|---|---|
| 1 | `add reflective pressure corpus review gate and reddit seed tooling` | Reflective Pressure source/docs/tests/tooling | Proceed only after raw Reddit data, external derived data, and local state are excluded. |
| 2 | `add HQ governance closure evidence` | HQ closure evidence | Final diff review and targeted closure verification required. |
| 3 | `add shared lifecycle and reconcile primitives` | Shared lifecycle/reconcile prerequisites | Must land before dependent antiglue/governance evidence. |
| 4 | `add governance antiglue evidence` | Governance evidence | May proceed only after lifecycle/reconcile prerequisite closes. |

#### Slice 001: Reflective Pressure

Allowed paths for the first execution review:

- `app/reflective_pressure/*.py`
- `tests/test_reflective_pressure_models_store.py`
- `tests/test_reflective_pressure_flow.py`
- `tests/test_reflective_pressure_cli.py`
- `tests/test_reflective_pressure_corpus.py`
- `tests/test_reddit_archive_to_pressure_seeds.py`
- `tests/test_reflective_pressure_review_batch.py`
- `tools/datasets/reddit_archive_to_pressure_seeds.py`
- `tools/datasets/reflective_pressure_review_batch.py`
- `docs/operator/reflective_pressure_spine_guide.md`
- `docs/operator/reflective_pressure_spine_architecture.md`
- `docs/operator/reflective_pressure_spine_checkpoint.md`
- `docs/operator/reflective_pressure_corpus_review_checkpoint.md`
- `data/state/module_artifacts.jsonl` only when the diff contains only intended reviewed Reflective Pressure metadata rows

Forbidden paths for that slice:

- `data/reddit/**`
- `E:\datasets\reddit\derived/**`
- `data/state/reflective_pressure_*.jsonl`
- `data/state/reflective_pressure_*.lock`
- runtime ledgers
- generated outputs
- unrelated dirty files
- private archive data

Targeted verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_reflective_pressure_review_batch.py tests\test_reddit_archive_to_pressure_seeds.py tests\test_reflective_pressure_models_store.py tests\test_reflective_pressure_flow.py tests\test_reflective_pressure_cli.py tests\test_reflective_pressure_corpus.py -q
```

First safe execution step after triage:

```text
Review the exact allowed-file diff for Slice 001 and confirm the staged set excludes all forbidden paths.
```

Slice 001 commit-level closure:

| Commit | Verification | Milestone role | Current release/archive state |
|---|---|---|---|
| `40d6af5` `Add reflective pressure corpus review gate and reddit seed tooling` | Focused Slice 001 command passed with `52 passed in 25.26s`; staged forbidden-path gate found `0` forbidden paths. | Candidate component for a future Reflective Pressure milestone release. | Not pushed, not tagged, not GitHub-released, and not Zenodo-archived. |

Future release or archive admission still requires milestone grouping, push, tag, bounded release notes, leakage review, and the rest of the GitHub and Zenodo gates above.

#### Slice 002: HQ Closure Evidence

Slice 002 commit-level closure:

| Commit | Verification | Milestone role | Current release/archive state |
|---|---|---|---|
| `b75b0c9` `Add HQ governance closure evidence` | `.\.venv\Scripts\python.exe -m pytest tests\test_casts_closure.py -q` passed with `10 passed in 4.56s`; dependency gate passed against tracked clean implementation files; staged gate contained exactly `tests/test_casts_closure.py` and `git diff --cached --check` was clean. | Candidate component for a future governance closure evidence milestone release. | Not pushed, not tagged, not GitHub-released, and not Zenodo-archived. |

Future release or archive admission still requires milestone grouping, push, tag, bounded release notes, leakage review, and the rest of the GitHub and Zenodo gates above.

#### Slice 003: Lifecycle/Reconcile Prerequisite

Slice 003 commit-level closure:

| Commit | Verification | Milestone role | Current release/archive state |
|---|---|---|---|
| `86ad731` `Add shared lifecycle and reconcile primitives` | `.\.venv\Scripts\python.exe -B -m py_compile shared\lifecycle.py shared\reconcile.py` passed; focused pytest command passed with `5 passed in 1.22s`; staged gate contained exactly `shared/lifecycle.py` and `shared/reconcile.py`; forbidden staged path count was `0`. | Candidate component for a future governance closure evidence milestone release. | Not pushed, not tagged, not GitHub-released, and not Zenodo-archived. |

Future release or archive admission still requires milestone grouping, push, tag, bounded release notes, leakage review, and the rest of the GitHub and Zenodo gates above.

### Phase 2: Larger Subsystem Slices

| Slice | Current status | Release action |
|---|---|---|
| Operator/security | Deferred | Isolate operator files, operator config, and security tests before staging. |
| Retention/appointments | Partial | Audit appointment lifecycle work as its own retention subsystem. |
| Laviathon/site | Dirty | Split public website/demo changes from generated output and legacy mirrors. |
| Letters of Light | Dirty | Split render logic and tests from produced content artifacts. |
| Bookgen | Dirty | Isolate CLI, render, templates, and tests from generated book outputs. |
| Clock/runtime audit/task contract | Dirty | Verify dependency coupling before splitting governance behavior. |

### Phase 3: Release Grouping

These are candidate release groupings. Final tags must be chosen from the committed, pushed diff and bounded release notes.

| Candidate tag | Intended contents | GitHub release | Zenodo candidate |
|---|---|---|---|
| `v0.2.0-reflective-pressure-spine` | Reflective Pressure module, Reddit seed tooling, review gate docs/tests | Yes | Yes, after stable corpus/privacy boundary review |
| `v0.3.0-governance-closure-evidence` | HQ closure, lifecycle/reconcile, antiglue/governance evidence | Yes | Yes |
| `v0.4.0-operator-security-boundary` | Operator/security boundary work | Yes | Yes |
| `v0.5.0-retention-appointments-spine` | Retention appointment lifecycle work | Yes | Yes |
| `v0.6.0-public-surface-orchestration-readiness` | Public-surface registry promotion/readiness work | Yes | Yes if claims and public artifacts are stable |

## Release Artifact Checklist

For a GitHub release, prepare or confirm:

- bounded release notes
- tag and tag target
- commit set and verification summary
- explicit non-claims
- leak review for private/raw/generated paths
- endpoint register update

For a Zenodo archive, also prepare or confirm:

- stable citation/version metadata
- archive record path in the repo
- DOI or record identifier after publication
- archived scope and test evidence
- related docs that bound the claim

## Current Release Precedent

The Stage 1 System Coherence and Local Spine Observability milestone already shows the intended chain:

- release notes in `docs/system_coherence/RELEASE_NOTES_v0.1.0.md`
- archive record in `docs/system_coherence/ARCHIVE_RECORD.md`
- bounded claims and explicit non-claims in both documents

Future closeout milestones should follow that shape while staying scoped to their own subsystem evidence.

## Coordination Rule

The endpoint register owns status. This plan owns release admission.

When a slice changes status:

1. Update its endpoint row.
2. Record the commit or blocker.
3. Decide whether it enters a future GitHub release candidate.
4. Decide whether it can ever enter a Zenodo archive candidate.
