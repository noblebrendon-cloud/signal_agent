# Milestone 4B Offline Simulated Operational Source — Implementation Report

## Status and recovery point

Milestone 4B is implemented as an additive, offline consumer of the protected
Milestone 4A kernel.

- Base SHA: `95d642ef2b520e13c6eeeff4c1648594cf8adc0a`
- Base branch: `codex/milestone4a-closure`
- Implementation branch: `codex/milestone4b-simulator`
- Linked worktree: `E:\signal_agent-milestone4b-simulator`
- Git state: additive and untracked; nothing staged or committed
- M4C status: not started

The pre-implementation base audit proved a clean local/remote base, 115 M4A
tests, 216 inherited closure tests with one documented deselection, three exact
existing witnesses, the protected hashes, and zero M4A networking/provider
implementation.

## Architecture

```text
versioned deterministic script
-> SimulatedOperationalTransport
-> SimulatedRemoteInteractionSource
-> persisted M4A attempts and exact captures
-> verified M4A acquisition boundary and bounded material
-> finite SimulatedOperationalEvidenceAdapter
-> unchanged generic relationship runner
-> detached operational completed manifest
-> M4A transitive verifier
-> observation index, checkpoint candidate, verifier authority
-> exclusive M4A checkpoint commit
```

`simulator.py` is explicitly simulator-specific. It does not present itself as
a provider-neutral remote client and imports no relationship, network, Gmail,
GitHub, authentication, scheduler, daemon, CLI, or UI implementation. The
source-specific composition root is the only bridge to relationship processing.

The generic relationship runner, both Milestone 2 adapters, every relationship
schema, identity-reconciliation implementation, the existing Gmail reader, the
corpus CLI, and all Milestone 1–3 witnesses remain byte-identical.

## Retry policy and transport behavior

`simulated_operational_retry_policy` version `1.0.0` defines retryable outcome
classes, three maximum attempts, bounded exponential backoff, SHA-256-derived
deterministic simulation jitter, a 30-second virtual acquisition window, and
bounded provider-like `Retry-After` handling. The injected virtual clock never
sleeps.

Attempts, retry delays, capture timestamps, page boundaries, cursors, and
provider request metadata remain operational provenance. They do not enter
source observation identity, `observation_set_hash`, normalized record identity,
or the transport-independent downstream semantic projection.

## Fixture and identity model

The base script has three pages:

- P1: R1/v1 and R2/v1.
- P2: one deterministic 429, successful retry, repeated R2/v1, and R3/v1.
- P3: R2/v2 and an explicit R3 tombstone.

Alternate scripts add R4/v1 and partition the same canonical observations
differently. The no-retry script carries the same semantic observations through
a different attempt history.

Clear R1–R4 labels are limited to deterministic synthetic capture/bounded
evidence. Source-local identity is HMAC-SHA-256 protected before neutral
normalization. Observation identity derives from protected source identity and
canonical content, never page number, cursor, session, attempt, retry count, or
capture order.

Exact protected-key plus content-hash replay creates no second observation.
Every valid capture locator is retained by the acquisition boundary. A changed
content hash creates an immutable new observation and, when simulator version
ordering proves a unique predecessor, records predecessor and supersession
links. Explicit tombstones are immutable observations; absence creates no
deletion semantics.

## Transport and semantic determinism

Identical script, virtual clock, policies, and transport outcomes produce
byte-identical operational and governed trees.

The alternate partition proof produces different `capture_set_hash` values and
the same `observation_set_hash`. The no-retry proof likewise changes exact
transport provenance while preserving the observation set and governed semantic
projection. Exact page bodies and attempt/capture receipts remain immutable even
when equivalent acquisitions legitimately have different operational trees.

The accepted witness values are:

- `capture_set_hash`: `sha256:2916a8c2a9004836885e432c20624e661246b6043183eea625affa711060ffa3`
- `observation_set_hash`: `sha256:8bd2fc6f86a0e980e9431898519bc1f66aac2aab69b2121bfbb61b5810456db6`
- semantic projection hash: `sha256:02161d8a5b1825d71a16ae1bcb6470233bdfb7f319f7ddac04c3604104c9107c`

## Recovery proofs

### Verified partial reuse

Interruptions after P1 and P2 leave no checkpoint. A newly constructed
coordinator reconstructs the partial acquisition from sealed attempt receipts,
capture receipts, and exact stored response bodies. It re-parses source
semantics, verifies request and continuation identities, capture topology,
response metadata, observation references, body hashes/sizes, and the prior
capture chain before continuing. The final run has zero lost observations, zero
duplicate normalized effects, and the same five-observation history.

### Conservative reacquisition

When partial reuse is discarded, a new session starts from the prior committed
checkpoint, reacquires overlapping evidence, deterministically deduplicates it,
and commits only after a new completed manifest verifies. The prior checkpoint
remains current throughout the abandoned partial session.

An uncommitted cursor is therefore an optimization, not evidence of committed
progress.

## Causal and transitive verification

M4B exercises the accepted M4A chain without shortcuts:

```text
capture body
-> PageCaptureReceipt
-> AcquisitionBoundary
-> BoundedSourceMaterial
-> exact preserved bytes and source receipt
-> completed governed manifest and artifact hashes
-> observation-index reference
-> checkpoint candidate
-> completed-manifest verifier authority
-> current predecessor
-> exclusive successor commit
```

Corrupting a stored capture body after downstream processing blocks candidate
creation. Corrupting bounded material after sealing also blocks candidate
creation. A candidate that was valid before a competing successor commits is
rejected at commit time. Exact candidate and checkpoint replays verify existing
bytes and return the immutable artifact rather than recreating it with a new
timestamp.

Failures after transport, attempt persistence, capture persistence, boundary or
bounded creation, preservation, normalization, downstream output, manifest
creation/verification, index creation, candidate creation, authority creation,
or immediately before commit never advance the checkpoint. A completed manifest
and authority left before a commit failure can be reverified and committed
without rerunning governed processing.

## Secret boundary

Successful responses containing Authorization/Bearer material, API keys,
refresh tokens, client secrets, signed URLs, secret query parameters, session
cookies, OAuth codes, PKCE verifiers, or secret-bearing error content fail
closed before capture. An exception canary is omitted from persisted failure
receipts. Tests scan every persisted artifact and the witness: persisted canary
count is zero.

## Scenario matrix

| # | Scenario | Result |
|---:|---|---|
| 1 | Successful root acquisition | Passed through committed root checkpoint |
| 2 | Multi-page acquisition | P1/P2/P3 sealed |
| 3 | Explicit terminal page | Required and verified |
| 4 | Exact page replay | Stable request, response bytes, and observations |
| 5 | Duplicate record across pages | One effect, two capture locators |
| 6 | Simulated 429 | Attempt receipt retained |
| 7 | Policy retry success | Deterministic 1,200 ms virtual delay |
| 8 | Permanent 403 | Failed closed; no checkpoint |
| 9 | Generic transport interruption | Sanitized failure; no checkpoint |
| 10 | Interruption after P1 | Prior/root state retained |
| 11 | Interruption after P2 | Prior/root state retained |
| 12 | Verified partial reuse | Disk reconstruction and full revalidation passed |
| 13 | Conservative reacquisition | Same observations, no duplicate effects |
| 14 | Stable partition | Deterministic tree |
| 15 | Alternate partition | Different capture topology |
| 16 | Equivalent observation set | Same semantic hash and projection |
| 17 | Changed record | R2/v2 retained |
| 18 | Multiple immutable versions | R2/v1 and R2/v2 both retained |
| 19 | Explicit tombstone | R3 tombstone with predecessor |
| 20 | Absence without tombstone | No deletion inferred |
| 21 | Malformed success response | Failed closed |
| 22 | Secret-bearing success response | Failed closed before capture |
| 23 | Repeated continuation | Rejected |
| 24 | Longer pagination cycle | Rejected |
| 25 | Empty terminal page | Accepted |
| 26 | Empty nonterminal page | Rejected |
| 27 | Maximum page bound | Enforced |
| 28 | Maximum record bound | Enforced |
| 29 | Maximum response-byte bound | Enforced |
| 30 | Capture persistence failure | No checkpoint |
| 31 | Boundary sealing failure | No checkpoint |
| 32 | Bounded-material failure | No checkpoint |
| 33 | Preservation failure | No checkpoint |
| 34 | Normalization failure | No checkpoint |
| 35 | Downstream failure | No checkpoint |
| 36 | Output before detached-manifest failure | Output identifiable; no checkpoint |
| 37 | Invalid completed manifest | Verification blocks checkpoint |
| 38 | Candidate creation failure | Prior checkpoint current |
| 39 | Verifier-authority failure | Commit rejected |
| 40 | Checkpoint commit failure | Candidate/authority recoverable; prior current |
| 41 | Exact checkpoint replay | Existing bytes returned |
| 42 | Divergent successor | Exclusive slot rejects fork |
| 43 | Stale candidate | Commit-time predecessor/slot check rejects it |
| 44 | Completed manifest without commit | Reverified and safely committed |
| 45 | Independent identical run | Byte-identical trees |
| 46 | Different retry history | Same observations and semantic output |

## Deterministic M4B witness

`tests/fixtures/operational_ingestion/compatibility_witness_v1.json` seals 29
artifacts spanning the root intent, session, four attempts, three exact bodies,
three capture receipts, boundary, bounded material, preservation, five normalized
effects, downstream analysis/packets, both detached manifests, observation index,
candidate, authority, and committed root checkpoint.

- Witness file SHA-256: `7f36276e2526d645f5ccc3914ba72a0059525b9bb433e29479ba3da9c6b68e6b`
- Sealed `witness_hash`: `sha256:61d6fc4a89ce891299bd1bad896aa55dfba8f701c9e54a9b98a8750503c2b3b1`
- Existing witness files modified or regenerated: 0

Interruption, exact replay, alternate partition equivalence, and output-before-
manifest failure are companion focused assertions rather than additional data in
the fixed successful tree.

## Verification manifest

| Gate | Result | Pytest time |
|---|---:|---:|
| Final M4B focused gate | 72 passed | 205.65 s |
| Protected M4A-only gate | 115 passed | 177.06 s |
| Inherited M2/M3 closure gate | 216 passed, 1 documented deselection | 223.15 s |
| Existing LinkedIn, interaction-event, and M3 witnesses | 3 passed exact | 11.86 s |
| New M4B witness | 1 passed exact, included in M4B gate | Included above |
| Governed failure matrix after final test cleanup | 7 passed | 36.64 s |
| Compilation | Passed | — |
| New JSON documents | 6/6 parsed | — |
| New source trailing whitespace | 0 | — |
| Forbidden imports/reverse imports | 0 | — |
| Out-of-scope additive paths | 0 | — |
| Persisted secret canaries | 0 | — |

The inherited deselection remains
`tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry`.
The 216-test gate used the documented M3-root fixture/test provenance with
`PYTHONPATH` pointed at this M4B worktree and pytest importlib mode. This preserves
the inherited absolute-path-bound Milestone 3 witness while exercising the
unchanged production code in this worktree.

## Protected hashes

| Protected item | SHA-256 |
|---|---|
| Generic relationship runner | `967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44` |
| LinkedIn adapter | `44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d` |
| Interaction-event adapter | `76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589` |
| Relationship-record schema | `32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1` |
| LinkedIn witness | `00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02` |
| Interaction-event witness | `823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d` |
| Milestone 3 witness | `80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b` |
| Identity-reconciliation policy/schema/package tree (16 files) | `907910c356002da4d0b600123ed267031d936d6dd67a8f6a5e37ddf69a8dd3c5` |
| Existing Gmail reader | `35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1` |
| Corpus-import CLI | `5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7` |
| Complete M4A delta tree (31 files) | `53deba75f109b071c1eebf300510f163f1ad779c3ff6543df466f52129cc11be` |
| M4A implementation report | `8b033252f909fdca4c00ff18903f80bf7e5ce69ca9ddb793620a5d358cd84179` |
| M4A closure report | `79185858befb23d51532a5d43cd2e3a207e4441a7e8a1cf4d47da06f77c1a737` |

## Exact additive inventory

| Path | SHA-256 |
|---|---|
| `config/operational_ingestion/retry_policy_v1.json` | `21dd942a1e646d5b283c5bdeaaad262c03b5e26999ccabdecab2d2125c2c1ee8` |
| `signal_agent/corpus_import/simulated_operational/__init__.py` | `60baa3aecdfc671a1dc5adf2aa2bdf26bf94035f7241f2dd286f66f2656c163e` |
| `signal_agent/corpus_import/simulated_operational/adapter.py` | `33588745ba70488356afab42e31fe3dc1360db51f7c80304a7fd29c7189b0452` |
| `signal_agent/operational_ingestion/simulator.py` | `7f16e571e650dadf2b68f793d72e00f79fb8a7ceae1a7777282b4a37a63d8bf9` |
| `signal_agent/relationship_signals/simulated_operational_pipeline.py` | `715c48896b6ffd0c98dd5221d34736dc1c4469503e12805c90369f543ebc1edf` |
| `tests/fixtures/operational_ingestion/base_no_retry_script.json` | `2386c545f57b8163624b9911a6dfc28dd6d473775aa3b56afb7b7f89be4386bd` |
| `tests/fixtures/operational_ingestion/base_script.json` | `be35d1e535c5268401c0d2079e8bec624625ba6f9464b821de30765590dbe04f` |
| `tests/fixtures/operational_ingestion/compatibility_witness_v1.json` | `7f36276e2526d645f5ccc3914ba72a0059525b9bb433e29479ba3da9c6b68e6b` |
| `tests/fixtures/operational_ingestion/partition_a_script.json` | `30867df2359658e49b9bc9a6b7c71e51a6f3f8c260938b1609a7811cedc96ef8` |
| `tests/fixtures/operational_ingestion/partition_b_script.json` | `8e38f0a5b2a79a09e1e378e658e3e4c8ea2b134dc9f0332ceb3c60297e91ae98` |
| `tests/operational_ingestion/simulated_test_support.py` | `68790c417071cb018375f2f38676d7dfce89710b98225913e2cfdd056c713a87` |
| `tests/operational_ingestion/test_architecture_and_failures.py` | `93f61d5ce59f7d4d4d23ae18397480117030fef39e0139f98498f183166cce96` |
| `tests/operational_ingestion/test_operational_compatibility_witness.py` | `c5b972e5538faf44cc3f0b1c7ce9d797b90f74d8d17d60af696509c49b48e3a7` |
| `tests/operational_ingestion/test_simulated_acquisition.py` | `5be82f52aad0e2ed5789e21f5f00ce8a4a0d7bf15c3fde4f1f12d9afbb8d3c41` |
| `tests/operational_ingestion/test_simulated_relationship_slice.py` | `38fa2b57d86bbcfdbc4b6672e24181a7c69ce10c7fafef0305dffb79b21af671` |
| `docs/architecture/MILESTONE_4B_SIMULATED_OPERATIONAL_SOURCE_IMPLEMENTATION_REPORT.md` | Self-referential; final file hash is reported in the review handoff |

The test-support module is the only additive path beyond the expected shape. It
centralizes fixed clocks, keys, fixture loading, tree hashing, and composition
invocation so scenario tests exercise the same production path.

## Deviations and limitations

- No new JSON Schema files were needed. M4B emits the accepted M4A artifact
  schemas and existing relationship schema; the retry and script documents are
  closed, versioned contracts validated by strict loaders and focused tests.
- The finite relationship run is written directly beneath its governed run root;
  the operational completed manifest has a distinct receipt filename and does
  not replace the generic runner's detached manifest.
- Partial recovery is deliberately bounded to an explicit incomplete session and
  reconstructs from immutable captures. Store-wide scheduling or automatic
  session discovery is not introduced.
- The simulator protection key is injected test material. M4B adds no key store,
  authentication lifecycle, or credential implementation.
- The inherited Milestone 3 witness remains absolute-path-bound; it was verified
  through the documented provenance mode and not repaired.
- There is no compaction, mutable current-state projection, live source,
  networking, provider API, scheduler, daemon, CLI, UI, or upstream write path.

## Completion statement

M4B demonstrates that an unreliable deterministic source can paginate, retry,
resume, reacquire, deduplicate, preserve changed history and tombstones, pass
through the unchanged relationship runner, and advance a checkpoint only after
the complete M4A causal chain verifies. Source mutations, automatic merges,
silent gaps, premature checkpoint commits, persisted secrets, unexplained test
failures, protected-path drift, networking, provider production code, and M4C
work are all zero.
