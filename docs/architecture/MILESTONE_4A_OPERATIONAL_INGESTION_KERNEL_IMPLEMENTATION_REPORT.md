# Milestone 4A Operational Ingestion Kernel Implementation Report

Date: 2026-08-09

Status: implemented and verified; not staged or committed

Repository: `E:\signal_agent-milestone2-closure`

Branch: `codex/milestone3-closure`

Canonical base: `6c533cfe7b3c1b1a43c1c68cea98787b2b6441bc`

## Outcome

M4A is implemented as an additive, source-neutral, domain-neutral operational-ingestion kernel. It defines immutable acquisition/session artifacts, secret-safe attempt receipts, exact page-capture provenance, separate transport and semantic hash domains, canonical bounded semantic material, content-addressed observation indexes, completed-manifest verification authority, checkpoint candidates, exclusive checkpoint commits, state resolution, and failure receipts.

No M4B simulator/source adapter, Gmail code, networking, authentication implementation, CLI, scheduler, daemon, UI, messaging, publishing, or upstream write path was added.

The canonical plan was updated before implementation to incorporate the four mandatory clarifications:

1. Transport-history determinism is separate from semantic-evidence determinism.
2. `capture_set_hash` is separate from `observation_set_hash`.
3. Stable immutable artifact replay uses load, full verification, and existing-byte return.
4. Checkpoints reference a content-addressed observation-index artifact instead of inlining unbounded history.

M4B remains unauthorized and unimplemented.

## Implemented architecture

```text
Frozen acquisition intent
  -> immutable session descriptor
  -> secret-safe request-attempt receipts
  -> exact content-addressed response bodies and capture receipts
  -> canonical source observations
  -> capture_set_hash (transport provenance)
  -> observation_set_hash (semantic evidence)
  -> semantic bounded source material
  -> sealed acquisition boundary
  -> injected governed processor
  -> completed detached manifest verification
  -> content-addressed observation index
  -> eligible checkpoint candidate
  -> candidate-bound completed-manifest verifier authority
  -> exclusive checkpoint commit
```

The kernel accepts already captured page models and an injected governed processor. It imports no transport implementation, relationship package, source adapter, provider client, or networking module. `OperationalTransport` and `RemotePageSource` remain structural protocols for later phases; M4A provides no implementation of either.

## Mandatory clarification results

### Transport-history and semantic-evidence determinism

- Identical acquisition inputs, response bodies, retry history, and injected clock produce byte-identical operational source trees.
- Different approved retry/page histories with the same canonical observations may produce different attempts, captures, boundaries, observation indexes, candidates, commits, and `capture_set_hash` values.
- Those histories produce the same `observation_set_hash`, byte-identical bounded semantic material, identical normalized fake effects, and byte-identical fake governed output trees.
- Exact capture history remains immutable rather than being normalized away.

### Exact capture and semantic observation identity

- `capture_set_hash` hashes ordered exact capture receipts, successful attempt references, exact response-body hashes, and page ordinals.
- `observation_set_hash` hashes only sorted canonical observation descriptors.
- Bounded material includes `observation_set_hash` and canonical observations. It explicitly excludes capture-set hash, retry history, page boundaries, attempt receipts, and acquisition time from semantic identity.
- Acquisition boundaries and observation-index entries retain exact capture references and record locators as provenance.

### Byte-safe immutable replay

- Canonical JSON persistence uses exclusive creation, exact byte comparison, sealed hash verification, secret scanning, and immutable conflict rejection.
- A repeated checkpoint-candidate construction revalidates intent, every capture receipt and exact body, boundary, bounded material, observation index, exact preserved source bytes, preservation receipt, completed manifest, and manifest artifacts before returning existing candidate bytes.
- A repeated checkpoint commit returns the existing commit bytes even when the caller supplies a later proposed commit time.
- A different successor for an occupied predecessor slot fails without mutation.
- A test that attempts to reuse a candidate ID with changed creation bytes is rejected.

### Observation-index boundary

- Each observation index is immutable and content-addressed.
- It contains protected source-record keys, observation IDs, content hashes, record types, and bounded capture-provenance references.
- It may reference the prior observation index by ID/path/hash.
- Checkpoint candidates and commits contain only observation-index ID/path/hash.
- They do not inline index entries or full source history.
- Mutable current-state storage, compaction, pruning, and history rewriting are absent.

## State and checkpoint semantics

The kernel resolves state from immutable artifact existence. It writes no mutable success flag.

The committed checkpoint advances only after:

1. Session, attempt, and exact capture artifacts persist.
2. Canonical observations and bounded semantic material persist.
3. A terminal acquisition boundary seals both hash domains.
4. The injected governed processor preserves/processes the bounded material.
5. The detached manifest exists, is canonical, has a valid sealed hash, declares `completion_state: completed`, binds the exact bounded material and preservation receipt, and verifies every named artifact hash.
6. The manifest safety flags prohibit network authorization and source-record mutation.
7. The observation index persists and verifies.
8. The checkpoint candidate persists and verifies.
9. A separate completed-manifest verifier authority binds the exact candidate ID/hash, exact completed-run references, and supported completion policy.
10. Commit reopens the local assembly chain and completed governed run, validates the authority, and resolves the actual current predecessor.
11. The predecessor's exclusive checkpoint slot is empty or contains the exact replay.
12. The commit receipt is exclusively created.

A missing, malformed, noncanonical, hash-invalid, input-mismatched, receipt-mismatched, artifact-invalid, network-authorizing, or source-mutating manifest blocks candidate creation and checkpoint advancement.

## Failure evidence

The focused suite injects failures after each kernel boundary:

- Session creation.
- Request-attempt persistence.
- Page-capture persistence.
- Bounded-material persistence.
- Acquisition-boundary persistence.
- Governed processor return.
- Completed-manifest verification.
- Observation-index persistence.
- Checkpoint-candidate persistence.
- Completed-manifest verifier-authority persistence.
- Immediately before checkpoint commit.

The fake governed processor separately fails:

- Before preservation.
- After preservation.
- After normalization.
- After output generation but before manifest creation.

For every injected failure, the prior checkpoint remains current and no successor commit exists. Failure receipts retain only class/code/stage and the last valid artifact references; exception detail is omitted. A canary secret embedded in an exception message does not persist.

## Secret boundary

Operational JSON writes and exact capture-body writes pass through secret-boundary enforcement. The implementation rejects:

- Credential-bearing key names such as access/refresh token, API key, authorization, cookie, client secret, password, OAuth code, PKCE verifier, and signed URL.
- Bearer tokens, token/key/secret/signature/OAuth/PKCE query parameters, provider token prefixes, authorization/cookie headers, signed URLs, and private-key markers in string or byte content.
- Secret-bearing attempt metadata and exact response bodies before they are written.

Persisted request identity is a fingerprint. Operational intent contains only a nonsecret credential-profile reference and authentication-mode label. Failure receipts never persist exception messages. The successful focused artifact tree contains zero configured secret canaries.

This is persistence enforcement, not authentication or secret-storage implementation.

## Public programmatic surface

The additive `signal_agent.operational_ingestion` package exports:

- Frozen `AcquisitionIntent`, `PolicyIdentity`, and `SourceIdentity` models.
- Frozen `RequestAttempt`, `CapturedPage`, and `CanonicalObservation` models.
- Frozen `CompletedRunReference` and `CompletedManifestVerifierAuthority` models.
- Frozen `ObservationIndexReference`, `PersistedArtifact`, `ResolvedIngestionState`, and `IngestionResult` models.
- `OperationalIngestionKernel.run_from_captured_pages(...)`.
- Canonical JSON and SHA-256 helpers.
- Capture/observation set hash helpers.
- Completed-run verification.
- Candidate creation, checkpoint commit, and current-state resolution.
- Stable operational error classes.

Transport, page-source, governed-processor, clock, and failure-injector interfaces are protocols. No provider implementation is present.

## Schema inventory

- `acquisition_intent.v1.schema.json`
- `acquisition_session.v1.schema.json`
- `request_attempt_receipt.v1.schema.json`
- `page_capture_receipt.v1.schema.json`
- `bounded_source_material.v1.schema.json`
- `acquisition_boundary.v1.schema.json`
- `observation_index.v1.schema.json`
- `ingestion_failure_receipt.v1.schema.json`
- `checkpoint_candidate.v1.schema.json`
- `completed_manifest_verifier_authority.v1.schema.json`
- `checkpoint_commit_receipt.v1.schema.json`

All successful operational artifact kinds and the injected-failure receipt validate under JSON Schema Draft 2020-12 in the focused suite.

## Verification manifest

| Verification universe | Final result |
|---|---:|
| M4A focused gate before closure-audit remediation | 42 passed in 111.25 seconds |
| M4A focused gate after closure-audit remediation | 115 passed in 213.37 seconds |
| Existing closure collection | 216 selected of 217 collected; one documented deselection in 8.08 seconds |
| Final Milestone 2/3 closure gate | 216 passed, 1 documented deselection in 215.45 seconds |
| Explicit LinkedIn, interaction-event, and Milestone 3 witness gate | 3 passed in 12.64 seconds |
| Python compilation | Passed for M4A package and focused tests |
| New trailing-whitespace findings | 0 |
| Tracked file modifications | 0 |
| Staged files | 0 |

The documented deselection remains:

`tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry`

It is the existing closure-only exception described by Milestones 2 and 3. The other six invariant-checker tests pass inside the 216-test gate.

The 216-test command includes the exact existing relationship/importer matrix, interaction-event gate, health/authority/invariant scope, and all Milestone 3 reconciliation tests. M4A tests are additive and run separately.

## Protected hashes

| Protected path or artifact | SHA-256 | Result |
|---|---|---|
| Generic relationship runner | `967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44` | Exact |
| LinkedIn adapter | `44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d` | Exact |
| Interaction-event adapter | `76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589` | Exact |
| Relationship-record schema | `32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1` | Exact |
| LinkedIn Milestone 2 witness | `00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02` | Exact |
| Interaction-event Milestone 2 witness | `823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d` | Exact |
| Milestone 3 witness | `80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b` | Exact |
| Existing Gmail reader | `35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1` | Exact |
| Existing corpus CLI | `5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7` | Exact |

The M4A architecture test parses every package import and rejects networking, corpus-import, relationship, identity-reconciliation, and media-opportunities dependencies.

## Exact additive file inventory

### Canonical planning and implementation evidence

1. `docs/architecture/MILESTONE_4_OPERATIONAL_INGESTION_AND_LIVE_SOURCE_PLAN.md`
2. `docs/architecture/MILESTONE_4A_OPERATIONAL_INGESTION_KERNEL_IMPLEMENTATION_REPORT.md`

### Operational-ingestion schemas

3. `schemas/operational_ingestion/acquisition_boundary.v1.schema.json`
4. `schemas/operational_ingestion/acquisition_intent.v1.schema.json`
5. `schemas/operational_ingestion/acquisition_session.v1.schema.json`
6. `schemas/operational_ingestion/bounded_source_material.v1.schema.json`
7. `schemas/operational_ingestion/checkpoint_candidate.v1.schema.json`
8. `schemas/operational_ingestion/checkpoint_commit_receipt.v1.schema.json`
9. `schemas/operational_ingestion/completed_manifest_verifier_authority.v1.schema.json`
10. `schemas/operational_ingestion/ingestion_failure_receipt.v1.schema.json`
11. `schemas/operational_ingestion/observation_index.v1.schema.json`
12. `schemas/operational_ingestion/page_capture_receipt.v1.schema.json`
13. `schemas/operational_ingestion/request_attempt_receipt.v1.schema.json`

### Source-neutral M4A package

14. `signal_agent/operational_ingestion/__init__.py`
15. `signal_agent/operational_ingestion/artifacts.py`
16. `signal_agent/operational_ingestion/canonical.py`
17. `signal_agent/operational_ingestion/checkpoints.py`
18. `signal_agent/operational_ingestion/contracts.py`
19. `signal_agent/operational_ingestion/errors.py`
20. `signal_agent/operational_ingestion/kernel.py`
21. `signal_agent/operational_ingestion/models.py`
22. `signal_agent/operational_ingestion/secrets.py`

### Focused M4A tests and fake processor

23. `tests/operational_ingestion/__init__.py`
24. `tests/operational_ingestion/conftest.py`
25. `tests/operational_ingestion/test_acquisition_contracts.py`
26. `tests/operational_ingestion/test_checkpoint_contract.py`
27. `tests/operational_ingestion/test_closure_audit_remediation.py`
28. `tests/operational_ingestion/test_failure_semantics.py`
29. `tests/operational_ingestion/test_models_and_determinism.py`
30. `tests/operational_ingestion/test_secret_and_architecture.py`

All 30 files are additive and currently untracked. No tracked Milestone 1-3 file is modified. Nothing is staged.

## Deviations from the planning change map

Three narrow implementation-shape deviations occurred; none changes the approved contract:

1. The coordinator is named `kernel.py` rather than the provisional `acquisition.py`, matching the approved M4A kernel scope.
2. No tracked retry-policy configuration file was added. M4A freezes and hashes retry-policy identity and persists retry/rate-limit attempt facts, but it does not execute a transport retry policy. A concrete versioned retry policy belongs to M4B's simulator acceptance rather than an unused M4A config.
3. No separate assembly-receipt file was added. In M4A, the sealed semantic bounded-material artifact plus the sealed boundary jointly contain and verify source/adapter/cycle/prior identities, observation scope, coverage, assembly policy, exact/semantic hashes, bounded-file identity, exact counts, terminal proof, capture membership, and observation-to-capture provenance. A source-specific assembler does not exist until M4B.

The report/test filenames were made more specific than the provisional change map. No functional scope was broadened.

## M4A Closure Audit Remediation

The first closure audit stopped before Git mutation and identified four contract failures. This remediation changes only the additive M4A implementation, schemas, focused tests, canonical-plan clarification, and this report.

### 1. Complete sealed assembly evidence

- **Root cause:** `AcquisitionBoundary` sealed only the two aggregate hashes, capture references, and a bounded-material reference. It omitted the requested observation boundary, explicit coverage, semantic and transport counts, assembly/canonicalization policy identity, and a structured terminal proof. `BoundedSourceMaterial` incorrectly reused acquisition-policy identity and did not carry the semantic observation scope/count contract.
- **Files repaired:** `models.py`, `artifacts.py`, `kernel.py`, acquisition-intent/boundary/bounded-material/page-capture schemas, fixture construction, and remediation tests.
- **Invariant restored:** `AcquisitionBoundary + BoundedSourceMaterial` jointly and explicitly bind source/adapter/cycle/prior identity, observation boundary and coverage, assembly policy ID/version/hash, ordered captures, distinct capture/observation hashes, bounded-material ID/hash/file SHA/path, captured/identity/observation/version/duplicate/change/tombstone counts, terminal evidence, and exact observation-to-capture provenance. No standalone assembly receipt was introduced.
- **Regression evidence:** missing and inconsistent observation-boundary, coverage, policy, count, terminal, capture-set, observation-set, and bounded-material fields all fail before candidate creation.

### 2. Transitive capture verification

- **Root cause:** candidate construction verified the sealed boundary envelope but did not reopen its capture receipts or exact response bodies.
- **Files repaired:** `artifacts.py`, `kernel.py`, page-capture schema, and `test_closure_audit_remediation.py`.
- **Invariant restored:** candidate creation and commit-time local-chain validation reopen every referenced capture and body, verify canonical seals and derived IDs, successful-attempt identity, request and continuation hashes, response-schema identity, body path/size/SHA, predecessor link, session membership, capture-set recomputation, terminal proof, observation membership, and provenance.
- **Regression evidence:** missing captures, altered bodies, invalid receipt hashes, wrong body hashes/sizes, altered chain links, wrong request/continuation/session facts, and false observation membership all fail closed. Re-bound malicious receipts and boundaries still fail on the underlying transitive fact rather than relying only on the original outer hash.

### 3. Exact preservation byte binding

- **Root cause:** completed-run verification compared the receipt's operational-input descriptor but never compared the receipt's source hash or preserved file bytes with the exact bounded-material file.
- **Files repaired:** `checkpoints.py`, the fake governed processor in `conftest.py`, and remediation tests.
- **Invariant restored:** verification computes SHA-256 over the canonical bounded-material file, requires the acquisition-boundary descriptor and preservation receipt to claim that exact hash/size, reopens the preserved-source path, requires byte equality, and verifies the completed manifest's preserved-source descriptor before candidate eligibility.
- **Regression evidence:** post-boundary bounded-material mutation, wrong receipt source SHA with a correct operational-input reference, wrong bounded descriptor, wrong preserved-source reference, and divergent preserved bytes all fail before candidate creation.

### 4. Independent commit authority and current-state validation

- **Root cause:** verifier authority was nested inside the candidate before the candidate had an ID/hash, so it could not bind that candidate without a cycle. Commit verified only the candidate seal and trusted its predecessor reference without resolving actual current state.
- **Files repaired:** `models.py`, `checkpoints.py`, `kernel.py`, `__init__.py`, candidate/commit schemas, new `completed_manifest_verifier_authority.v1.schema.json`, and checkpoint/remediation/failure tests.
- **Invariant restored:** the candidate is sealed first; a separate immutable authority artifact then binds its exact ID/hash, exact completed-run/preservation/boundary/material references, supported completion-policy ID/version/hash, required assertions, and explicit absence of external/network/upstream authority. Commit independently reopens the complete local assembly chain and completed governed run, validates candidate and authority identities, resolves the verified current checkpoint chain immediately before promotion, and uses the exclusive predecessor slot. Exact occupied-slot replay returns existing bytes; divergent or stale successors fail without mutation.
- **Regression evidence:** valid root and successor commits, exact replay, invalid candidate schema/status/identity, missing authority, wrong candidate binding, unsupported authority type/version, wrong policy, false assertions, forbidden action flags, a noncurrent predecessor with an empty slot, stale concurrent candidates, divergent bootstrap candidates, and unchanged losing history are covered.

### Cross-cutting verification result

The focused gate increased from 42 to 115 passing tests. The failure-injection matrix now includes authority persistence. The three original implementation-shape deviations remain valid: `kernel.py` is still only a layout choice; retry-policy execution/configuration remains deferred because M4A has no retry consumer; and the now-complete sealed boundary/material pair still replaces a standalone assembly receipt. M4B and M4C remain unstarted.

## Explicit non-implementation result

The following remain absent:

- M4B simulator transport or source adapter.
- Gmail-specific parser, adapter, composition root, or transport.
- Production or test networking imports in the M4A package.
- OAuth, token refresh, credential loading, or secret storage.
- CLI command or operator surface.
- Scheduler, daemon, webhook, Pub/Sub, background worker, or source registry.
- Relationship runner or source-adapter modification.
- New relationship schema or identity-reconciliation behavior.
- Automatic merge, decision, projection, message, publication, or upstream action.

## Worktree and handoff state

- Starting and current HEAD: `6c533cfe7b3c1b1a43c1c68cea98787b2b6441bc`.
- Current branch: `codex/milestone3-closure`.
- Tracked modifications: zero.
- Staged files: zero.
- Additive untracked M4 planning/implementation files: exactly 30, listed above.
- New trailing whitespace: zero.
- No commit, merge, push, tag, PR, worktree deletion, or remote mutation was performed.

M4A is ready for separate review. M4B must not begin until M4A is explicitly approved.
