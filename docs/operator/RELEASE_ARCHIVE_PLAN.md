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

#### Slice 004A: Antiglue Governance Evidence

Slice 004A commit-level closure:

| Commit | Verification | Milestone role | Current release/archive state |
|---|---|---|---|
| `993a459` `Add antiglue governance evidence` | `.\.venv\Scripts\python.exe -B -m pytest tests\test_antiglue_phase_next.py -q -p no:cacheprovider` passed with `6 passed in 1.09s`; narrow governance selector passed with `3 passed in 0.32s`; staged gate contained exactly `tests/test_antiglue_phase_next.py`; forbidden staged path count was `0`. | Candidate component for a future governance closure evidence milestone release. | Not pushed, not tagged, not GitHub-released, and not Zenodo-archived. |

The broader governance-unification/support remainder is not release-admitted. `CLOSE-040B` failed closed with no staging and no commit because `tests/test_governance_unification.py` performs repo-wide scanning and the support files reach runtime-state, routing, or checkpoint surfaces. Only already closed governance slices are candidate milestone components.

Future release or archive admission still requires milestone grouping, push, tag, bounded release notes, leakage review, and the rest of the GitHub and Zenodo gates above.

### Phase 2: Larger Subsystem Slices

| Slice | Current status | Release action |
|---|---|---|
| Operator/security | Deferred | Isolate operator files, operator config, and security tests before staging. |
| Retention/appointments | Partial | Audit appointment lifecycle work as its own retention subsystem. |
| Laviathon/site | Dirty | Split public website/demo changes from generated output and legacy mirrors. |
| Letters of Light | Blocked | `a094d66` is not release-admitted as currently committed; split render logic/tests/docs from produced content artifacts, generated outputs, and runtime-state JSONL. |
| Bookgen | Dirty | Isolate CLI, render, templates, and tests from generated book outputs. |
| Clock/runtime audit/task contract | Dirty | Verify dependency coupling before splitting governance behavior. |

### Phase 3: Release Grouping

These are candidate release groupings. Final tags must be chosen from the committed, pushed diff and bounded release notes.

### Current Push / Release Readiness

The push/release-readiness audit after the clean closure chain found that no milestone is currently GitHub-release-ready or Zenodo-ready.

Release readiness is blocked by:

- questionable ahead commit review for `a094d66` `Add Letters of Light weekly layer`
- safe push path decision for `main` or a release branch
- tag target selection
- bounded release notes
- leakage review
- milestone packaging
- Zenodo metadata and archive package, if a milestone later qualifies

The clean closure chain is internally coherent, but it does not by itself justify pushing `main` because earlier ahead commits still need review. Closed commit-level endpoints remain candidate release components only; they are not pushed, tagged, GitHub-released, or Zenodo-archived.

### Letters of Light Release Admission

`a094d66` `Add Letters of Light weekly layer` is not release-admitted as currently committed.

The source/docs/tests portion appears coherent, but the commit also contains generated outputs and runtime-state JSONL. These paths are not admitted to release or archive without an explicit register exception:

- `data/outputs/letters_of_light/**`
- `data/state/letters_of_light_*.jsonl`

Likely future split:

- Letters of Light source/docs/tests slice
- optional admitted content artifact slice for `docs/letters_of_light/letters/2026-05-17.md`
- generated output excluded from source commits or admitted only as bounded release artifacts
- runtime state excluded or converted to fixtures/seeds with an explicit register exception

Until that split or exception exists, all milestone releases remain not ready.

### Public-Surface Readiness Admission

The public-surface push-review audit approved these commits for push once the `a094d66` blocker is resolved or bypassed:

- `c362c10` `Assess public surface governance bridge`
- `b8bb70e` `Add public surface config validator`
- `2a45585` `Add public surface governance report`
- `610fdc4` `Add public surface governance CLI`

The audit found no forbidden paths, no runtime/generated/private paths, and a preserved read-only boundary: example config/JSONL loading, validation, report construction, and JSON/text rendering only. Focused verification passed with `24 passed in 2.95s`.

These commits are candidate components for a future public-surface readiness milestone. They are not pushed, not tagged, not GitHub-released, not Zenodo-archived, and not Zenodo-ready by themselves.

Public-surface release admission still requires:

- push-safe branch state
- tag target selection
- bounded release notes
- leakage review
- milestone packaging

### Social Source Worklist Bridge Admission

`CLOSE-130` `Add social source campaign worklist bridge` is a partial social orchestration slice. It is not part of the current release branch `codex/release-closeout-governance-chain`.

Scope:

- source-memory evaluation documentation
- source-to-campaign worklist architecture documentation
- read-only worklist report builder
- `source-campaign-worklist` CLI wiring
- optional operator console source worklist summary
- focused module and CLI tests

Release status:

- candidate component for a later social orchestration milestone only after it is committed from a self-contained staged set
- not pushed
- not tagged
- not GitHub-release-ready
- not Zenodo-ready
- currently blocked by untracked source-memory base modules outside the reviewed staged set

Archive status:

- not a Zenodo candidate by itself
- could contribute to a future social orchestration milestone only after push, tag, release notes, leakage review, milestone packaging, and archive metadata

Non-admitted behavior:

- campaign creation
- ingestion expansion
- rendering
- approvals
- dry-run preparation
- adapters
- credentials
- scraping
- browser automation
- network activity

### Social Orchestration Dependency Order

The social orchestration/source-memory lane is not part of the current release branch `codex/release-closeout-governance-chain`. No social orchestration slice is currently release-admitted, GitHub-release-ready, or Zenodo-ready.

The read-only dependency map replaced the broad `CLOSE-131` source-memory base candidate with granular prerequisite endpoints. The safe order is:

```text
CLOSE-131A transport schemas/models [closed locally]
-> CLOSE-131B transport ledger primitives [closed locally]
-> CLOSE-131C social models and social ledger shell
-> CLOSE-131D source ingestion and source review base
-> CLOSE-130 source worklist bridge retry
```

Later and separate:

- `CLOSE-131E` review queue / human-gated lifecycle
- `CLOSE-131F` transport orchestration/provider boundary
- campaign creation, approval, dry-run, packet lifecycle, renderers, reconcile, lineage, CLI, and operator console release packaging

CLOSE-131A local commit scope:

- `signal_agent/transport/schemas/models.py`
- `signal_agent/transport/schemas/__init__.py`

CLOSE-131A verification:

- `py_compile` passed for both schema files.
- Scoped whitespace gate passed.
- No orchestrator, provider, adapter, network, credential, ledger, social orchestration, generated-state, or runtime-state dependency was admitted.

CLOSE-131A exclusions:

- `signal_agent/transport/__init__.py`
- `signal_agent/transport/ledgers/**`
- `signal_agent/social_orchestration/**`
- `tests/test_transport_orchestration.py`
- `tests/.probe_workspace/**`

CLOSE-131A handoff: `CLOSE-131B` transport ledger primitives.

CLOSE-131B local commit scope:

- `signal_agent/transport/ledgers/jsonl.py`
- `signal_agent/transport/ledgers/store.py`
- `signal_agent/transport/ledgers/__init__.py`

CLOSE-131B verification:

- `py_compile` passed for all three ledger files.
- Scoped whitespace gate passed.
- Focused test discovery found no ledger-only test file.
- `tests/test_transport_orchestration.py` was not run because it imports orchestrator, router, queue, and retry policy.
- No provider, adapter, network, credential, orchestrator, queue, social orchestration, generated-state, runtime-state, or external-action dependency was admitted.

CLOSE-131B exclusions:

- `signal_agent/transport/__init__.py`
- `signal_agent/transport/orchestrator.py`
- `signal_agent/transport/providers/**`
- `signal_agent/transport/adapters/**`
- `signal_agent/transport/queues/**`
- `signal_agent/social_orchestration/**`
- `tests/test_transport_orchestration.py`
- `tests/.probe_workspace/**`

Next local prerequisite slice: `CLOSE-131C` social models and social ledger shell.

The social orchestration milestone remains future/not ready. Release admission requires committed prerequisite slices, leakage review, focused verification, push-safe branch decision, release notes, tag decision, milestone packaging, and archive metadata.

### Release Branch Cherry-Pick Strategy

Preferred strategy: create a clean release branch from `origin/main` in a separate worktree, then cherry-pick approved safe commits in order while excluding `a094d66`.

Branch and worktree:

- branch: `codex/release-closeout-governance-chain`
- worktree: `..\signal_agent_release_closeout`

Reason:

- `a094d66` is the first ahead commit.
- A branch from current `main` plus revert would still publish `a094d66` in branch history.
- Cherry-picking from `origin/main` is the clean way to exclude `a094d66` from remote history.
- Dirty `main` must not contaminate the release path.

Excluded from the branch plan:

- `a094d66` `Add Letters of Light weekly layer`
- `data/outputs/letters_of_light/**`
- `data/state/letters_of_light_*.jsonl`
- raw/private/generated/runtime paths unless separately admitted

Approved include commits, in order:

```text
6d711f0 1958f33 b9699fa 35bb675 3184e3a 555449b 29c488e
d7c46cb c8b1e97 2102efc 83a46f4 51eef37 7ed46fc 53a6bd3
fc139d3 f7325c2 c86d715 95c950f ba76e3d 86b1005 9a9d24b
c362c10 ab955fc 71c76b8 b8bb70e 2e11882 5b7ebe8 2a45585
610fdc4 d36672a 40d6af5 3d1a3b4 b75b0c9 d8777d2 86ad731
b22fa11 993a459 38df102 94ed6a1 d27f5a9 9a8c4dc 6703090
```

Known risks:

- public-surface examples reference Letters of Light paths introduced by excluded `a094d66`; this is semantic, not runtime, and needs a branch-specific note or later patch
- authority docs `d27f5a9`, `9a8c4dc`, and `6703090` mention the local `a094d66` blocker; release notes should clarify that the branch excludes that commit
- cherry-pick conflicts are unproven until execution
- `data/state/module_artifacts.jsonl` requires the already-reviewed Reflective Pressure exception
- dirty `main` must be avoided by using the separate worktree

Future command skeleton, not yet run:

```powershell
git fetch origin
git worktree add -b codex/release-closeout-governance-chain ..\signal_agent_release_closeout origin/main
cd ..\signal_agent_release_closeout
git cherry-pick 6d711f0 1958f33 b9699fa 35bb675 3184e3a 555449b 29c488e d7c46cb c8b1e97 2102efc 83a46f4 51eef37 7ed46fc 53a6bd3 fc139d3 f7325c2 c86d715 95c950f ba76e3d 86b1005 9a9d24b c362c10 ab955fc 71c76b8 b8bb70e 2e11882 5b7ebe8 2a45585 610fdc4 d36672a 40d6af5 3d1a3b4 b75b0c9 d8777d2 86ad731 b22fa11 993a459 38df102 94ed6a1 d27f5a9 9a8c4dc 6703090
git diff --name-only origin/main..HEAD | rg "^(data/reddit/|data/outputs/letters_of_light/|data/state/letters_of_light_|artifacts/|tests/\.probe_workspace/|\.env|tmp_|out.*\.json)"
.\.venv\Scripts\python.exe -B -m pytest tests\test_public_surfaces.py tests\test_public_surface_report.py tests\test_public_surface_cli.py tests\test_shared_contract.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pytest tests\test_reflective_pressure_review_batch.py tests\test_reddit_archive_to_pressure_seeds.py tests\test_reflective_pressure_models_store.py tests\test_reflective_pressure_flow.py tests\test_reflective_pressure_cli.py tests\test_reflective_pressure_corpus.py tests\test_casts_closure.py tests\test_antiglue_phase_next.py -q -p no:cacheprovider
```

After successful cherry-pick, leakage check, focused tests, and a branch-specific authority/release note, the branch can become a push-only candidate. It is not GitHub-release-ready yet and not Zenodo-ready.

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
