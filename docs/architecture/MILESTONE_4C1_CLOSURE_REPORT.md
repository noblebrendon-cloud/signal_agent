# M4C1 Gmail History Offline Source Adapter Closure Report

## Closure verdict

M4C1 is locally closed on the dedicated `codex/milestone4c1-closure`
branch. The current 27-file implementation was independently rebuilt from the
implementation worktree, byte-audited, tested before Git mutation, copied into
an isolated closure worktree, and committed with explicit path staging.

M4C1 remains synthetic/offline.

M4C1 does not prove universally gap-free live bootstrap.

M4C1 does not authorize mailbox-wide live Gmail History acquisition.

M4C2 was not started.

No push, merge, tag, pull request, witness regeneration, live Gmail access,
network access, OAuth flow, credential load, Google client execution, or Gmail
write was performed.

## Repository identity

- Authorized M4C1 base: `fa26dc3a7e20cc8deaf9ac99792933ce723a9b45`
- M4B parent: `f804f41e92ca87777213ac1450f64c4549955b39`
- Implementation branch: `codex/milestone4c1-gmail-history-offline`
- Implementation worktree: `E:\signal_agent-milestone4c1-gmail-history-offline`
- Closure branch: `codex/milestone4c1-closure`
- Closure worktree: `E:\signal_agent-milestone4c1-closure`
- Final audited implementation commit before this report:
  `014adef4178adc8b7866ec38043a5fc17bc241e6`
- Final closure SHA: the `docs(architecture): close M4C1` commit containing this
  report. Its exact object ID is recorded in the external final audit handoff,
  because embedding a Git commit's own SHA in its tree is self-referential and
  changes that SHA.

The last item is a reporting-mechanics deviation only. It does not change the
tree, tests, inventory, or closure decision.

## Fresh 27-file inventory

The canonical manifest encodes each sorted record as:

```text
<sha256>  <bytes>  <physical-lines>  <category>  <path>\n
```

- Files: 27
- Total bytes: 250,561
- Physical lines: 6,032
- Manifest bytes: 4,272
- Inventory SHA-256:
  `cfaf46b744646ba5ab86fb10320ce94a690535af17d3d75fbce596896b761495`
- Implementation-report SHA-256:
  `df9d42a99003406e2d88efcd11468d877edaf61a4844ed80202fe064f83b7764`
- Implementation-report bytes/lines: 33,095 / 525

| Path | Bytes | Lines | Category | SHA-256 | Purpose |
|---|---:|---:|---|---|---|
| `config/operational_ingestion/gmail_history_metadata_v1.json` | 1,598 | 63 | policy | `97066f55afba0525abb85c060b74461dd888aca7911455f1830f4e6c00a5e7b1` | Metadata allowlist, bounds, source protection, and denied authorizations |
| `docs/architecture/MILESTONE_4C1_GMAIL_HISTORY_OFFLINE_IMPLEMENTATION_REPORT.md` | 33,095 | 525 | implementation-report | `df9d42a99003406e2d88efcd11468d877edaf61a4844ed80202fe064f83b7764` | Implementation rationale, limitations, and verification record |
| `schemas/operational_ingestion/gmail_history_source_receipt.v1.schema.json` | 1,475 | 39 | schema | `12240c7cbc88d7bc4887d67d2a4e164df2071f47d645e10b2672917886d8cd14` | Sealed Gmail source receipt contract |
| `schemas/operational_ingestion/gmail_target_label_projection.v1.schema.json` | 1,623 | 39 | schema | `95f04de071dd8999d99dfa97475ccc5021073135ef773ef239be3d18c2643628` | Immutable target-label projection contract |
| `signal_agent/corpus_import/gmail_history/__init__.py` | 1,057 | 38 | production-source | `12affb5c35dc168e0482202f0b07a83df900375b88f40ae46b91346fd9405b9b` | Gmail package exports |
| `signal_agent/corpus_import/gmail_history/adapter.py` | 21,558 | 546 | production-source | `35f2db64643439248e66837c086eb36fa8ebb235dbf46c279968279f22ac6eba` | Assembly verification, preservation, protection, and neutral normalization |
| `signal_agent/corpus_import/gmail_history/canonicalization.py` | 41,308 | 915 | production-source | `5691fb409f5880363dfcf594a9e9068d6fe4ec1322398382c842bf433748b047` | Fixture validation, pagination, minimization, and provider observations |
| `signal_agent/corpus_import/gmail_history/models.py` | 4,336 | 154 | production-source | `2c4629493ffe535b5b73177b9bf5f76501f20fdc03d1e979d8f93d84dceb6f92` | Immutable Gmail models and typed continuations |
| `signal_agent/corpus_import/gmail_history/projection.py` | 15,987 | 388 | production-source | `b005c2b4988fa836d0918995bfc66da34c7b67dc420ca37765f0211d794d3253` | Predecessor-bound TARGET_LABEL state projection |
| `signal_agent/relationship_signals/gmail_history_pipeline.py` | 20,101 | 544 | production-integration | `bc6aa6a7cd2401503ad9075418360d68c5064d117f6b34b72defc9cefc29e785` | Real M4A-kernel and unchanged relationship-runner composition |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_coverage_unknown.json` | 1,241 | 36 | synthetic-fixture | `0f9c18c9c4e798e4d609e4429e7a213c9196b02b9f80b8d4a2b1fb46d0c61565` | Ambiguous bootstrap coverage |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_empty_mailbox.json` | 731 | 23 | synthetic-fixture | `507c6b44568acbb08f27fcacfd9a39f52b7a6400c52647a58ae7148e73666206` | Unsupported entirely empty mailbox |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_empty_target.json` | 1,233 | 36 | synthetic-fixture | `eb13ca44d057d65b12b1c642992dba5fecefe78aedd913d804f60ef86514c46d` | Empty target and bounded unfiltered anchor lookup |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_nonempty.json` | 1,623 | 49 | synthetic-fixture | `6c4b6da23211de334e91ccdf9d84e30a0376ed3f808a969727e2b0e6455aae9f` | Nonempty target bootstrap |
| `tests/fixtures/operational_ingestion/gmail_checkpoint_expired.json` | 607 | 18 | synthetic-fixture | `d984035f387f088bde49757c4879bd8d5f06978395924cd37bc10e85293524ff` | Expired history continuation |
| `tests/fixtures/operational_ingestion/gmail_history_compatibility_witness_v1.json` | 16,493 | 354 | witness | `d47fc21cd057029bf9f500af473a0cf1e0ef81c13bc58d2032d1ea9688920504` | Exact M4C1 compatibility witness |
| `tests/fixtures/operational_ingestion/gmail_incremental_partition_a.json` | 3,310 | 90 | synthetic-fixture | `d81363c942bb068ead7613c6320f86baa604c548c31a01d80d276b8e542c789e` | Incremental partition A |
| `tests/fixtures/operational_ingestion/gmail_incremental_partition_b.json` | 3,571 | 100 | synthetic-fixture | `5beb2c32d22cff3004d6351a2921a8fcee54cfe2c172091f6df3934114d7d8d1` | Semantically equivalent partition B |
| `tests/fixtures/operational_ingestion/gmail_recovery.json` | 1,656 | 49 | synthetic-fixture | `65a7ad47f01ebf3cab84dbfbaaa32923b0cd2da363597c9d1f01544de5b2973f` | Explicit bounded recovery |
| `tests/fixtures/operational_ingestion/gmail_recovery_coverage_unknown.json` | 1,067 | 30 | synthetic-fixture | `ace107d82f1343e6d64f16cd08c3e39a21b88a997f4ac3e7db37ea057329a6b6` | Ambiguous recovery coverage |
| `tests/operational_ingestion/gmail_test_support.py` | 3,258 | 102 | test-support | `e245f84d9852c50977676559d729f9fd643aca9caad42ea4f60627c5707faa70` | Deterministic fixture and run harness |
| `tests/operational_ingestion/test_gmail_history_architecture.py` | 17,252 | 469 | focused-test | `3e1307ce78a851f53b2acda68189b961a6e01246913ea92667e51c392c1d8a70` | Protected imports/hashes, recursive schema subset, and privacy guards |
| `tests/operational_ingestion/test_gmail_history_compatibility_witness.py` | 5,235 | 139 | focused-test | `a87b345fc6eb791ee9921b745557be549b7df6a9b559b4c095925373975716f4` | Exact witness replay |
| `tests/operational_ingestion/test_gmail_history_contracts.py` | 20,461 | 490 | focused-test | `7b47fe694159ae53c78f157f94cb632dd08af84b0b84ef4cf519eda81d7847f0` | Provider contract, pagination, minimization, and secret rejection |
| `tests/operational_ingestion/test_gmail_history_failures.py` | 6,114 | 174 | focused-test | `c9b6d04edf0d8e5f1695026cfb1a2f07e2e43a7730596722423b11f3347fc9cb` | Kernel/processor non-advancement boundaries |
| `tests/operational_ingestion/test_gmail_history_governance.py` | 5,694 | 151 | focused-test | `2cca4f24194b7ff23fca5fcc95428206b262de79247194b8d9f0efd691b0a636` | Replay, transitive corruption, verifier authority, and predecessor checks |
| `tests/operational_ingestion/test_gmail_history_projection.py` | 18,877 | 471 | focused-test | `744cd9b3788ca5c4ac90b1bfb8e922213e71bda2fad830c11068ec69939b3e31` | Bootstrap, projection, recovery, and equivalence semantics |

## Causal commits

Every commit used explicit path staging. The staged path set was compared with
the intended set before each commit.

| SHA | Message | Scope |
|---|---|---|
| `302ac5245f3aac95395daf5d377096d8fbeef04a` | `feat(gmail): add offline history source contracts` | Policy, two schemas, models, exports, canonical acquisition contract |
| `9fa213ddbd1cefc3281c4acf1ade93d5336dde5c` | `feat(gmail): add target-label projection and governed pipeline` | Adapter, immutable projection, M4A composition |
| `9f58f54372cff16f3c873b1a858af0fb8f89c4a6` | `test(gmail): prove bootstrap and history semantics` | Test support, nine synthetic cases, five focused modules |
| `9260bea18528005ce32474c96d45f125f0632741` | `test(gmail): lock M4C1 compatibility witness` | Pinned witness and exact verifier |
| `014adef4178adc8b7866ec38043a5fc17bc241e6` | `docs(architecture): document M4C1 implementation` | Audited implementation report |

## Local schema validator remediation and independent proof

The repository does not declare `jsonschema`; changing shared dependencies or
installing a package solely for this additive acceptance test was not
authorized. The local validator is deliberately limited to the exact schema
subset used by the two M4C1 schemas and is not a general JSON Schema
implementation.

The supported types are `object`, `array`, `string`, `integer`, and `null`.
The recursively enforced keywords are `required`, `properties`,
`additionalProperties`, `items`, `const`, `pattern`, `minLength`, and
`minimum`. `$schema`, `$id`, and `title` are metadata. `format` is an
annotation; no format checker is claimed.

The earlier validator recursed only for object item schemas and incorrectly
accepted `semantic_identity_excludes: [42]`. The remediation routes every
array item through the same recursive value validator. Independent adversarial
execution produced:

| Case | Result |
|---|---|
| Valid string array | Accepted |
| `[42]` | Rejected |
| Mixed string/integer array | Rejected |
| Object-item constraint violation | Rejected |
| Nested object -> array -> primitive violation | Rejected |
| Nested object -> array -> object violation | Rejected |
| Missing required property | Rejected |
| Unknown property under `additionalProperties: false` | Rejected |
| Wrong `const` | Rejected |
| `pattern` mismatch | Rejected |
| `minLength` violation | Rejected |
| `minimum` violation | Rejected |
| Invalid date-time string where only `format` annotates | Accepted, as documented |

The implementation report truthfully records the dependency rationale,
supported subset, recursive behavior, original defect, remediation,
regressions, annotation behavior, and non-general scope.

## Provider contract and semantic projection proof

### Authoritative scope

Incremental continuity accepts only unfiltered
`users.history.list(startHistoryId=..., pageToken=..., maxResults=...)`.
`labelId` and `historyTypes` are detected first and fail with
`gmail_filtered_history_forbidden`; other unknown fields use the generic
endpoint-specific rejection. No `getProfile.historyId` route exists.

Typed `messagesAdded`, `messagesDeleted`, `labelsAdded`, and `labelsRemoved`
events become distinct canonical provider observations. Generic
`History.messages` does not create duplicate effects. Provider event identity
is content-derived and exact duplicates are idempotent.

### TARGET_LABEL projection

The projection loads and verifies the prior projection seal, source,
projection policy, and protected label reference. Each transition binds the
prior state/transition, provider observation identity/hash, protected message
identity, and policy identity. Prior bytes are rechecked before preservation,
so historical states are never edited in place.

- OUTSIDE/UNKNOWN plus a relevant add enters TARGET_LABEL.
- INSIDE plus `labelsRemoved(TARGET_LABEL)` becomes `left_target_label` and
  OUTSIDE.
- INSIDE plus explicit `messagesDeleted` becomes
  `mailbox_deleted_while_in_target_scope` and DELETED.
- Unknown relevance is recorded unresolved without emitting an effect.
- Unrelated mailbox events remain provider evidence only.
- Snapshot absence never creates deletion or label-departure evidence.

The M4A `observation_set_hash` remains the canonical provider-observation hash.
The separate target-label projection hash binds provider evidence, prior
projection reference/state, target-label reference, and projection policy
identity/version. Capture page boundaries, attempt history, and retry history
are explicitly outside semantic identity.

## Pagination, bootstrap, incremental history, and recovery

Supported nonempty TARGET_LABEL bootstrap and recovery require an exact,
bounded `users.messages.list(labelIds=[TARGET_LABEL])` token chain ending in a
response without `nextPageToken`. Dangling, missing, wrong, repeated, cyclic,
malformed, over-bound, or falsely terminal scripts fail closed.
`resultSizeEstimate` is never completion proof. Each listed message requires
an exact `users.messages.get(format=METADATA, metadataHeaders=[From])` result.

Empty TARGET_LABEL is distinct: after proving the target list terminal and
empty, one unfiltered `users.messages.list(maxResults=1)` lookup may derive a
message history anchor. It does not enumerate or claim the mailbox complete and
does not create target membership. An entirely empty mailbox remains
unsupported in this lane.

Bootstrap concurrency ambiguity is `coverage_unknown`; it does not claim
complete history, infer deletion, or become checkpoint eligible.

Incremental history enforces exact page-token chaining, a terminal mailbox
`historyId`, non-contiguous but numerically ordered history records, page and
record bounds, and typed distinction between page tokens and mailbox history
continuations. A page token can never become the checkpoint candidate.

Expired/out-of-range history produces an explicit expiry failure and preserves
the current predecessor. Recovery is a separate bounded operation that
exhausts TARGET_LABEL membership, derives supported metadata/anchor evidence,
deduplicates overlap, and preserves prior projection/checkpoint evidence.
Recovery absence creates no tombstone; ambiguous recovery is
`coverage_unknown`.

## Equivalence, replay, and corruption proof

Alternate valid page partitions produce different `capture_set_hash` values
but equal provider `observation_set_hash`, projection, normalized semantic
effects, and governed result. Alternate allowed retry histories alter attempt
receipts/timing only, not provider or projection semantics.

Same provider event plus same predecessor produces the same transition
identity and no duplicate semantic effect. Repeated pages/events are
idempotent; cycles fail closed; exact checkpoint replay returns immutable
existing bytes; divergent successor/predecessor state fails.

Negative tests prove fail-closed behavior for page-body corruption, metadata
body corruption, PageCaptureReceipt corruption, bounded-material corruption,
preserved-source corruption/SHA mismatch, manifest dependency corruption,
missing verifier authority, stale predecessor, and failed/divergent commit.

## Real M4A causal chain and checkpoint non-advancement

The Gmail entry point loads only synthetic provider-shaped fixtures, builds
M4A request attempts and captured pages, instantiates the real
`OperationalIngestionKernel`, and calls `run_from_captured_pages`. The adapter
invokes M4A transitive `verify_assembly_evidence`, recomputes the provider
observation-set hash, preserves exact bounded bytes through the existing
preservation API, and verifies preservation binding. Normalization delegates
to the unchanged relationship runner. The completed manifest binds the
bounded material, projection, source receipt, preserved bytes, relationship
manifest, and governed artifacts.

M4A alone creates/verifies the observation index, checkpoint candidate,
completed-manifest verifier authority, current predecessor, and exclusive
commit. Gmail-local code has no candidate/authority/commit bypass and only
reads current checkpoint state to validate expiry predecessor state.

The prior checkpoint remains current after partial acquisition, terminal-ID
receipt, canonicalization, projection, boundary/material creation,
preservation, normalization, downstream output, incomplete/invalid manifest,
missing/invalid authority, stale predecessor, processor/kernel failure, and
failed commit. Only the complete M4A authority chain advances it.

## Metadata minimization, identity protection, and isolation

The admitted top-level metadata fields are exactly `id`, `threadId`,
`labelIds`, `historyId`, `internalDate`, and `payload`; payload contains only a
single nonempty `From` header. `threadId` preserves event/message linkage,
`historyId` provides message-derived continuity evidence, and `internalDate`
provides the only admitted event-time basis.

`snippet`, `raw`, bodies, MIME body data, parts, attachments, `attachmentId`,
Subject, arbitrary headers, recipient collections, body-bearing unknown
payload, and credential-like fields fail closed. Static review found eight
unique fixture email values; all use `@synthetic.invalid`, and `From` is the
only header name.

Clear sender identity remains only in synthetic preserved/source-specific
evidence. Neutral relationship output uses Gmail-specific HMAC identifiers
under namespace `gmail_history_source_identifier.v1` and version
`gmail_history_identifier_token.v1`; no cross-source shared token, automatic
reconciliation, or clear email is emitted.

The existing `signal_agent/media_opportunities/gmail.py` reader is byte-exact,
unimported, uncalled, unwrapped, and not reused for authentication or
credentials. Protected M4A, LinkedIn, interaction-event, and identity modules
contain no reverse import of M4C1.

## Security, privacy, and scope proof

Scoped import and source scans found zero live/network/HTTP/socket/Google
client imports, Gmail write/watch/PubSub/webhook routes, OAuth/credential/token
handling, active CLI/UI/scheduler/daemon/plugin surfaces, reverse imports,
persisted secret-key classes, forbidden provider fields, nonsynthetic fixture
emails, M4C2 paths, or trailing-whitespace lines. The source policy explicitly
denies authentication, live mailbox access, network, OAuth, Gmail write, and
upstream write authority.

All 13 additive JSON files parsed. All 13 additive Python files compiled in
memory without writing bytecode.

## Protected architecture hashes

The protected set was rebuilt from the M4A/M4B closure inventories plus the
required LinkedIn, interaction-event, identity-reconciliation, relationship,
witness, prior Gmail reader, M4 plan, and M4C1 contract-review paths. Git-filtered
blob comparison against the authorized base checked 61 paths with zero drift.

- Protected blob manifest bytes: 6,072
- Protected blob manifest SHA-256:
  `34cd5ceda2728cdb586fce8ee6199a8ce082c4991dec338efe6c44813a0c6eb0`

The following filesystem SHA-256 values were recorded at closure:

| Protected path | SHA-256 | Result |
|---|---|---|
| `docs/architecture/MILESTONE_4_OPERATIONAL_INGESTION_AND_LIVE_SOURCE_PLAN.md` | `dd2370b95715bc45617d6b8b9748e21578cceaddd7e5d9c15cb6ee6258566522` | Exact |
| `docs/architecture/MILESTONE_4A_OPERATIONAL_INGESTION_KERNEL_IMPLEMENTATION_REPORT.md` | `8b033252f909fdca4c00ff18903f80bf7e5ce69ca9ddb793620a5d358cd84179` | Exact |
| `docs/architecture/MILESTONE_4C1_GMAIL_HISTORY_SOURCE_CONTRACT_REVIEW.md` | `74ec88b7b5fa3b6a53fb453955066372429d8e884526fb05a8dccccb886f0e5a` | Exact |
| `schemas/identity_reconciliation/identity_candidate.v1.schema.json` | `3ea2f6435e4c03217665b544b66809a722ee169d47d2b6883003f410dafa02c1` | Exact |
| `schemas/identity_reconciliation/identity_decision_receipt.v1.schema.json` | `4ffc4b5f8a7f2f02cea03ca9eb7f051ffe2823af94037ff981b5ecbd3d2b1a5b` | Exact |
| `schemas/identity_reconciliation/identity_evidence_bundle.v1.schema.json` | `eb339cb02c40d2eadcabcdddca94be4d683a77b841e643dadc7298f36ba0755f` | Exact |
| `schemas/identity_reconciliation/identity_reconciliation_manifest.v1.schema.json` | `081637e513c9f86480d30ae4635b595264cb45c6ffa1c2e8d36929abd8ec73c3` | Exact |
| `schemas/identity_reconciliation/projection_status_receipt.v1.schema.json` | `d7b861ff50d8a9e5b91cb385dc3a7c3ee37573d1007b958610f4d5dff546eabe` | Exact |
| `schemas/identity_reconciliation/reconciled_identity_projection.v1.schema.json` | `cb2f4901a63dee48be2a8be48597a5b5d151a96217a85be5d632bc1a23339e62` | Exact |
| `schemas/operational_ingestion/acquisition_boundary.v1.schema.json` | `6f0a58e7c12ef0243c11485b4a3599ddab8f720379024eae2ec89295a736f1cc` | Exact |
| `schemas/operational_ingestion/acquisition_intent.v1.schema.json` | `c576408037e7b922f73f57090931bb6478b1dd46c722d7b96314951e0890b141` | Exact |
| `schemas/operational_ingestion/acquisition_session.v1.schema.json` | `e56b76aebbbada139d1b419c61889985ee6eb3e84fe8de4cec34aadb13400c7d` | Exact |
| `schemas/operational_ingestion/bounded_source_material.v1.schema.json` | `24608d453f0a5f608e8defc2430b1721029705bd93f48c4a22a5f42c56ff9c7b` | Exact |
| `schemas/operational_ingestion/checkpoint_candidate.v1.schema.json` | `1d239c9e81f8fb4f4ea152eb5cac5e2b43b6ea682fbb3d9e0ede0dff02136a61` | Exact |
| `schemas/operational_ingestion/checkpoint_commit_receipt.v1.schema.json` | `6521f4c8cfb61bf9b2edf19cc57ac425e97b8ad4b8405c7595865a218293080e` | Exact |
| `schemas/operational_ingestion/completed_manifest_verifier_authority.v1.schema.json` | `cb8c599e018ac685930facb84c87434853da2ced6d29c862038192bb9a839b8c` | Exact |
| `schemas/operational_ingestion/ingestion_failure_receipt.v1.schema.json` | `ddbd7d347817add41c5cd062a79797e202f110053e9d8a34ce9315de72f575a9` | Exact |
| `schemas/operational_ingestion/observation_index.v1.schema.json` | `8d10909be51554e61c65786cc93938310e061e35def4e8faf88c2a79adc629f5` | Exact |
| `schemas/operational_ingestion/page_capture_receipt.v1.schema.json` | `b8517c3cb39654d473c62a3e5728eb0ebd25e1a553cbf21d864c75c8333db096` | Exact |
| `schemas/operational_ingestion/request_attempt_receipt.v1.schema.json` | `8f821f732641f454c5d14400fb8ab21ffa108d08125f7c75d01e0f22136d9693` | Exact |
| `schemas/relationship_signals/relationship_record.v1.schema.json` | `246e08373d0231004e7ad4fa99b0148953268ece1085a2086431e585f696149f` | Exact |
| `signal_agent/corpus_import/interaction_events/__init__.py` | `90dfdb1af2608fc33adf9b16f463e9fa0a9536aaf88083f9001b3933791835e8` | Exact |
| `signal_agent/corpus_import/interaction_events/adapter.py` | `76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589` | Exact |
| `signal_agent/corpus_import/interaction_events/importer.py` | `7d7c8dbcffb31e4afa77f44055a2dc77ca77352fa957d0790cd8d03bc8d7c3a8` | Exact |
| `signal_agent/corpus_import/interaction_events/key.py` | `966da3ef1699c3391b4440feae675621f8d5368a09d0ff07a4709575c1b64df7` | Exact |
| `signal_agent/corpus_import/linkedin/__init__.py` | `b9121fcb5ba5edfe31f2160c55f9c7c0d43a1523ce6637c3380071e661d78ca3` | Exact |
| `signal_agent/corpus_import/linkedin/adapter.py` | `44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d` | Exact |
| `signal_agent/corpus_import/linkedin/importer.py` | `216d622f6048d978151fae94c61fab7b5547c2d3ee08347085cfa8b9481d82e9` | Exact |
| `signal_agent/corpus_import/linkedin/key_verifier.py` | `4b67cfd52c6cc53978f4a0e754a584ec3198c6b7ccc245e0f0f5aa92314574ec` | Exact |
| `signal_agent/identity_reconciliation/__init__.py` | `6ccef1f0073c2a9a3b25627fc58835dd57a5c426a5f273f4ecb3c6f71699d3b1` | Exact |
| `signal_agent/identity_reconciliation/artifacts.py` | `6264f3d062574b7bfb45a5df9b42a807985a4507d5e8579aa960481afcbef806` | Exact |
| `signal_agent/identity_reconciliation/candidates.py` | `dda9e35a06a7161adc8ffd6c32f871d52611f1b4b6b73fcc783b7d30ecdbe6c8` | Exact |
| `signal_agent/identity_reconciliation/decisions.py` | `42aa3a187759f6544393378fafee94b36ec30bca520192083a48d4f5426bbd90` | Exact |
| `signal_agent/identity_reconciliation/errors.py` | `b225952cee3e2e96225f2e0a398b16484bb92cb9ab2a2005faa1531c7b8a3bef` | Exact |
| `signal_agent/identity_reconciliation/inputs.py` | `522ae89187b078557bdc461873de8e1e657fe20179f404003dd020607bdf655d` | Exact |
| `signal_agent/identity_reconciliation/models.py` | `794d4e4e0e6011728a7e5af11b911ef303a1e62e6dceb67e13cde2ac327fbbe3` | Exact |
| `signal_agent/identity_reconciliation/policy.py` | `152e291a426e95c5438e032f8206d041ddb16e906338a94a02df04b9a8fc6f9e` | Exact |
| `signal_agent/identity_reconciliation/projections.py` | `3c529d135d25e0f606d3acd4743ff31ecb6178977cfcb1af3ec08dac4883e4e6` | Exact |
| `signal_agent/media_opportunities/gmail.py` | `35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1` | Exact |
| `signal_agent/operational_ingestion/__init__.py` | `413c9a1b7b058b3cdb173fe7a05e9f74c6a65391ba53eb598ea39fe51d9cbb45` | Exact |
| `signal_agent/operational_ingestion/artifacts.py` | `d23b0ea5c8e931b7e5c6f1a3ee28ccc584fb4eada76a15acb1731870af5435c9` | Exact |
| `signal_agent/operational_ingestion/canonical.py` | `beccf91dbfc6149024417eecd736f3a93e13c561d8dee83b3bb8ab70c151c6e3` | Exact |
| `signal_agent/operational_ingestion/checkpoints.py` | `9805e622627b68546a5068125f5f2106930db2ea083dcf9c06d390ff2dff6304` | Exact |
| `signal_agent/operational_ingestion/contracts.py` | `46e5bc6ef668d1e2631feda3d6fa46f5be73ab24139b73b7eb5d2e43bb95717d` | Exact |
| `signal_agent/operational_ingestion/errors.py` | `bc60d345ef0b401151425947fd0c407849ea028a50879de020c4ba5f09a5a7e3` | Exact |
| `signal_agent/operational_ingestion/kernel.py` | `dec838d418c2d4337da9d34f9fa8d2b283cbe0111ccc808326dadb7b3bdf1f7a` | Exact |
| `signal_agent/operational_ingestion/models.py` | `be825835b1e568bb13ffdf2a679fac00ab87dcd2b6dc302b0a62b89d81c2d72c` | Exact |
| `signal_agent/operational_ingestion/secrets.py` | `4978b7914840cf8213b4a350fe64b25a39dddcd9aa92f41556652731bcce3bc5` | Exact |
| `signal_agent/relationship_signals/relationship_pipeline.py` | `967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44` | Exact |
| `tests/fixtures/identity_reconciliation/compatibility_witness_v1.json` | `f6e253dbe0f9c5ab5cad83651d26584a084455abe0b010300b170ffe10c564e1` | Exact |
| `tests/fixtures/interaction_events/compatibility_witness_v1.json` | `823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d` | Exact |
| `tests/fixtures/linkedin_connections/compatibility_witness_v1.json` | `52a581c65a0dde472a7eae4848219e7fda07e874100676a5537633f03ab77702` | Exact |
| `tests/fixtures/operational_ingestion/compatibility_witness_v1.json` | `a9610dd532c71d00e8fa120421660f1d367fa062ab9ca7a77184dab020858796` | Exact |
| `tests/operational_ingestion/__init__.py` | `5b4b1c1d82c781daffd06dad4603bca6cd2757f0b3278e755c6ed1121d2728de` | Exact |
| `tests/operational_ingestion/conftest.py` | `b5d0f571dc589e0111d4ea95f672aed9bd1a9df9785bb020a607c9a4ce88e401` | Exact |
| `tests/operational_ingestion/test_acquisition_contracts.py` | `4f5f165abb5a91e6dcf15dc28087165449dbd4f491b845a294922e1d72f5dd5c` | Exact |
| `tests/operational_ingestion/test_checkpoint_contract.py` | `118668e6c803f0f4c50c8f3ba7ab003cddcca869f16df332025da5a73cc98a65` | Exact |
| `tests/operational_ingestion/test_closure_audit_remediation.py` | `88d88210a6fd86c8f3a1ff43beebd05d8ef882f7be8c10dc7e8cf3bfea73823e` | Exact |
| `tests/operational_ingestion/test_failure_semantics.py` | `5997eb42ea351b28a661eb857366c28c70320fe259580077f81c832fbed6b7a5` | Exact |
| `tests/operational_ingestion/test_models_and_determinism.py` | `89726b7ea69809941de48259608d4bf45003d9265b0e76d3a438764b2fec7738` | Exact |
| `tests/operational_ingestion/test_secret_and_architecture.py` | `582bdad31b0b7536725d75ad8e0880868a5bdca3dd7b8371bdb76a875bef28d4` | Exact |

## Independent pre-commit verification receipts

All Python test commands used `PYTHONDONTWRITEBYTECODE=1`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`E:\signal_agent\.venv\Scripts\python.exe -B`, and
`-p no:cacheprovider`. Inherited gates used their canonical fixture/test roots,
`--import-mode=importlib`, and the M4C1 implementation through `PYTHONPATH`.

| Gate | Result |
|---|---:|
| Architecture/schema | `25 passed in 14.59s` |
| Complete M4C1 | `129 passed, 0 failed, 0 deselected in 266.23s` |
| Pinned M4C1 witness | `1 passed in 6.90s` |
| M4B | `72 passed in 248.05s` |
| M4A | `115 passed in 237.03s` |
| M2/M3 | `216 passed, 1 documented deselection in 224.89s` |
| Existing M1-M3 witnesses | `3 passed in 25.46s` |
| M4B witness | `1 passed in 9.34s` |
| In-memory Python compilation | `13/13` |
| JSON parsing | `13/13` |
| Protected audit | `61 paths; zero drift` |
| Security/privacy/scope scans | `zero findings` |

The sole inherited deselection was explicit and unchanged:

```text
tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry
```

The M4C1 witness replayed without regeneration:

- Filesystem SHA-256:
  `d47fc21cd057029bf9f500af473a0cf1e0ef81c13bc58d2032d1ea9688920504`
- Internal sealed hash:
  `sha256:22914c07c53630c452c8928a18d0b5e2595ce55e3180342640a6d3fb8d5d5a76`

## Deviations and limitations

- The exact SHA of the commit that contains this report is necessarily
  external, as documented under Repository identity; the final handoff records
  it after commit creation.
- Windows `core.autocrlf` means filesystem SHA-256 values and Git blob IDs are
  different hash domains. Materialization compared raw bytes before staging;
  protected comparison used Git filters against the authorized base.
- Official Gmail behavior does not establish snapshot isolation across a live
  multi-page bootstrap. This closure proves only the captured synthetic
  contract and deliberately retains `coverage_unknown`.
- Entirely empty mailboxes remain unsupported because no accepted
  message-derived continuation exists.
- Recovery cannot recover expired provider history and never treats snapshot
  absence as deletion.
- Any live acquisition, credential lifecycle, retention, filesystem
  protection, privacy assessment, or broader mailbox-history authority belongs
  to a separately authorized M4C2. M4C2 was not started.

## Final Git-state requirement

After this report is committed, the complete post-commit verification matrix
must be rerun from the closure tree. Local closure is final only when that
matrix passes, the closure worktree is clean, the implementation worktree
retains its exact 27 untracked files, the canonical contract/M4B worktrees
remain clean, and no branch has been pushed or merged. Those terminal facts are
recorded in the final audit handoff because they occur after this report's
commit is created.
