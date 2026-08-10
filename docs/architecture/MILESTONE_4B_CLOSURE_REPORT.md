# Milestone 4B Closure Report

## Closure decision

Milestone 4B is accepted and closed as an additive, offline simulated
operational source that exercises the protected Milestone 4A kernel. The
closure adds no live provider, networking, authentication, scheduler, daemon,
CLI, UI, upstream write, or Milestone 4C behavior.

- Canonical M4A base: `95d642ef2b520e13c6eeeff4c1648594cf8adc0a`
- M4A closure branch/worktree: `codex/milestone4a-closure` at
  `E:\signal_agent-milestone4a-closure`
- Implementation branch/worktree: `codex/milestone4b-simulator` at
  `E:\signal_agent-milestone4b-simulator`
- Closure branch/worktree: `codex/milestone4b-closure` at
  `E:\signal_agent-milestone4b-closure`
- Implementation-report SHA-256:
  `79f22eb72d7d9a41343c729143be7a7fb85f206fbfd27c6ede9efa4bc1e8e3ac`
- Reviewed 16-file inventory digest:
  `4cfc19cb82477b155e9866137fbe0257c962dac994410104cfcb7bff692c591d`
- M4C status: not started

The final closure SHA is the documentation commit containing this report and
is recorded in the external closure handoff. A file cannot contain the SHA of
the commit that contains that file without changing the commit and therefore
invalidating the embedded value. This is the same self-reference boundary used
by earlier milestone closure reports.

## Commit boundary

| Commit | Message |
|---|---|
| `765c84a3e6f413f5eadbb4ca18a838f9eeb85023` | `feat(ingestion): add deterministic simulated transport` |
| `911a3081736252eb975ff9c56bb60eb981fc479c` | `feat(relationships): add simulated operational source` |
| `9436187a501f3bb2679f652511e99a35c88475b2` | `test(ingestion): prove operational recovery semantics` |
| `9798acb689bf73597171df5a3138f1035008c216` | `test(ingestion): lock M4B compatibility witness` |
| Documentation commit | `docs(architecture): close M4B`; SHA reported externally because it contains this report |

Every commit was staged with an explicit path list. No protected M4A path was
staged or committed. There was no broad staging, merge, push, tag, pull request,
or worktree deletion.

## Audited 16-file inventory

The inventory digest is constructed as follows:

1. Take the exact 16 reviewed relative POSIX paths.
2. Sort them using PowerShell `Sort-Object`, whose case-insensitive ordering is
   equivalent to Unicode case-fold ordering for this inventory.
3. For every path, compute SHA-256 over the raw file bytes and append
   `path=lowercase_sha256\n`.
4. Concatenate those lines as UTF-8 without a BOM.
5. SHA-256 the concatenated bytes.

The resulting digest is
`4cfc19cb82477b155e9866137fbe0257c962dac994410104cfcb7bff692c591d`.

| Path | SHA-256 | Category |
|---|---|---|
| `config/operational_ingestion/retry_policy_v1.json` | `21dd942a1e646d5b283c5bdeaaad262c03b5e26999ccabdecab2d2125c2c1ee8` | A — retry policy |
| `docs/architecture/MILESTONE_4B_SIMULATED_OPERATIONAL_SOURCE_IMPLEMENTATION_REPORT.md` | `79f22eb72d7d9a41343c729143be7a7fb85f206fbfd27c6ede9efa4bc1e8e3ac` | I — implementation evidence |
| `signal_agent/corpus_import/simulated_operational/__init__.py` | `60baa3aecdfc671a1dc5adf2aa2bdf26bf94035f7241f2dd286f66f2656c163e` | D — source public surface |
| `signal_agent/corpus_import/simulated_operational/adapter.py` | `33588745ba70488356afab42e31fe3dc1360db51f7c80304a7fd29c7189b0452` | C/D — parser, assembler, adapter |
| `signal_agent/operational_ingestion/simulator.py` | `7f16e571e650dadf2b68f793d72e00f79fb8a7ceae1a7777282b4a37a63d8bf9` | B — deterministic transport/coordinator |
| `signal_agent/relationship_signals/simulated_operational_pipeline.py` | `715c48896b6ffd0c98dd5221d34736dc1c4469503e12805c90369f543ebc1edf` | E — source composition root |
| `tests/fixtures/operational_ingestion/base_no_retry_script.json` | `2386c545f57b8163624b9911a6dfc28dd6d473775aa3b56afb7b7f89be4386bd` | F — retry-equivalence fixture |
| `tests/fixtures/operational_ingestion/base_script.json` | `be35d1e535c5268401c0d2079e8bec624625ba6f9464b821de30765590dbe04f` | F — reference fixture |
| `tests/fixtures/operational_ingestion/compatibility_witness_v1.json` | `7f36276e2526d645f5ccc3914ba72a0059525b9bb433e29479ba3da9c6b68e6b` | H — exact witness |
| `tests/fixtures/operational_ingestion/partition_a_script.json` | `30867df2359658e49b9bc9a6b7c71e51a6f3f8c260938b1609a7811cedc96ef8` | F — partition fixture A |
| `tests/fixtures/operational_ingestion/partition_b_script.json` | `8e38f0a5b2a79a09e1e378e658e3e4c8ea2b134dc9f0332ceb3c60297e91ae98` | F — partition fixture B |
| `tests/operational_ingestion/simulated_test_support.py` | `68790c417071cb018375f2f38676d7dfce89710b98225913e2cfdd056c713a87` | G — deterministic test composition support |
| `tests/operational_ingestion/test_architecture_and_failures.py` | `93f61d5ce59f7d4d4d23ae18397480117030fef39e0139f98498f183166cce96` | G — architecture/failure verification |
| `tests/operational_ingestion/test_operational_compatibility_witness.py` | `c5b972e5538faf44cc3f0b1c7ce9d797b90f74d8d17d60af696509c49b48e3a7` | H — witness verifier |
| `tests/operational_ingestion/test_simulated_acquisition.py` | `5be82f52aad0e2ed5789e21f5f00ce8a4a0d7bf15c3fde4f1f12d9afbb8d3c41` | G — transport/recovery verification |
| `tests/operational_ingestion/test_simulated_relationship_slice.py` | `38fa2b57d86bbcfdbc4b6672e24181a7c69ce10c7fafef0305dffb79b21af671` | G — governed relationship verification |

No category J or out-of-scope item was found. The closure report itself is a
seventeenth closure-only documentation path and is intentionally outside the
audited implementation digest.

### Imports, dependents, and closure participation

| Item | Principal imports/inputs | Direct dependents | Witness | Closure-critical |
|---|---|---|---:|---:|
| Retry policy | Closed JSON contract | Simulator loader and focused tests | Yes | Yes |
| Implementation report | Audited results | Closure review/report | No | Yes |
| Simulated package `__init__` | `.adapter` exports | Composition root and tests | Yes | Yes |
| Simulated adapter | Standard library, neutral evidence contracts/models, M4A boundary verification | Composition root and tests | Yes | Yes |
| Simulator kernel consumer | Standard library plus accepted M4A acquisition, persistence, verifier, candidate, authority, resolver, and commit APIs | Composition root and tests | Yes | Yes |
| Relationship composition root | Simulator source, adapter, unchanged relationship analyzer/packet/manifest/generic runner | Test support and slice tests | Yes | Yes |
| Base script | Versioned synthetic operations | Test support and witness | Yes | Yes |
| No-retry script | Same semantic observations with alternate attempt history | Retry-independence test | No | Yes |
| Partition scripts A/B | Same canonical observations with alternate topology | Partition-independence tests | No | Yes |
| Witness JSON | Fixed 29-artifact inventory and stable values | Witness verifier | Yes | Yes |
| Test support | Fixed clock/key, fixture loader, real production composition | Four focused test modules | Yes | Yes |
| Architecture/failure tests | Pytest, test support, protected paths, M4A APIs for adversarial calls | Closure gates | No | Yes |
| Acquisition tests | Pytest, test support, production simulator | Closure gates | No | Yes |
| Relationship-slice tests | Pytest, test support, production composition root | Closure gates | No | Yes |
| Witness test | Pytest, test support, witness JSON | Witness gate | Yes | Yes |

The helper never writes a successful M4A completion artifact directly. It
invokes the same production coordinator/composition path used by every accepted
scenario.

## Architecture and use of M4A

The audited successful path is:

```text
SimulatedOperationalTransport
-> simulator source semantics
-> M4A intent/session/attempt persistence
-> M4A exact page-body and capture persistence
-> M4A transitive capture verification
-> M4A AcquisitionBoundary
-> M4A BoundedSourceMaterial
-> simulated-source preservation and normalization
-> unchanged generic relationship runner
-> detached completed operational manifest
-> M4A observation index reference
-> M4A checkpoint candidate
-> M4A completed-manifest verifier authority
-> M4A current-predecessor resolution
-> M4A exclusive checkpoint commit
```

Static and runtime traces found no shadow candidate, authority, checkpoint,
commit, or current-state implementation. The production simulator calls the
accepted M4A persistence APIs and `OperationalIngestionKernel`; the adapter
calls M4A assembly verification; and the composition root calls the unchanged
generic relationship runner. Tests use M4A checkpoint functions directly only
to exercise adversarial replay/conflict cases.

Protected reverse imports are zero: the M4A kernel, LinkedIn adapter,
interaction-event adapter, identity-reconciliation package, and generic runner
do not import M4B.

## Retry policy and base source

The versioned retry policy allows three attempts, bounded exponential backoff,
SHA-256-derived deterministic simulator jitter, a 30-second virtual acquisition
window, and bounded provider-like `Retry-After` handling. The injected virtual
clock never sleeps.

The accepted source sequence is:

- P1: R1/v1, R2/v1, then `cursor-1`.
- P2: repeated R2/v1 and R3/v1; the first attempt is a deterministic 429 and
  the retry succeeds, then `cursor-2`.
- P3: R2/v2 and an explicit R3 tombstone, then terminal end-of-stream.
- R4/v1 exists only in the two approved alternate-partition fixtures.

Stable source identity excludes page number, cursor ordinal, attempt/session
identity, capture order, and retry count. Clear R1–R4 labels exist only inside
synthetic capture/bounded evidence and are HMAC-protected before neutral
normalization.

## Transport versus semantic determinism

Transport determinism is exact: identical script, responses, policies, virtual
clock, and outcomes produce byte-identical operational and governed trees.

Evidence determinism is topology-independent: approved page partitions or retry
histories representing the same canonical observations produce the same
observation set, normalized effects, and governed semantic projection. Exact
attempts, captures, sessions, timing, page boundaries, and `capture_set_hash`
remain immutable operational provenance and may differ.

The reference witness seals:

- `capture_set_hash`:
  `sha256:2916a8c2a9004836885e432c20624e661246b6043183eea625affa711060ffa3`
- `observation_set_hash`:
  `sha256:8bd2fc6f86a0e980e9431898519bc1f66aac2aab69b2121bfbb61b5810456db6`
- semantic projection hash:
  `sha256:02161d8a5b1825d71a16ae1bcb6470233bdfb7f319f7ddac04c3604104c9107c`

Independent four-run comparison proved:

| Comparison | Expected different | Required equal | Result |
|---|---|---|---|
| Partition A vs B | Exact pages/captures, capture receipts, page topology, `capture_set_hash` | Canonical observations, `observation_set_hash`, five unique normalized effects, semantic projection | Passed |
| Retried base vs no-retry | Attempt receipts, retry timing/history, exact operational tree, `capture_set_hash` | Canonical observations, `observation_set_hash`, normalized effects, semantic projection | Passed |

Exact capture identity and semantic observation identity therefore remain
separate. Exact capture references are retained in provenance but do not enter
semantic evidence identity.

## Duplicate, version, tombstone, and absence proofs

- Repeated R2/v1 creates one canonical observation/version and one normalized
  effect while retaining both valid capture locators.
- R2/v2 keeps the same protected stable source identity, has a different
  canonical content hash, creates a new immutable observation, and names R2/v1
  as its unique predecessor. R2/v1 bytes remain unchanged.
- R3/v1 followed by its explicit tombstone creates a distinct immutable
  deletion observation with capture provenance and predecessor linkage.
- Omission of an earlier record from a later page/batch creates no deletion or
  tombstone evidence.

The reference run has six captured source records, five canonical observations,
one suppressed duplicate, two changed observations, one tombstone, five unique
normalized record IDs, and zero duplicate normalized effects.

## Recovery and checkpoint proofs

### Verified partial reuse

After interruption following P1 or P2, a new coordinator reconstructs and
transitively verifies the sealed attempt/capture/body chain, continuation
identity, response metadata, body hashes/sizes, observation references, and
prior-capture topology before continuing. The prior checkpoint remains current
until the final commit. The completed history has no loss or duplicate effect.

### Conservative reacquisition

When partial continuation is unsafe or discarded, a new session begins from the
prior committed checkpoint, reacquires overlap, deterministically deduplicates,
and commits only after a new completed manifest verifies. Uncommitted cursor
state never implies progress; there are zero silent gaps and duplicate effects.

### Non-advancement matrix

No checkpoint advances after a successful request, one or multiple captures,
boundary sealing, bounded material, preservation, normalization, downstream
output, incomplete/invalid manifest, candidate without authority, stale
candidate, or failed commit. Advancement requires all of:

```text
verified completed detached manifest
+ eligible immutable candidate
+ valid completed-manifest verifier authority
+ actual current predecessor
+ exclusive successor commit
```

Injected failures after transport, attempt persistence, capture persistence,
boundary/bounded creation, preservation, normalization, downstream output,
manifest creation/verification, index creation, candidate creation, authority
creation, and immediately before commit leave the prior checkpoint current.
Exact commit replay returns the fully verified existing immutable artifact;
divergent or stale successors fail closed.

## Transitive corruption proof

Independent post-processing corruption attempts produced these fail-closed
results before checkpoint advancement:

| Corruption | Result |
|---|---|
| Stored capture body | `capture_body_hash_mismatch` |
| Modified and resealed capture receipt | `capture_id_derivation_mismatch` |
| Bounded material bytes | Artifact unreadable/rejected |
| Preservation receipt source SHA | Completed-manifest receipt-reference mismatch |
| Preserved source bytes | Preserved-source byte mismatch |
| Completed-manifest dependency | Completed-manifest artifact-hash mismatch |
| Candidate made stale by a competing predecessor commit | Exclusive commit rejected |

This proves that M4B does not bypass transitive capture verification,
preservation-byte binding, detached-manifest verification, authority, current
predecessor resolution, or exclusive successor creation.

## Failure, pagination, and secret matrix

The 72-test M4B gate covers 46 accepted scenarios: root and multipage success;
terminal handling; exact replay; duplicate capture provenance; deterministic
429/retry; permanent 403 and transport interruption; P1/P2 restart; verified
partial reuse; conservative reacquisition; same/different partition and retry
histories; changed versions; tombstone and absence; malformed/secret-bearing
successes; repeated cursors and cycles; empty terminal/nonterminal pages;
page/record/byte bounds; persistence, boundary, bounded-material, preservation,
normalization, downstream, manifest, candidate, authority, and commit failures;
exact replay; divergent/stale successors; and commit retry after a verified
manifest.

Secret-boundary cases include Authorization/Bearer material, API keys, refresh
tokens, client secrets, signed URLs and secret query parameters, session
cookies, OAuth codes, PKCE verifiers, secret-bearing bodies, and exception
canaries. Production rejects them before eligible capture or sanitizes failure
receipts. The independent scan covered 113 produced persisted files and found
zero canaries; the committed 72-test gate repeated the boundary assertions.

## Witness audit

The new witness seals 29 artifacts: root intent/session, four attempts including
the deterministic 429, three exact bodies, three capture receipts, boundary,
bounded material, preservation, five normalized effects, downstream analysis
and packets, both detached manifests, observation index, checkpoint candidate,
verifier authority, and committed root checkpoint.

- Witness file SHA-256:
  `7f36276e2526d645f5ccc3914ba72a0059525b9bb433e29479ba3da9c6b68e6b`
- Sealed `witness_hash`:
  `sha256:61d6fc4a89ce891299bd1bad896aa55dfba8f701c9e54a9b98a8750503c2b3b1`
- Fixed clock: `2026-08-10T12:00:00Z`
- Absolute implementation paths: 0
- Credential/personal-data canaries: 0
- Existing witnesses regenerated: 0

R4 is absent from the base and no-retry trees and occurs exactly once in each
alternate partition tree.

## Verification manifest

### Independent pre-closure audit

| Gate | Result | Pytest time |
|---|---:|---:|
| M4B focused | 72 passed | 210.64 s |
| Protected M4A | 115 passed | 220.86 s |
| Inherited M2/M3 closure | 216 passed, 1 documented deselection | 205.62 s |
| Existing three witnesses | 3 passed exact | 11.95 s |
| M4B witness | 1 passed exact | 4.65 s |

### Committed production/test tree

| Gate | Result | Pytest time |
|---|---:|---:|
| M4B focused | 72 passed | 258.11 s |
| Protected M4A | 115 passed | 221.18 s |
| Inherited M2/M3 closure | 216 passed, 1 documented deselection | 510.15 s |
| Existing three witnesses | 3 passed exact | 13.47 s |
| M4B witness | 1 passed exact | 5.41 s |
| Compilation | Passed | — |
| JSON documents | 6/6 parsed | — |
| New trailing whitespace | 0 | — |
| Forbidden production imports | 0 | — |
| Protected reverse imports | 0 | — |
| Persisted secret canaries | 0 | — |

The inherited gate used the canonical Milestone 3 test/fixture root at
`E:\signal_agent-milestone2-closure`, `--import-mode=importlib`, and
`PYTHONPATH=E:\signal_agent-milestone4b-closure`. The sole deselection is:

`tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry`

This preserves the accepted absolute-path-bound Milestone 3 witness provenance
while exercising the closure worktree's production code.

The exact committed-code commands were:

```powershell
# M4B: four simulated test modules
E:\signal_agent\.venv\Scripts\python.exe -m pytest -q `
  tests/operational_ingestion/test_architecture_and_failures.py `
  tests/operational_ingestion/test_operational_compatibility_witness.py `
  tests/operational_ingestion/test_simulated_acquisition.py `
  tests/operational_ingestion/test_simulated_relationship_slice.py

# M4A: the six protected M4A modules
E:\signal_agent\.venv\Scripts\python.exe -m pytest -q `
  tests/operational_ingestion/test_acquisition_contracts.py `
  tests/operational_ingestion/test_checkpoint_contract.py `
  tests/operational_ingestion/test_closure_audit_remediation.py `
  tests/operational_ingestion/test_failure_semantics.py `
  tests/operational_ingestion/test_models_and_determinism.py `
  tests/operational_ingestion/test_secret_and_architecture.py

# Inherited closure: canonical M3 root, current production through PYTHONPATH,
# pytest importlib mode, and the documented live-registry deselection.
# The explicit path list selects 216 tests from corpus_import,
# identity_reconciliation, relationship/importer, and repository-health files.
```

## Protected boundaries

| Protected item | SHA-256/result |
|---|---|
| Generic relationship runner | `967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44` |
| LinkedIn adapter | `44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d` |
| Interaction-event adapter | `76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589` |
| Relationship-record schema | `32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1` |
| LinkedIn witness | `00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02` |
| Interaction-event witness | `823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d` |
| Milestone 3 witness | `80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b` |
| Identity-reconciliation policy/schema/package tree | `907910c356002da4d0b600123ed267031d936d6dd67a8f6a5e37ddf69a8dd3c5` |
| Complete M4A delta tree, 31 files | `53deba75f109b071c1eebf300510f163f1ad779c3ff6543df466f52129cc11be` |
| M4A closure report | `79185858befb23d51532a5d43cd2e3a207e4441a7e8a1cf4d47da06f77c1a737` |
| Existing Gmail reader | `35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1` |
| Corpus-import CLI | `5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7` |

Unauthorized protected drift, source mutations, automatic reconciliation,
automatic merges, and changes to existing witnesses are all zero.

## Deviations and technical debt

- No new JSON Schema files were required. The simulator emits accepted M4A and
  relationship artifacts; the closed retry/script documents are strictly
  validated by loaders and focused tests.
- `simulated_test_support.py` is the only additive helper beyond the core
  source/config/test/report shape. It centralizes deterministic composition and
  does not implement successful completion artifacts.
- The inherited Milestone 3 witness remains absolute-path-bound. It was
  verified through its canonical test/fixture root and was not modified.
- The implementation report's pre-commit Git-state language is preserved as
  historical implementation evidence; this report records the closure state.
- A fresh Windows linked-worktree checkout initially materialized 25 protected
  JSON/CSV files with CRLF bytes despite unchanged Git blobs. Raw bytes were
  restored from the clean canonical M4A worktree and the index stat cache was
  refreshed with zero staged content. The initial diagnostic run consequently
  reported raw-hash/witness failures; serial reruns after restoration passed
  72/72 and 115/115. No protected blob or M4B reviewed file changed.
- There is no compaction, mutable current-state projection, live source,
  networking, provider API, authentication, scheduler, daemon, webhook,
  background worker, CLI, UI, source registry, plugin discovery, or upstream
  write path.

## Final state

The closure diff consists of the exact reviewed 16-file implementation plus
this closure-only report. The closure worktree is clean after the five causal
commits. The original M4A and M4B implementation worktrees were not cleaned,
mutated, or removed. No push was performed. M4C was not started.

