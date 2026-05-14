# Bounded Publication Chain Loop

## Purpose

This document defines the bounded chain by which implemented system work becomes public-facing explanation without overclaiming.

The repository, release, and archive remain the authority. Public articles are interpretations of that authority. Social posts are derivative summaries. Engagement is treated as signal that may enter governed routing, not as proof that a claim is true.

## Core Loop

```text
Repo Evidence
-> Local Implementation
-> Documentation Alignment
-> Checkpoint Note
-> Release Notes
-> GitHub Release
-> Zenodo Archive
-> Archive Record
-> Public Article
-> Social Downflow
-> Signal Capture
-> Spine Assignment
-> Retention / Relationship State
-> Next System Input
```

## Stage Rules

| Stage | Purpose | Required input | Output artifact | Boundary rule | Failure condition |
|---|---|---|---|---|---|
| Repo Evidence | Establish what the repository can actually prove. | Existing code, tests, docs, ledgers, or release artifacts. | Evidence paths and commit references. | Evidence must point to real files or commits. | Claim depends on memory, intent, or rhetoric rather than repo artifacts. |
| Local Implementation | Add or refine a bounded local capability. | Repo evidence, scoped implementation plan, and allowed file boundary. | Committed code and tests. | Implementation must stay inside the approved scope. | Runtime changes include unrelated files, external actions, or untested behavior. |
| Documentation Alignment | Update docs to match implemented behavior. | Landed implementation commit and test evidence. | Updated status docs. | Docs must not exceed implementation. | Docs claim future-facing behavior as implemented. |
| Checkpoint Note | Name the bounded checkpoint. | Implemented feature, aligned docs, and known tests. | `STAGE_1_CHECKPOINT.md` or equivalent checkpoint note. | Checkpoint must state implemented boundaries and non-claims. | Checkpoint omits limitations or treats planned work as complete. |
| Release Notes | Prepare release-facing summary. | Checkpoint note and commit chain. | Versioned release notes. | Release notes must be downstream of committed docs and implementation. | Release notes are drafted before the evidence chain exists. |
| GitHub Release | Publish a repository release artifact. | Git tag and release notes. | GitHub release URL. | Release must reference the correct tag and bounded notes. | Release notes overclaim or tag points at the wrong commit. |
| Zenodo Archive | Create citable archival record. | GitHub release detected by Zenodo. | Zenodo record, DOI, version DOI, concept DOI. | Zenodo archive must be created from an actual release. | Archive metadata is invented or captured before Zenodo issues the DOI. |
| Archive Record | Bring archive evidence back into the repo. | DOI, record URL, citation text, GitHub release URL. | `ARCHIVE_RECORD.md` or equivalent archive record. | Archive records must not exist before DOI capture. | Archive record contains speculative DOI or unverified citation metadata. |
| Public Article | Explain the artifact chain in plain language. | Checkpoint note, release notes, archive record. | Article draft or published article. | Article must not exceed repo-grounded claims. | Article becomes the authority rather than interpretation of the archive. |
| Social Downflow | Derive smaller public summaries from the article. | Published or review-ready article. | Platform-specific posts or snippets. | Social posts are derivatives, not authority. | Social copy introduces claims absent from release/archive docs. |
| Signal Capture | Treat response as structured input. | Comments, replies, reactions, messages, or references. | Captured local signal record or intake note. | Engagement is signal, not validation. | Popularity is interpreted as proof of correctness. |
| Spine Assignment | Route signal to the right identity-aligned lane. | Captured signal and spine taxonomy. | Spine assignment or routing decision. | Signal must route through spine assignment before commercial interpretation. | Signal is converted directly into sales/action without identity context. |
| Retention / Relationship State | Preserve continuity with people and context. | Assigned signal and relationship context. | Retention or relationship state update, if admissible. | Relationship state must remain governed and local unless external action is explicitly allowed. | Relationship data is used for external action without approval or governance. |
| Next System Input | Feed learned signal back into planning. | Governed state, summaries, and operator review. | Next bounded implementation, doc, or release plan. | Next work must start from evidence and scoped boundaries. | Dirty working tree material is swept into publication or planning commits. |

## Invariants

1. Public writing must not exceed repo-grounded claims.
2. Release notes must be downstream of committed docs and implementation.
3. Archive records must not exist before DOI capture.
4. Social posts are derivatives, not authority.
5. Engagement is treated as signal, not validation.
6. Signal must route through spine assignment before commercial interpretation.
7. External actions remain out of scope unless explicitly implemented and governed.
8. Dirty working tree material must not be swept into publication commits.

## Current v0.1.0 Chain

| Field | Value |
|---|---|
| Git tag | `v0.1.0-system-coherence-spine-observability` |
| Tag target commit | `4f7abb8` |
| GitHub release URL | https://github.com/noblebrendon-cloud/signal_agent/releases/tag/v0.1.0-system-coherence-spine-observability |
| Zenodo DOI | `10.5281/zenodo.20176462` |
| Concept DOI | `10.5281/zenodo.20176461` |
| Archive record | `docs/system_coherence/ARCHIVE_RECORD.md` |

The v0.1.0 chain establishes:

- system coherence documentation layer
- local spine observability Stage 1
- local append-only spine/platform/metric records
- deterministic local summaries
- under-tracked detection
- release notes
- GitHub release
- Zenodo DOI
- repo-local archive record

## Explicit Non-Claims

This chain does not claim:

- external platform ingestion
- scraping
- API automation
- posting automation
- messaging automation
- autonomous metric collection
- external actions
- dashboard integration

Any future claim in one of those areas must be implemented, tested, documented, released, archived, and then explained downstream.
