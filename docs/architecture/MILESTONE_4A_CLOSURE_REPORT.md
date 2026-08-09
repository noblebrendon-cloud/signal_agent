# Milestone 4A Closure Report

## Closure identity

- Milestone 3 base SHA: `6c533cfe7b3c1b1a43c1c68cea98787b2b6441bc`
- Source branch: `codex/milestone3-closure`
- Source implementation worktree: `E:\signal_agent-milestone2-closure`
- M4A closure branch: `codex/milestone4a-closure`
- M4A closure worktree: `E:\signal_agent-milestone4a-closure`
- Reviewed implementation-report SHA-256: `8b033252f909fdca4c00ff18903f80bf7e5ce69ca9ddb793620a5d358cd84179`
- Scope: M4A operational-ingestion semantics and kernel only.
- M4B/M4C status: not started.

The final closure commit contains this report, so its SHA cannot be embedded in
its own bytes without changing that SHA. The final SHA and final clean status
are recorded by the external closure handoff and are recoverable directly from
`git rev-parse HEAD` and `git status --short` on the closure branch.

## Causal commits

| Order | SHA | Message | Boundary |
|---:|---|---|---|
| 1 | `53969e79294ba9fd873ae99f476af0d4c12ce4dd` | `docs(architecture): add Milestone 4 operational-ingestion plan` | Approved architecture and M4A/M4B/M4C boundary |
| 2 | `f6fc84296e0fceb74a033e3931ee555672c9ca79` | `feat(ingestion): add operational ingestion contracts` | Eleven schemas, frozen contracts/models, canonical sealing, errors, and secret checks |
| 3 | `1fb78d9e8d4ebd4cbdb5244c0cd6cafc6c39ec90` | `feat(ingestion): add verified checkpoint kernel` | Artifact persistence, transitive verification, kernel orchestration, checkpoint authority and state |
| 4 | `8f5fcb50033b31f974b3a35b6f7fca5769ee8ba9` | `test(ingestion): prove M4A causal invariants` | Focused acquisition, failure, determinism, secret, architecture, and remediation proof |
| 5 | self | `docs(architecture): close M4A` | Implementation evidence and this closure manifest |

The contracts commit was independently compiled and imported before the kernel
commit. The complete public package was independently compiled and imported
after the kernel commit.

## Exact reviewed 30-file inventory

Categories are: A documentation; B schemas; C frozen models/contracts; D
acquisition/artifact persistence; E checkpoint/authority/state; F secret and
failure handling; G focused tests; H closure-remediation regression tests. No
category-I file was found. “Critical” means the path directly establishes or
tests a closure acceptance invariant.

| # | Path | Category | SHA-256 | Purpose | Imports | Direct dependents | Critical |
|---:|---|:---:|---|---|---|---|:---:|
| 1 | `docs/architecture/MILESTONE_4_OPERATIONAL_INGESTION_AND_LIVE_SOURCE_PLAN.md` | A | `806591d57b8b3baca47c369e21c67e0061eb0360d447788c58a7ba0eae15425f` | Canonical M4 plan and clarified determinism/identity semantics | None | Implementation and closure reports | Yes |
| 2 | `docs/architecture/MILESTONE_4A_OPERATIONAL_INGESTION_KERNEL_IMPLEMENTATION_REPORT.md` | A | `8b033252f909fdca4c00ff18903f80bf7e5ce69ca9ddb793620a5d358cd84179` | Implementation, audit, and verification evidence | None | This closure report | Yes |
| 3 | `schemas/operational_ingestion/acquisition_boundary.v1.schema.json` | B | `f0ff7952b7e6e39cdde44e4f2aa6e65cdfccd0dc86bac666601b3d913bee43d7` | Sealed acquisition coverage and capture/observation linkage | None | Kernel artifacts; remediation and determinism tests | Yes |
| 4 | `schemas/operational_ingestion/acquisition_intent.v1.schema.json` | B | `d96befb256e6dd4c129ad4201a16e2fd219573a7780be790736818bbf9d26134` | Source-neutral acquisition intent contract | None | Models; acquisition/model tests | Yes |
| 5 | `schemas/operational_ingestion/acquisition_session.v1.schema.json` | B | `272ec16120a55db2b94297c4e10b214dfd460a19d9319b9bd3f341e56c0cc071` | Immutable operational session contract | None | Kernel; acquisition/model tests | Yes |
| 6 | `schemas/operational_ingestion/bounded_source_material.v1.schema.json` | B | `3f90f4ae4fb98e655f864ea424ef0268db1d3e41c03ee1b61aa0aba00b0986d2` | Canonical semantic material and complete assembly evidence | None | Artifact/checkpoint verification; remediation tests | Yes |
| 7 | `schemas/operational_ingestion/checkpoint_candidate.v1.schema.json` | B | `3a4e1b3f6fdd2a97df1398e45228a5b1ae97b71eb7cef19b43727d10dd135f13` | Eligible-uncommitted candidate contract | None | Checkpoint implementation/tests | Yes |
| 8 | `schemas/operational_ingestion/checkpoint_commit_receipt.v1.schema.json` | B | `f81ee9fbdaf1e8f557261999e2f8ac172e7d6d3550eae2bbda76ad0624ee0de5` | Exclusive immutable checkpoint commit receipt | None | Checkpoint implementation/tests | Yes |
| 9 | `schemas/operational_ingestion/completed_manifest_verifier_authority.v1.schema.json` | B | `730bd27137397324aa5858e8a024baeec80abc27a48f1a01bc99a9f65d533ea9` | Narrow completed-manifest verification authority | None | Checkpoint implementation; remediation tests | Yes |
| 10 | `schemas/operational_ingestion/ingestion_failure_receipt.v1.schema.json` | B | `39bee9b8d14761e4dbaacc95cdbb8dad12dab18fdbcec5625d0036464d41d251` | Sanitized immutable failure receipt | None | Kernel; failure tests | Yes |
| 11 | `schemas/operational_ingestion/observation_index.v1.schema.json` | B | `9f4b3b5fbf76201a5ddbd204c14361890590f0e5a8284f887a1bc38f2484cdd0` | Content-addressed observation state and provenance reference | None | Artifacts/checkpoints; determinism/remediation tests | Yes |
| 12 | `schemas/operational_ingestion/page_capture_receipt.v1.schema.json` | B | `e229a7e98c878203293be1346197a026e3b24b2c611e32576747370e40f2ff82` | Exact body, request, response-schema, and chain receipt | None | Artifacts/kernel; acquisition/remediation tests | Yes |
| 13 | `schemas/operational_ingestion/request_attempt_receipt.v1.schema.json` | B | `01120a1ad67c47319720591a4f6087b3c24d83a547ffcf829c8bc7f16e8c98e0` | Secret-safe request-attempt provenance | None | Kernel; acquisition/secret tests | Yes |
| 14 | `signal_agent/operational_ingestion/__init__.py` | E | `413c9a1b7b058b3cdb173fe7a05e9f74c6a65391ba53eb598ea39fe51d9cbb45` | Governed public programmatic surface | Local artifacts, canonical, checkpoints, errors, kernel, models | All focused tests and callers | Yes |
| 15 | `signal_agent/operational_ingestion/artifacts.py` | D | `d23b0ea5c8e931b7e5c6f1a3ee28ccc584fb4eada76a15acb1731870af5435c9` | Immutable persistence, hash domains, and transitive assembly verification | Stdlib; local canonical, errors, models, secrets | Kernel, checkpoints, focused tests | Yes |
| 16 | `signal_agent/operational_ingestion/canonical.py` | C | `beccf91dbfc6149024417eecd736f3a93e13c561d8dee83b3bb8ab70c151c6e3` | Canonical JSON, validation, hashes, IDs, and seals | Stdlib; local errors | Models, artifacts, checkpoints, kernel, tests | Yes |
| 17 | `signal_agent/operational_ingestion/checkpoints.py` | E | `9805e622627b68546a5068125f5f2106930db2ea083dcf9c06d390ff2dff6304` | Completion verification, byte binding, authority, candidates, commits, and state resolution | Stdlib; local artifacts, canonical, errors, models, secrets | Kernel, public facade, checkpoint/remediation tests | Yes |
| 18 | `signal_agent/operational_ingestion/contracts.py` | C | `46e5bc6ef668d1e2631feda3d6fa46f5be73ab24139b73b7eb5d2e43bb95717d` | Source/domain-neutral transport, page, processor, and failure protocols | Stdlib; local models | Kernel, fake processor fixtures | Yes |
| 19 | `signal_agent/operational_ingestion/errors.py` | F | `bc60d345ef0b401151425947fd0c407849ea028a50879de020c4ba5f09a5a7e3` | Typed fail-closed error taxonomy | None | All production modules and tests | Yes |
| 20 | `signal_agent/operational_ingestion/kernel.py` | E | `dec838d418c2d4337da9d34f9fa8d2b283cbe0111ccc808326dadb7b3bdf1f7a` | Source-neutral acquisition/session orchestration and failure injection | Stdlib; local artifacts, canonical, checkpoints, contracts, errors, models | Public facade and focused tests | Yes |
| 21 | `signal_agent/operational_ingestion/models.py` | C | `be825835b1e568bb13ffdf2a679fac00ab87dcd2b6dc302b0a62b89d81c2d72c` | Frozen validated value models and result/reference types | Stdlib; local canonical, errors, secrets | Contracts, artifacts, checkpoints, kernel, tests | Yes |
| 22 | `signal_agent/operational_ingestion/secrets.py` | F | `4978b7914840cf8213b4a350fe64b25a39dddcd9aa92f41556652731bcce3bc5` | Recursive prohibited-key/value and byte-level secret boundary | Stdlib; local errors | Models, artifacts, checkpoints, secret tests | Yes |
| 23 | `tests/operational_ingestion/__init__.py` | G | `5b4b1c1d82c781daffd06dad4603bca6cd2757f0b3278e755c6ed1121d2728de` | Focused-test package marker | None | Pytest collection | No |
| 24 | `tests/operational_ingestion/conftest.py` | G | `b5d0f571dc589e0111d4ea95f672aed9bd1a9df9785bb020a607c9a4ce88e401` | Fake governed processor, deterministic clock, histories, and fixtures | Stdlib, pytest, M4A public/canonical APIs | All focused tests | Yes |
| 25 | `tests/operational_ingestion/test_acquisition_contracts.py` | G | `4f5f165abb5a91e6dcf15dc28087165449dbd4f491b845a294922e1d72f5dd5c` | Acquisition/session/capture/boundary contract proof | Pytest, M4A public APIs, fixtures | Pytest gate | Yes |
| 26 | `tests/operational_ingestion/test_checkpoint_contract.py` | G | `118668e6c803f0f4c50c8f3ba7ab003cddcca869f16df332025da5a73cc98a65` | Candidate, authority, commit, replay, and predecessor proof | Pytest, M4A public/artifact/canonical/model APIs, fixtures | Pytest gate | Yes |
| 27 | `tests/operational_ingestion/test_closure_audit_remediation.py` | H | `88d88210a6fd86c8f3a1ff43beebd05d8ef882f7be8c10dc7e8cf3bfea73823e` | Negative proof for all four former closure findings | Pytest, M4A public/artifact/canonical/checkpoint APIs, fixtures | Pytest gate and closure audit | Yes |
| 28 | `tests/operational_ingestion/test_failure_semantics.py` | G | `5997eb42ea351b28a661eb857366c28c70320fe259580077f81c832fbed6b7a5` | Failure-stage isolation and prior-current preservation | Pytest, jsonschema, M4A public APIs, fixtures | Pytest gate | Yes |
| 29 | `tests/operational_ingestion/test_models_and_determinism.py` | G | `89726b7ea69809941de48259608d4bf45003d9265b0e76d3a438764b2fec7738` | Frozen/schema, semantic-vs-transport, replay-byte, and index-reference proof | Pytest, jsonschema, M4A public APIs, fixtures | Pytest gate | Yes |
| 30 | `tests/operational_ingestion/test_secret_and_architecture.py` | G | `582bdad31b0b7536725d75ad8e0880868a5bdca3dd7b8371bdb76a875bef28d4` | Secret canaries, protected hashes, imports, and out-of-scope proof | Stdlib, pytest, M4A public/artifact APIs, fixtures | Pytest gate and static audit | Yes |

The closure report itself is additive closure metadata and is intentionally not
part of the reviewed implementation inventory.

## Accepted causal chain

```text
exact captured bodies
  -> sealed PageCaptureReceipts
  -> sealed complete AcquisitionBoundary
  -> canonical BoundedSourceMaterial
  -> exact preservation byte binding
  -> completed governed detached manifest
  -> eligible-uncommitted CheckpointCandidate
  -> completed-manifest verifier authority
  -> actual current predecessor
  -> exclusive CheckpointCommitReceipt
```

Candidate construction and final commit each re-open and revalidate their
dependencies. A previous in-memory success result is insufficient.

### Assembly evidence

`AcquisitionBoundary + BoundedSourceMaterial = complete accepted assembly evidence.`

Together they seal source instance, adapter/source, acquisition cycle, prior
checkpoint, ordered captures, separate capture and observation set hashes,
coverage and lower/upper observation boundaries, terminal proof, assembly
policy ID/version/hash, bounded-material ID/path/content hash, all required
counts, and observation-to-capture provenance. Model construction,
serialization, JSON schemas, and verification agree. No standalone assembly
receipt exists or is required.

### Transitive capture verification

`verify_assembly_evidence`, `verify_completed_run`, candidate creation, and
commit-time verification traverse boundary -> every page-capture receipt ->
every captured body. They verify receipt seals and IDs; actual body path, size,
and SHA-256; response schema; request and continuation hashes; predecessor
chain; session and capture-set membership; ordered capture identity;
`capture_set_hash`; `observation_set_hash` linkage; terminal proof; and boundary
hash. Mutated/missing bodies, substituted receipts, wrong size/hash, wrong
receipt hash, broken chain links, and nonmember captures all fail closed before
candidate eligibility.

### Exact preservation byte binding

The completion verifier reads and hashes the actual canonical bounded-material
file and actual preserved source. Eligibility requires:

```text
SHA256(actual bounded material)
  == declared bounded-material file/content hash
  == preservation receipt source_sha256
  == SHA256(actual preserved source bytes)
```

It also verifies the bounded descriptor and completed-manifest artifact
descriptor. Changed bounded bytes, wrong source hash, correct reference with
wrong bytes, wrong descriptor, or different preserved bytes all block the
candidate.

### Commit-time authority and current predecessor

Commit independently revalidates the candidate schema/hash and
`eligible_uncommitted` state, full dependency chain, supported verifier
authority type/version, exact candidate and completion-policy binding, required
assertions, both nonauthorization flags, and the candidate predecessor against
the resolved current commit. Root is valid only without a current checkpoint.
The predecessor/successor slot is exclusively created. Exact replay returns the
verified existing bytes; stale, divergent, unsupported, wrongly bound, or losing
concurrent successors fail without changing history.

## Determinism and identity

- Transport determinism: identical acquisition script, responses, and clock
  produce identical attempt, capture, session, and boundary artifacts.
- Evidence determinism: approved retry histories/page partitions with the same
  canonical observations produce the same observation set, bounded semantic
  material, processor effects, and governed downstream outputs.
- `capture_set_hash` identifies exact ordered acquisition provenance.
- `observation_set_hash` identifies canonical observation semantics and excludes
  retry timing, session ID, page ordinal, page partition, and attempt history.
- Exact capture references remain immutable provenance but do not enter semantic
  observation identity.
- An immutable artifact whose stable ID excludes a local timestamp verifies and
  returns the existing artifact on exact replay. Divergent bytes under the same
  ID are rejected.
- Candidate and checkpoint replay are byte-safe.
- Checkpoints carry an observation-index ID/path/hash reference. The immutable,
  content-addressed index may link to a prior index and does not inline an
  ever-growing history into each checkpoint.

## Secret and dependency boundaries

Recursive structured scans and byte canaries reject access/refresh tokens, API
keys, client secrets, cookies/session material, authorization headers, signed
URLs, secret query parameters, OAuth codes, PKCE verifiers, secret-bearing error
bodies, and unsanitized exception content before persistence. Failure receipts
contain structured sanitized codes, not raw exception bodies.

The package imports no networking, provider, authentication, relationship,
identity-reconciliation, campaign, messaging, publishing, CLI, scheduler,
daemon, webhook, or UI module. Protected Milestone 1–3 production code has no
reverse import into M4A. There is no upstream write or external-action path.

## Four closure-audit findings and remediation

1. **Incomplete assembly evidence:** repaired by jointly sealing all required
   identities, boundaries, counts, policies, hashes, terminal state, and
   observation provenance in the boundary/material pair and aligning schemas,
   construction, and validation.
2. **Non-transitive capture trust:** repaired by reopening every capture receipt
   and body at candidate and commit eligibility, validating exact bytes and the
   complete predecessor/membership chain.
3. **Reference-only preservation trust:** repaired by hashing the actual bounded
   and preserved bytes and requiring equality with every receipt/manifest claim.
4. **Commit trust in stale eligibility:** repaired by independently revalidating
   verifier authority, policy/candidate assertions, the actual current
   predecessor, and the exclusive successor slot at commit time.

The 51-test remediation file and the complete 115-test M4A gate exercise the
required positive and negative cases. A separate one-off missing-body audit also
failed closed before candidate creation.

## Verification manifest

### Before Git mutation in the implementation worktree

| Gate | Command summary | Result | Time |
|---|---|---:|---:|
| Four-finding remediation | `python -m pytest -q tests/operational_ingestion/test_closure_audit_remediation.py` | 51 passed | 127.93 s |
| Complete M4A | `python -m pytest -q tests/operational_ingestion` | 115 passed | 209.48 s |
| Existing closure scope | Reviewed 216-test command with the live-registry node deselected | 216 passed, 1 deselected | 206.33 s wall |
| Existing witnesses | LinkedIn + interaction-event + Milestone 3 witness nodes | 3 passed | 11.06 s wall |
| Compilation | `python -m compileall` over the M4A package/tests | passed | — |
| Static boundaries | protected hashes, forbidden imports/reverse imports, scope, whitespace | 9 exact; 0; 0; 0; 0 | — |

### From the committed closure implementation

| Gate | Command summary | Result | Time |
|---|---|---:|---:|
| M4A focused gate | `python -m pytest -q tests/operational_ingestion` | 115 passed | 232.52 s pytest / 267.36 s wall |
| Existing closure scope | Canonical test/fixture root + closure code via `PYTHONPATH`, `--import-mode=importlib`, one documented deselection | 216 passed, 1 deselected | 214.34 s pytest / 217.16 s wall |
| Existing witnesses | Same provenance-preserving mode for all three witness nodes | 3 passed | 12.20 s pytest |
| Invariant deselection check | Six supported invariant nodes with the live-registry node deselected | 6 passed, 1 deselected | 5.25 s |
| Protected-hash regression node | Closure-root M4A architecture test | 1 passed | 0.25 s |

The exact reviewed closure command is the Milestone 3 216-test list with:

```text
--deselect=tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry
```

The excluded node remains the documented closure-only repository-global
invariant whose required uncommitted modules are intentionally not part of this
branch.

## Protected Milestone 1–3 hashes

| Protected path/artifact | SHA-256 | Result |
|---|---|---|
| Generic relationship runner | `967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44` | Exact |
| LinkedIn adapter | `44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d` | Exact |
| Interaction-event adapter | `76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589` | Exact |
| Relationship-record schema | `32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1` | Exact |
| LinkedIn witness | `00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02` | Exact |
| Interaction-event witness | `823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d` | Exact |
| Milestone 3 witness | `80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b` | Exact |
| Existing Gmail reader | `35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1` | Exact |
| Corpus-import CLI | `5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7` | Exact |

Neither Milestone 2 witness was regenerated. The Milestone 3 witness was not
regenerated or modified.

## Repository-root provenance limitation

The host Git configuration has `core.autocrlf=true`. Initial linked-worktree
checkout converted raw bytes in fourteen protected/base JSON or CSV paths even
though Git's normalized diff was empty. This caused raw-hash and witness drift.
Those paths were mechanically byte-aligned from the clean canonical base
worktree; an explicit-path index refresh produced zero staged changes and zero
semantic diff. This was a checkout correction, not a repository change.

The Milestone 3 witness also derives identity artifacts from a LinkedIn source
receipt containing the resolved absolute fixture path. Consequently its fixed
witness is bound to the canonical Milestone 3 repository root. Direct execution
from the new closure path legitimately produced different sealed run/candidate
IDs even after all source bytes matched. No M3 code, fixture, or witness was
changed. The final legacy and witness gates therefore resolve the unchanged
tests and fixtures from `E:\signal_agent-milestone2-closure` while importing
production code from `E:\signal_agent-milestone4a-closure` through
`PYTHONPATH` and pytest importlib mode. This preserves the witness's recorded
provenance and still exercises the closure code.

This is an inherited repository-provenance limitation, not M4A behavior. A
future witness format could explicitly parameterize or exclude the absolute
source path, but changing Milestone 3 is outside M4A.

## Original implementation-shape deviations

- `kernel.py` remains an internal layout choice rather than a new generic runner.
- Retry-policy execution/configuration remains deferred because M4A has no live
  transport or retry consumer.
- The complete sealed `AcquisitionBoundary + BoundedSourceMaterial` pair replaces
  a standalone assembly-receipt file.

No additional implementation-shape deviation was accepted during closure.

## Final scope and status

- The accepted implementation inventory contains exactly 30 additive files;
  this report is the sole additional closure-metadata file.
- Compilation passes.
- Forbidden imports: zero.
- Reverse imports from protected production paths: zero.
- Out-of-scope implementation files: zero.
- New trailing-whitespace findings: zero.
- Secret-boundary canary failures: zero accepted secrets.
- Networking/authentication/provider/Gmail/CLI/scheduler/daemon/webhook/UI work:
  none.
- M4B: not started.
- M4C: not started.
- Push, merge, tag, PR, and worktree deletion: not performed.
- Final closure worktree status: required to be clean after this report commit
  and recorded by the external handoff.

M4A is closed at the programmatic kernel boundary only. M4B requires separate
review and explicit approval.
