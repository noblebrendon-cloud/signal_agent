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
| `CLOSE-020` | Commit HQ closure evidence | HQ governance | `partial` | HQ closure tests and evidence files from current diff | The slice needs final diff review. | Inspect `tests/test_casts_closure.py` neighbors and exact evidence paths. | HQ evidence commit is bounded and targeted closure verification passes. |
| `CLOSE-030` | Commit lifecycle and reconcile prerequisites | Shared governance | `partial` | `shared/lifecycle.py`; `shared/reconcile.py`; dependent tests | Governance evidence depends on shared prerequisites landing first. | Bound shared primitive diff and its direct tests. | Shared lifecycle/reconcile commit lands before dependent governance evidence. |
| `CLOSE-040` | Commit antiglue governance evidence | Governance evidence | `deferred` | antiglue and governance evidence tests/files | Must follow shared lifecycle/reconcile prerequisite. | Re-evaluate after `CLOSE-030` closes. | Dependent evidence commit passes targeted verification without prerequisite mixing. |
| `CLOSE-050` | Isolate operator and security boundary | Operator/security | `deferred` | operator code, security tests, operator config | Larger dirty slice needs audit after near-ready work. | Group operator/security files without staging. | A separate commit plan names exact files, checks, and boundary claims. |
| `CLOSE-060` | Isolate retention appointments spine | Retention/appointments | `partial` | `app/retention/`; appointment tests; retention docs | Appointment and retention work spans multiple new files. | Audit retention paths as one subsystem before staging. | Retention commit slice and release relevance are explicit and verified. |
| `CLOSE-070` | Split Laviathon site work from generated output | Laviathon/site | `partial` | `laviathon/`; `site_laviathon/`; app and site surfaces | Public site/demo work is mixed with legacy and generated surfaces. | Classify source/demo docs separately from outputs. | Public-facing commit plan excludes generated outputs and legacy ambiguity. |
| `CLOSE-080` | Split Letters of Light logic from outputs | Letters of Light | `partial` | `app/letters_of_light/`; tests; render outputs | Logic/tests and content outputs need separate treatment. | Review render code/tests separately from produced content. | Code/test slice has a clean commit boundary and output policy. |
| `CLOSE-090` | Bound bookgen slice | Bookgen | `partial` | `app/bookgen/`; tests; templates | CLI, render, template, and generated-book paths may mix. | Isolate code/template/test diffs from generated books. | Bookgen commit plan is narrow and verification command is named. |
| `CLOSE-100` | Verify clock, runtime audit, and task contract grouping | Governance runtime | `partial` | clock, runtime audit, task contract, contract evaluator tests | These changes may share governance behavior and require grouped verification. | Map direct dependency links before splitting or grouping. | Commit sequence preserves behavior and each slice has targeted verification. |
| `CLOSE-110` | Review public-surface readiness for release grouping | Public surfaces | `unverified` | public-surface ahead commits and any remaining registry/docs diff | Committed work exists ahead of origin, but release grouping is not reviewed here. | Classify ahead public-surface commits in Phase 0. | Push and release disposition is recorded in the release plan. |

## Commit Closure Evidence

| endpoint_id | Commit | Verification | Boundary evidence | Release/archive state |
|---|---|---|---|---|
| `CLOSE-010` | `40d6af5` `Add reflective pressure corpus review gate and reddit seed tooling` | Focused Slice 001 test command: `52 passed in 25.26s`. | Forbidden-path staged gate passed with `0` forbidden paths. `data/reddit/**`, generated outputs, locks, runtime-state paths, probe workspace state, artifacts, env paths, and temp paths were excluded. | Commit-level endpoint closure only. No push, GitHub release, or Zenodo archive was performed. |

## Phase 0 Ahead Commit Classification

`CLOSE-001` is closed at the triage level by this summary. It records classification for the ahead chain reviewed before Slice 001; later commits must be reviewed when push or release grouping reaches them.

| Classification | Ahead commits from Phase 0 |
|---|---|
| `already released/published` | None from local git evidence. |
| `needs push review` | Public-surface bridge assessment, config validator, report, and CLI commits. |
| `questionable/mixed` | Letters of Light weekly layer commit because code/tests/docs were committed with `data/outputs/**` and `data/state/**`. |
| `clean local feature` | Closeout authority, HQ capture/governance/shared foundation, OIL/io-contract, reflective corpus, and Laviathon evaluator feature commits reviewed as coherent local feature boundaries. |
| `unknown` | None. |

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
