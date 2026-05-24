# Master Endpoint Register

Generated: 2026-05-22
Status: active closeout authority
Scope: dirty-worktree closeout, subsystem endpoints, release readiness, and archive readiness
Behavior changed: no

## Purpose

This register is the repo-level closeout authority for unfinished work in `E:\signal_agent`.

Every closeout session must do at least one of these before it ends:

1. Close an endpoint with verification evidence.
2. Open a new endpoint with a bounded reason and closure condition.
3. Update an existing endpoint with a more accurate status, file boundary, blocker, or next action.

This register does not replace git history, targeted tests, release notes, archive records, or the module registry. It binds them into one auditable closeout queue so a dirty worktree does not become an implicit roadmap.

## System Goal

```text
Finish every open subsystem slice, commit each one cleanly, verify it,
publish the appropriate release artifacts, archive stable milestones to Zenodo,
and close every endpoint into an auditable system register.
```

The system goal is not to finish all code in one sweep. The goal is to turn open work into bounded release work.

## Operating Rules

- Freeze broad feature work until Phase 0 triage is closed. A small fix is allowed only when it is required to close an already-started slice.
- Do not use broad staging such as `git add .` while this register is active.
- Treat every dirty file as untriaged until its subsystem and admission rule are explicit.
- Keep private data, raw archives, generated outputs, runtime state, and scratch files out of source commits unless a separate human decision admits an exact artifact.
- Prefer the smallest verified commit slice that preserves subsystem meaning.
- Do not call a milestone archived until the committed release state is pushed, tagged, release-noted, checked for leakage, and recorded after Zenodo publication.

## Closeout Pipeline

```text
untriaged work
-> subsystem classification
-> private/generated exclusion
-> narrow commit slice
-> targeted verification
-> release grouping
-> GitHub push/tag/release
-> Zenodo archive when milestone-worthy
-> endpoint marked closed
```

Not every endpoint needs a GitHub release. Not every GitHub release needs a Zenodo archive. The endpoint record must state which level applies.

## Phase Order

| Phase | Objective | Closure condition |
|---|---|---|
| Phase 0 | Freeze and triage | Every dirty file is classified and every ahead commit has a review disposition. |
| Phase 1 | Commit near-ready slices | Reflective Pressure, HQ closure evidence, lifecycle/reconcile prerequisites, and governance antiglue are either committed or explicitly blocked. |
| Phase 2 | Commit larger subsystem slices | Operator/security, retention/appointments, public site/content surfaces, bookgen, and clock/runtime/audit contracts have bounded commit plans. |
| Phase 3 | Release and archive | Coherent commits are grouped into documented GitHub releases and stable citable milestones are archived. |

## Classification Vocabulary

Every dirty path must receive one path class during Phase 0.

| Path class | Meaning |
|---|---|
| `source` | Runtime or library code intended for repo ownership. |
| `test` | Verification code, fixture policy, or test support intended for repo ownership. |
| `docs` | Operator, architecture, release, checkpoint, or publication documentation. |
| `config` | Versioned policy, registry, or tooling configuration. |
| `generated` | Build, render, derived output, export, report output, or machine-created artifact. |
| `private` | Raw archive, private corpus, credential-bearing material, or other non-public input. |
| `runtime-state` | Ledger, lock, cache, local run evidence, mutable JSONL state, or transient state projection. |
| `scratch` | Probe, temp, debug, local experiment, or disposable working output. |
| `unknown` | Path needs a decision before staging. |

## Endpoint Status Vocabulary

| Status | Meaning |
|---|---|
| `blocked` | A human decision, missing prerequisite, or unsafe boundary prevents execution. |
| `partial` | Work exists but its file boundary, implementation, or verification is incomplete. |
| `unverified` | The slice may be present but the current diff or verification evidence has not been reviewed. |
| `deferred` | The slice is intentionally ordered behind another endpoint. |
| `ready` | The next action is bounded and can be executed without broad repo mutation. |
| `closed` | The closure condition is satisfied and evidence is recorded here or in a linked release/archive record. |

## Endpoint Record Shape

Every endpoint entry must remain answerable in this shape.

| Field | Required meaning |
|---|---|
| `endpoint_id` | Stable register identifier. |
| `title` | Short bounded outcome, not a vague theme. |
| `subsystem` | Owning subsystem or closeout phase. |
| `status` | One status from this document. |
| `affected_files` | Exact files or path patterns that define the current boundary. |
| `reason_open` | Why the endpoint is not closed now. |
| `safest_next_action` | Smallest action that improves closure confidence. |
| `closure_condition` | Observable evidence required to mark it closed. |

Verification, commit hashes, release tags, DOI records, and human decisions should be added to the endpoint note when they exist.

## Do-Not-Commit Register

These paths and classes require a separate human decision or an exact subsystem release plan before staging.

| Path or class | Reason | Admission rule |
|---|---|---|
| `data/reddit/**` | Raw/private Reddit archive material may leak source data. | Never sweep into source commits. Admit only an explicitly reviewed public derivative if approved. |
| `E:\datasets\reddit\derived/**` | External derived dataset workspace is not repo source authority. | Keep outside repo commits and Zenodo bundles unless separately reviewed. |
| `data/**/*.lock` | Runtime locks are execution state. | Do not commit. |
| `data/state/reflective_pressure_*.jsonl` | Local corpus/runtime state for Reflective Pressure. | Do not include in source/tooling slices. |
| `data/state/reflective_pressure_*.lock` | Reflective Pressure runtime locks. | Do not commit. |
| runtime ledgers and local JSONL state not named by a slice plan | Mutable operational evidence can mix runs and private state. | Admit only an exact reviewed append or formal archive record. |
| generated outputs under `artifacts/**`, `data/outputs/**`, and processed data paths | Derived outputs can be large, stale, private, or rebuildable. | Exclude unless the release plan names exact publishable artifacts. |
| `tmp_*`, `out*.json`, probe outputs, debug outputs, and scratch directories | Local investigation residue. | Exclude until classified as a deliberate fixture or evidence artifact. |
| `.env*` | Environment files can expose local configuration or secrets. | Human review required even for example templates during closeout. |
| `tests/.probe_workspace/**` | Local test workspace state. | Do not commit unless converted into intentional fixtures outside the probe workspace. |
| private archives and external dataset artifacts | Privacy and provenance boundary. | Do not commit or archive raw. |

`data/state/module_artifacts.jsonl` is not automatically forbidden, but a slice may include it only when the diff contains the intended reviewed metadata rows and the commit plan names that exception.

## Endpoint Register

This register begins from the Phase 0 triage queue and records closeout evidence as endpoints move through commit, release, and archive levels. A closed commit-level endpoint does not imply GitHub release or Zenodo archive admission.

| endpoint_id | title | subsystem | status | affected_files | reason_open | safest_next_action | closure_condition |
|---|---|---|---|---|---|---|---|
| `CLOSE-000` | Classify dirty worktree | Phase 0 triage | `partial` | tracked and untracked git status | Phase 0 classified the dirty tree by path class and subsystem buckets, but the remaining dirty paths still need endpoint ownership or explicit blockers before this endpoint can close. | Keep new commit slices bounded by the Phase 0 classifications and record unresolved buckets as endpoint work. | Every dirty path has a path class and subsystem owner or an explicit human-decision blocker. |
| `CLOSE-001` | Review commits ahead of `origin/main` | Phase 0 triage | `closed` | `origin/main..HEAD` at Phase 0 triage | Phase 0 classified the ahead chain before Slice 001: coherent local feature commits, public-surface push-review commits, and one mixed Letters of Light commit requiring caution. | Use the recorded classification when deciding later push and release grouping. | Every ahead commit is marked released, clean local feature, questionable/mixed, needs push review, or unknown. |
| `CLOSE-002` | Decide private Reddit export disposition | Reflective Pressure data boundary | `blocked` | `data/reddit/**`; `E:\datasets\reddit\derived/**` | Raw archive material must not be committed or archived by sweep. | Record the exclusion boundary in triage and ask for a human decision only if a derivative must ship. | Source commits and milestone archives exclude raw/private Reddit data. |
| `CLOSE-003` | Bound generated and runtime state | Phase 0 hygiene | `unverified` | locks, ledgers, generated outputs, scratch outputs | Ignore and artifact hygiene has not been checked against the current dirty tree. | Classify generated/runtime paths and identify ignore or attributes changes needed later. | Generated/private/runtime files are excluded or explicitly admitted by exact plan. |
| `CLOSE-010` | Commit Reflective Pressure review gate slice | Reflective Pressure | `closed` | `app/reflective_pressure/*.py`; focused Reflective Pressure tests; Reddit seed and review tooling; four operator docs; reviewed `data/state/module_artifacts.jsonl` append | Slice 001 closed at commit level with source/docs/tests/tooling only. Raw/private/generated/runtime paths stayed excluded. | Hold for future milestone grouping in the release plan; do not treat closure as release/archive admission. | Focused tests pass and a narrow source/docs/tests/tooling commit exists. |
| `CLOSE-020` | Commit HQ closure evidence | HQ governance | `closed` | `tests/test_casts_closure.py` | Slice 002 closed at commit level with a one-file HQ closure evidence test. Dependency review found only tracked clean implementation imports and no need for uncommitted lifecycle/reconcile/operator work. | Hold for future governance evidence milestone grouping in the release plan; do not treat closure as release/archive admission. | HQ evidence commit is bounded and targeted closure verification passes. |
| `CLOSE-030` | Commit lifecycle and reconcile prerequisites | Shared governance | `closed` | `shared/lifecycle.py`; `shared/reconcile.py` | Slice 003 closed at commit level with prerequisite-only shared primitives. Broader health/reaction/evidence files were intentionally deferred. | Hold for future governance evidence milestone grouping in the release plan; do not treat closure as release/archive admission. | Shared lifecycle/reconcile commit lands before dependent governance evidence. |
| `CLOSE-040` | Commit antiglue governance evidence | Governance evidence | `partial` | antiglue and governance evidence tests/files; deferred shared health/reaction files | The bounded antiglue evidence sub-slice closed, but governance unification/support files remain deferred for separate exact diff review. | Keep parent endpoint open until `CLOSE-040B` is resolved or split further. | Dependent evidence commit passes targeted verification without prerequisite mixing. |
| `CLOSE-040A` | Commit antiglue governance evidence sub-slice | Governance evidence | `closed` | `tests/test_antiglue_phase_next.py` | Slice 004A closed at commit level with one bounded antiglue evidence test file. | Hold for future governance evidence milestone grouping in the release plan; do not treat closure as release/archive admission. | Antiglue evidence test passes and staged set excludes forbidden paths. |
| `CLOSE-040B` | Review governance unification and support primitives | Governance evidence/support | `deferred` | `tests/test_governance_unification.py`; `shared/health.py`; `shared/event_reader.py`; `shared/artifact_envelope.py`; `shared/reactions.py` | Review failed closed with no staging and no commit. The files are useful but too broad for the bounded evidence slice: governance unification scans the repo, health/event-reader touch runtime state, reactions reaches routing/checkpoint mutation, and health has whitespace issues. | Split into narrower endpoints before any staging. | Remainder is either committed as bounded verified slices, redesigned for isolation, or explicitly blocked. |
| `CLOSE-050` | Isolate operator and security boundary | Operator/security | `deferred` | operator code, security tests, operator config | Larger dirty slice needs audit after near-ready work. | Group operator/security files without staging. | A separate commit plan names exact files, checks, and boundary claims. |
| `CLOSE-060` | Isolate retention appointments spine | Retention/appointments | `partial` | `app/retention/`; appointment tests; retention docs | Appointment and retention work spans multiple new files. | Audit retention paths as one subsystem before staging. | Retention commit slice and release relevance are explicit and verified. |
| `CLOSE-070` | Split Laviathon site work from generated output | Laviathon/site | `partial` | `laviathon/`; `site_laviathon/`; app and site surfaces | Public site/demo work is mixed with legacy and generated surfaces. | Classify source/demo docs separately from outputs. | Public-facing commit plan excludes generated outputs and legacy ambiguity. |
| `CLOSE-080` | Split Letters of Light logic from outputs | Letters of Light | `partial` | `app/letters_of_light/`; tests; render outputs | Logic/tests and content outputs need separate treatment. | Review render code/tests separately from produced content. | Code/test slice has a clean commit boundary and output policy. |
| `CLOSE-090` | Bound bookgen slice | Bookgen | `partial` | `app/bookgen/`; tests; templates | CLI, render, template, and generated-book paths may mix. | Isolate code/template/test diffs from generated books. | Bookgen commit plan is narrow and verification command is named. |
| `CLOSE-092` | Split or except Letters of Light mixed commit | Letters of Light / release control | `blocked` | `a094d66`; `app/letters_of_light/*.py`; `docs/letters_of_light/**`; `tests/test_letters_of_light_*.py`; `data/outputs/letters_of_light/**`; `data/state/letters_of_light_*.jsonl` | `a094d66` is not push-safe as-is because it mixes coherent source/docs/tests with generated outputs and runtime-state JSONL. History rewrite is high-risk while the worktree is dirty, so a human decision is needed before repair. | Choose a safe path: release branch/cherry-pick clean chain, rebuild Letters of Light later as smaller slices, or perform controlled history repair only after the dirty tree is clean or safely parked. | `a094d66` is either split/rebuilt, explicitly excepted by human decision, or excluded from a release branch before `main` is pushed. |
| `CLOSE-093` | Review release branch cherry-pick strategy | Release control | `closed` | `origin/main`; `codex/release-closeout-governance-chain`; approved safe ahead commits; excluded `a094d66` | Read-only strategy review found that `a094d66` is the first ahead commit, so a branch from current `main` plus revert would still publish the bad commit in history. | Execute only from a clean worktree rooted at `origin/main`, cherry-picking the approved commit list from the release plan. | Strategy is recorded, include/exclude boundaries are explicit, and branch execution is separated from dirty `main`. |
| `CLOSE-094` | Execute release branch worktree cherry-pick | Release control | `ready` | `..\signal_agent_release_closeout`; branch `codex/release-closeout-governance-chain`; approved commit list in release plan | Execution has not run yet. Cherry-pick conflicts, branch-specific authority notes, leakage checks, and focused tests remain unverified. | Create a separate worktree from `origin/main`, cherry-pick safe commits in order, stop on conflict, then run leakage and focused verification. | Clean branch exists without `a094d66`, leakage check passes, focused tests pass, and branch-specific release notes are recorded before any push. |
| `CLOSE-100` | Verify clock, runtime audit, and task contract grouping | Governance runtime | `partial` | clock, runtime audit, task contract, contract evaluator tests | These changes may share governance behavior and require grouped verification. | Map direct dependency links before splitting or grouping. | Commit sequence preserves behavior and each slice has targeted verification. |
| `CLOSE-110` | Review public-surface readiness for release grouping | Public surfaces | `closed` | `c362c10`; `b8bb70e`; `2a45585`; `610fdc4`; public-surface config examples, docs, source, and tests | Push-review audit approved the public-surface commits for push once the `a094d66` blocker is resolved or bypassed. Main remains blocked by `a094d66`. | Hold for future public-surface readiness milestone grouping; do not treat review approval as push, tag, release, or archive admission. | Push-review audit passed, forbidden-path check passed, read-only boundary is preserved, and focused verification passed. |
| `CLOSE-120` | Record push and release readiness audit | Release control | `closed` | `origin/main..HEAD`; git status counts; release candidate gates | Audit completed with no staging, no push, no tag, no GitHub release, and no Zenodo archive. Main must not be pushed blindly because the ahead chain contains at least one questionable/mixed commit. | Use the audit result to review blocking commits before deciding a safe push path. | Push/release audit result is recorded and next review targets are explicit. |
| `CLOSE-121` | Review questionable ahead commit `a094d66` | Letters of Light / release control | `closed` | `a094d66`; `data/outputs/letters_of_light/**`; `data/state/letters_of_light_*.jsonl`; Letters of Light source/docs/tests | Read-only review found the commit is not push-safe as-is. Source/docs/tests are coherent, but the commit mixes them with generated outputs and runtime-state JSONL. | Keep `main` push blocked and resolve `CLOSE-092` before publishing `main`, unless an explicit human exception is recorded. | A push disposition for `a094d66` is recorded before pushing `main` or forming a release branch. |

## Commit Closure Evidence

| endpoint_id | Commit | Verification | Boundary evidence | Release/archive state |
|---|---|---|---|---|
| `CLOSE-010` | `40d6af5` `Add reflective pressure corpus review gate and reddit seed tooling` | Focused Slice 001 test command: `52 passed in 25.26s`. | Forbidden-path staged gate passed with `0` forbidden paths. `data/reddit/**`, generated outputs, locks, runtime-state paths, probe workspace state, artifacts, env paths, and temp paths were excluded. | Commit-level endpoint closure only. No push, GitHub release, or Zenodo archive was performed. |
| `CLOSE-020` | `b75b0c9` `Add HQ governance closure evidence` | `.\.venv\Scripts\python.exe -m pytest tests\test_casts_closure.py -q`: `10 passed in 4.56s`. | Dependency gate passed: the test imports tracked clean implementation files and did not require uncommitted lifecycle/reconcile/operator work. Staged gate passed with exactly one staged path, `tests/test_casts_closure.py`, and `git diff --cached --check` clean. | Commit-level endpoint closure only. No push, GitHub release, or Zenodo archive was performed. |
| `CLOSE-030` | `86ad731` `Add shared lifecycle and reconcile primitives` | `.\.venv\Scripts\python.exe -B -m py_compile shared\lifecycle.py shared\reconcile.py` passed. Focused pytest command passed with `5 passed in 1.22s`. | Staged gate passed with exactly two paths, `shared/lifecycle.py` and `shared/reconcile.py`; `git diff --cached --check` was clean; forbidden staged path count was `0`. | Commit-level endpoint closure only. No push, GitHub release, or Zenodo archive was performed. |
| `CLOSE-040A` | `993a459` `Add antiglue governance evidence` | `.\.venv\Scripts\python.exe -B -m pytest tests\test_antiglue_phase_next.py -q -p no:cacheprovider`: `6 passed in 1.09s`. Narrow selector `tests\test_governance_unification.py::TestSharedLifecycleDeprecation`: `3 passed in 0.32s`. | Staged gate passed with exactly one path, `tests/test_antiglue_phase_next.py`; `git diff --cached --check` was clean; forbidden staged path count was `0`. | Commit-level endpoint closure only. No push, GitHub release, or Zenodo archive was performed. |

## Deferred From Governance Evidence

These files remain deferred under `CLOSE-040B` and must be classified one by one before any later staging:

- `shared/health.py`
- `shared/event_reader.py`
- `shared/artifact_envelope.py`
- `shared/reactions.py`
- `tests/test_governance_unification.py`

Review evidence:

- No files were staged or committed; the index remained empty.
- `.\.venv\Scripts\python.exe -B -m py_compile shared\health.py shared\event_reader.py shared\artifact_envelope.py shared\reactions.py` passed.
- `.\.venv\Scripts\python.exe -B -m pytest tests\test_governance_unification.py::TestSharedLifecycleDeprecation -q -p no:cacheprovider` passed with `3 passed in 0.28s`.

Deferral reasons:

- `tests/test_governance_unification.py` includes repo-wide `root.rglob("*.py")` scanning, too broad for the current dirty tree.
- `shared/health.py` reaches runtime-state paths such as `data/state/*` and `data/capture/routing_log.jsonl`.
- `shared/event_reader.py` reads and writes checkpoint/event-log state when used.
- `shared/reactions.py` reaches routing behavior and checkpoint mutation.
- `shared/health.py` fails `git diff --no-index --check` due whitespace issues.

Recommended future split:

- health/event-reader runtime-state support slice
- artifact-envelope primitive slice
- reactions/routing checkpoint slice
- governance-unification repo-wide scan redesign or isolation slice

## Phase 0 Ahead Commit Classification

`CLOSE-001` is closed at the triage level by this summary. It records classification for the ahead chain reviewed before Slice 001; later commits must be reviewed when push or release grouping reaches them.

| Classification | Ahead commits from Phase 0 |
|---|---|
| `already released/published` | None from local git evidence. |
| `needs push review` | Public-surface bridge assessment, config validator, report, and CLI commits. |
| `questionable/mixed` | Letters of Light weekly layer commit because code/tests/docs were committed with `data/outputs/**` and `data/state/**`. |
| `clean local feature` | Closeout authority, HQ capture/governance/shared foundation, OIL/io-contract, reflective corpus, and Laviathon evaluator feature commits reviewed as coherent local feature boundaries. |
| `unknown` | None. |

## Push / Release Readiness Audit

The push/release-readiness audit recorded after `CLOSE-040B` kept the repository read-only and did not push, tag, release, archive, stage, or commit runtime/code/data files.

| Field | Result |
|---|---|
| Branch | `main` |
| Upstream | `origin/main` |
| Ahead / behind | ahead `40`, behind `0` |
| Staged paths | `0` |
| Modified tracked paths | `34` |
| Untracked paths | `1538` |
| Repo clean | `false` |
| Push `main` recommended | `false` |

Blocking commit for blind push:

- `a094d66` `Add Letters of Light weekly layer`: committed source/docs/tests together with generated output under `data/outputs/letters_of_light/**` and runtime-state-like JSONL paths under `data/state/letters_of_light_*.jsonl`. This requires explicit review before publishing `main`.

Push-review commits:

- `c362c10` `Assess public surface governance bridge`
- `b8bb70e` `Add public surface config validator`
- `2a45585` `Add public surface governance report`
- `610fdc4` `Add public surface governance CLI`

Safe closure-chain commits identified by the audit:

- `d36672a` `Add repo closeout authority`
- `40d6af5` `Add reflective pressure corpus review gate and reddit seed tooling`
- `3d1a3b4` `Record Reflective Pressure slice closure`
- `b75b0c9` `Add HQ governance closure evidence`
- `d8777d2` `Record HQ closure evidence`
- `86ad731` `Add shared lifecycle and reconcile primitives`
- `b22fa11` `Record lifecycle reconcile closure`
- `993a459` `Add antiglue governance evidence`
- `38df102` `Record antiglue evidence closure`
- `94ed6a1` `Record governance unification deferral`

Release readiness result:

- Reflective Pressure Spine `v0.2` is not ready.
- Governance Evidence `v0.3` is not ready.
- Combined Closeout Authority + Governance Evidence checkpoint is not ready.
- There are no Zenodo candidates yet.

The safe next action is to inspect `a094d66` before deciding whether to push `main`, create a release branch, or continue local cleanup.

## Letters of Light Mixed Commit Review

Read-only inspection of `a094d66` `Add Letters of Light weekly layer` is complete. The verdict is:

- `push_safe`: `false`
- `requires_human_approval`: `true`
- recommended action: revert/split `a094d66` before pushing `main`
- `main` must still not be pushed blindly

Reason: the code/docs/tests are coherent, but the commit mixes source/docs/tests with generated outputs and runtime-state JSONL.

Path classification:

| Class | Paths |
|---|---|
| Source code | `app/letters_of_light/weekly_cli.py`; `app/letters_of_light/weekly_models.py`; `app/letters_of_light/weekly_render.py`; `app/letters_of_light/weekly_store.py` |
| Tests | `tests/test_letters_of_light_weekly_content.py`; `tests/test_letters_of_light_weekly_render.py`; `tests/test_letters_of_light_weekly_state.py` |
| Docs/template source | `docs/letters_of_light/README.md`; `docs/letters_of_light/sunday_runbook.md`; `docs/letters_of_light/templates/email_preview.md.j2`; `docs/letters_of_light/templates/jail_packet.md.j2`; `docs/letters_of_light/templates/print_packet.md.j2`; `docs/letters_of_light/templates/weekly_letter.md` |
| Acceptable only with explicit admission | `docs/letters_of_light/letters/2026-05-17.md` |
| Generated output | `data/outputs/letters_of_light/2026-05-17/email_preview.md`; `data/outputs/letters_of_light/2026-05-17/human_approval_checklist.md`; `data/outputs/letters_of_light/2026-05-17/jail_packet.md`; `data/outputs/letters_of_light/2026-05-17/print_packet.md` |
| Runtime state | `data/state/letters_of_light_letters.jsonl`; `data/state/letters_of_light_transitions.jsonl` |

Blocking paths:

- `data/outputs/letters_of_light/**`
- `data/state/letters_of_light_*.jsonl`

Do not rewrite or rebase while the dirty worktree remains unresolved. Safe options remain:

- release branch or cherry-pick clean chain
- rebuild Letters of Light later as smaller slices
- interactive rebase only after the dirty tree is clean or safely parked

## Public-Surface Push Review

Read-only push-review audit of the public-surface commits is complete. The verdict is:

- public-surface commits are approved for push once the `a094d66` blocker is resolved or bypassed
- `main` remains blocked by `a094d66`
- public-surface commits are release-relevant for a future public-surface readiness milestone
- public-surface commits are not Zenodo-ready by themselves

Reviewed commits and path classes:

| Commit | Paths | Classification |
|---|---|---|
| `c362c10` `Assess public surface governance bridge` | `config/public_surfaces/*.example.*`; `docs/operator/public_surface_*` | config/example; docs |
| `b8bb70e` `Add public surface config validator` | `shared/public_surfaces.py`; `tests/test_public_surfaces.py` | source; test |
| `2a45585` `Add public surface governance report` | `app/public_surfaces/report.py`; `tests/test_public_surface_report.py` | source; test |
| `610fdc4` `Add public surface governance CLI` | `app/public_surfaces/cli.py`; `tests/test_public_surface_cli.py` | source; test |

Forbidden path check passed:

- no `data/reddit/**`
- no `data/state/**`
- no `data/outputs/**`
- no `artifacts/**`
- no locks
- no env/temp/probe paths
- no runtime, generated, or private paths

Boundary verdict: read-only boundary preserved. The implementation reads example config/JSONL, validates, builds reports, and renders JSON/text. It does not perform routing execution, publishing execution, platform adapter work, approval execution, live ledger writes, external network calls, or public-content mutation. Test-only writes are confined to `tmp_path`.

Verification:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\test_public_surfaces.py tests\test_public_surface_report.py tests\test_public_surface_cli.py tests\test_shared_contract.py -q -p no:cacheprovider
```

Result: `24 passed in 2.95s`.

## Release Branch Cherry-Pick Strategy

Read-only release-branch planning is complete. The preferred strategy is to create branch `codex/release-closeout-governance-chain` from `origin/main` in a separate worktree at `..\signal_agent_release_closeout`, then cherry-pick the approved safe commits in order.

Reason:

- `a094d66` is the first ahead commit.
- A branch from current `main` plus revert would still publish `a094d66` in branch history.
- Cherry-picking from `origin/main` is the clean path that excludes `a094d66` from remote history.
- Dirty `main` must not contaminate the release path.

Exclude:

- `a094d66` `Add Letters of Light weekly layer`
- `data/outputs/letters_of_light/**`
- `data/state/letters_of_light_*.jsonl`
- raw/private/generated/runtime paths unless separately admitted

Known risks:

- Public-surface examples reference Letters of Light paths introduced by excluded `a094d66`; this is semantic, not runtime, and needs a branch-specific note or later patch.
- Authority docs `d27f5a9`, `9a8c4dc`, and `6703090` mention the local `a094d66` blocker; acceptable for internal control, but release notes should clarify that the release branch excludes that commit.
- Cherry-pick conflicts are unproven until execution.
- `data/state/module_artifacts.jsonl` requires the already-reviewed Reflective Pressure exception.
- Dirty `main` must be avoided by using a separate worktree.

The full include list and future command skeleton are owned by the release/archive plan.

## Closed Milestone Evidence

| endpoint_id | title | status | Evidence |
|---|---|---|---|
| `CLOSE-900` | Stage 1 System Coherence and Local Spine Observability | `closed` | `docs/system_coherence/RELEASE_NOTES_v0.1.0.md` and `docs/system_coherence/ARCHIVE_RECORD.md` record the bounded release and Zenodo archive. |

## Update Rules

- Change a status only when the reason is written into the row or an adjacent note.
- Add a new endpoint instead of widening a row until it stops having one closure condition.
- Close a commit-level endpoint only after the commit hash and verification result are known.
- Close a release-level endpoint only after tag, pushed release state, release notes, and release boundary checks are known.
- Close an archive-level endpoint only after the Zenodo record or DOI is recorded in repo docs.
- Keep blocked endpoints visible. A blocker is part of the audit trail, not a reason to hide work.
