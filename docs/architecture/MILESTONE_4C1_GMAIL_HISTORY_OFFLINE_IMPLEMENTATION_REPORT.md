# M4C1 Gmail History Offline Implementation Report

## Review status and boundary

This report records the synthetic/offline M4C1 implementation and pagination
remediation reviewed on 2026-08-12, plus the closure-audit schema-validator
remediation reviewed on 2026-08-13.

- Contract-review base SHA: `fa26dc3a7e20cc8deaf9ac99792933ce723a9b45`
- Branch: `codex/milestone4c1-gmail-history-offline`
- Worktree: `E:\signal_agent-milestone4c1-gmail-history-offline`
- Parent M4B closure SHA: `f804f41e92ca87777213ac1450f64c4549955b39`
- Implementation state: additive and uncommitted; no staged files
- Network/API execution: none
- Authentication, OAuth, credentials, tokens, or mailbox access: none
- Gmail writes, watch, Pub/Sub, or webhooks: none
- M4C2: not started and not authorized

M4C1 is synthetic/offline only. It proves a bounded contract and its local
governed integration against synthetic captures. M4C1 does **not** prove a
universally gap-free live Gmail bootstrap, and it does **not** authorize
mailbox-wide live Gmail History acquisition.

## Official provider documentation

The protected contract review completed its official-document review on
2026-08-10. The implementation and remediation use that committed review as
authority; no live API or web request was made during implementation.

| Official Gmail source | Contract fact relied upon |
|---|---|
| [`users.history.list`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list) | Global chronological history, non-contiguous history IDs, page tokens, terminal history ID, typed changes, generic-message duplication caveat, and expired/invalid-start behavior |
| [Synchronize clients with Gmail](https://developers.google.com/workspace/gmail/api/guides/sync) | Full/partial synchronization, a recent message-derived history anchor, and full synchronization after expiry |
| [`users.messages.list`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) | Label filtering, opaque page tokens, ID/thread-only list results, and the `q` restriction with `gmail.metadata` |
| [`users.messages.get`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get) | `format=METADATA` and `metadataHeaders` request semantics |
| [Message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages) | Immutable message ID, thread ID, labels, message history ID, internal date, and sensitive fields that must be rejected |
| [Message `Format`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format) | METADATA versus FULL/RAW exposure |
| [`users.getProfile`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile) | Profile history ID exists, but is not documented as a normative first-lane `startHistoryId` source |
| [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) | `gmail.metadata` permits labels/headers without message bodies but remains a restricted scope |

The implementation relies on increasing but potentially non-contiguous
history IDs; typed `messagesAdded`, `labelsAdded`, `labelsRemoved`, and
`messagesDeleted` collections; terminal provider pagination exhaustion; and
HTTP 404 as the explicit synthetic expiry signal. It does not infer provider
snapshot isolation or label-filtered continuity guarantees that the official
documentation does not state.

## Additive implementation inventory

The final review inventory contains 27 additive files: one policy, two schemas,
five Gmail source-package files, one relationship integration, ten synthetic
fixtures including the pinned witness, one test-support module, six focused
test modules, and this report. No pre-M4C1 tracked path changed.

The hashes below are final for the 26 non-report files. This report cannot
embed its own final SHA-256 without changing that SHA; its final byte size,
line count, SHA-256, and the digest over all 27 files are therefore recorded in
the external final review inventory. This is the same necessary
self-reference treatment used by earlier milestone reports.

| Path | Category | Bytes | Physical lines | SHA-256 |
|---|---|---:|---:|---|
| `config/operational_ingestion/gmail_history_metadata_v1.json` | policy | 1,598 | 63 | `97066f55afba0525abb85c060b74461dd888aca7911455f1830f4e6c00a5e7b1` |
| `schemas/operational_ingestion/gmail_history_source_receipt.v1.schema.json` | schema | 1,475 | 39 | `12240c7cbc88d7bc4887d67d2a4e164df2071f47d645e10b2672917886d8cd14` |
| `schemas/operational_ingestion/gmail_target_label_projection.v1.schema.json` | schema | 1,623 | 39 | `95f04de071dd8999d99dfa97475ccc5021073135ef773ef239be3d18c2643628` |
| `signal_agent/corpus_import/gmail_history/__init__.py` | Gmail source package | 1,057 | 38 | `12affb5c35dc168e0482202f0b07a83df900375b88f40ae46b91346fd9405b9b` |
| `signal_agent/corpus_import/gmail_history/adapter.py` | Gmail source package | 21,558 | 546 | `35f2db64643439248e66837c086eb36fa8ebb235dbf46c279968279f22ac6eba` |
| `signal_agent/corpus_import/gmail_history/canonicalization.py` | Gmail source package | 41,308 | 915 | `5691fb409f5880363dfcf594a9e9068d6fe4ec1322398382c842bf433748b047` |
| `signal_agent/corpus_import/gmail_history/models.py` | Gmail source package | 4,336 | 154 | `2c4629493ffe535b5b73177b9bf5f76501f20fdc03d1e979d8f93d84dceb6f92` |
| `signal_agent/corpus_import/gmail_history/projection.py` | Gmail source package | 15,987 | 388 | `b005c2b4988fa836d0918995bfc66da34c7b67dc420ca37765f0211d794d3253` |
| `signal_agent/relationship_signals/gmail_history_pipeline.py` | integration | 20,101 | 544 | `bc6aa6a7cd2401503ad9075418360d68c5064d117f6b34b72defc9cefc29e785` |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_coverage_unknown.json` | synthetic fixture | 1,241 | 36 | `0f9c18c9c4e798e4d609e4429e7a213c9196b02b9f80b8d4a2b1fb46d0c61565` |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_empty_mailbox.json` | synthetic fixture | 731 | 23 | `507c6b44568acbb08f27fcacfd9a39f52b7a6400c52647a58ae7148e73666206` |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_empty_target.json` | synthetic fixture | 1,233 | 36 | `eb13ca44d057d65b12b1c642992dba5fecefe78aedd913d804f60ef86514c46d` |
| `tests/fixtures/operational_ingestion/gmail_bootstrap_nonempty.json` | synthetic fixture | 1,623 | 49 | `6c4b6da23211de334e91ccdf9d84e30a0376ed3f808a969727e2b0e6455aae9f` |
| `tests/fixtures/operational_ingestion/gmail_checkpoint_expired.json` | synthetic fixture | 607 | 18 | `d984035f387f088bde49757c4879bd8d5f06978395924cd37bc10e85293524ff` |
| `tests/fixtures/operational_ingestion/gmail_history_compatibility_witness_v1.json` | pinned M4C1 witness | 16,493 | 354 | `d47fc21cd057029bf9f500af473a0cf1e0ef81c13bc58d2032d1ea9688920504` |
| `tests/fixtures/operational_ingestion/gmail_incremental_partition_a.json` | synthetic fixture | 3,310 | 90 | `d81363c942bb068ead7613c6320f86baa604c548c31a01d80d276b8e542c789e` |
| `tests/fixtures/operational_ingestion/gmail_incremental_partition_b.json` | synthetic fixture | 3,571 | 100 | `5beb2c32d22cff3004d6351a2921a8fcee54cfe2c172091f6df3934114d7d8d1` |
| `tests/fixtures/operational_ingestion/gmail_recovery.json` | synthetic fixture | 1,656 | 49 | `65a7ad47f01ebf3cab84dbfbaaa32923b0cd2da363597c9d1f01544de5b2973f` |
| `tests/fixtures/operational_ingestion/gmail_recovery_coverage_unknown.json` | synthetic fixture | 1,067 | 30 | `ace107d82f1343e6d64f16cd08c3e39a21b88a997f4ac3e7db37ea057329a6b6` |
| `tests/operational_ingestion/gmail_test_support.py` | test support | 3,258 | 102 | `e245f84d9852c50977676559d729f9fd643aca9caad42ea4f60627c5707faa70` |
| `tests/operational_ingestion/test_gmail_history_architecture.py` | focused test | 17,252 | 469 | `3e1307ce78a851f53b2acda68189b961a6e01246913ea92667e51c392c1d8a70` |
| `tests/operational_ingestion/test_gmail_history_compatibility_witness.py` | focused test | 5,235 | 139 | `a87b345fc6eb791ee9921b745557be549b7df6a9b559b4c095925373975716f4` |
| `tests/operational_ingestion/test_gmail_history_contracts.py` | focused test | 20,461 | 490 | `7b47fe694159ae53c78f157f94cb632dd08af84b0b84ef4cf519eda81d7847f0` |
| `tests/operational_ingestion/test_gmail_history_failures.py` | focused test | 6,114 | 174 | `c9b6d04edf0d8e5f1695026cfb1a2f07e2e43a7730596722423b11f3347fc9cb` |
| `tests/operational_ingestion/test_gmail_history_governance.py` | focused test | 5,694 | 151 | `2cca4f24194b7ff23fca5fcc95428206b262de79247194b8d9f0efd691b0a636` |
| `tests/operational_ingestion/test_gmail_history_projection.py` | focused test | 18,877 | 471 | `744cd9b3788ca5c4ac90b1bfb8e922213e71bda2fad830c11068ec69939b3e31` |
| `docs/architecture/MILESTONE_4C1_GMAIL_HISTORY_OFFLINE_IMPLEMENTATION_REPORT.md` | implementation report | external final inventory | external final inventory | self-referential final SHA recorded externally |

Before this report, the 26 implementation/support files totalled 217,466 bytes
and 5,507 physical lines.

## Provider observation and identity model

The provider observation set contains two semantic record types:

- `gmail_history_typed_event` represents one admitted specific history change.
  Its semantic identity binds the SHA-256 of the history record ID, its numeric
  sequence, event kind, HMAC-protected message and thread IDs, sorted
  HMAC-protected affected/message labels, and a deterministic within-record
  rank. The derived `provider_event_id` is independent of page boundaries,
  request attempts, and capture timestamps.
- `gmail_message_metadata` represents one exact METADATA response. Its identity
  binds the protected immutable Gmail message ID, hashed message `historyId`,
  hashed `internalDate`, sorted protected label IDs, and a protected normalized
  `From` value.

The immutable Gmail message ID is the source-local message identity. It is
domain-separated with `gmail_history_source_identifier.v1` and protected with
HMAC-SHA-256 before semantic artifacts or relationship records are emitted.
Clear message, thread, label, sender, source-instance, and history-continuation
values are not retained downstream.

History-event identity is typed-event identity, not the generic
`History.messages` collection. Exact specific events are sorted by numeric
history sequence, the fixed kind rank (`messagesAdded`, `labelsAdded`,
`labelsRemoved`, `messagesDeleted`), protected identity, affected labels, and
derived event ID. The provider does not promise temporal order among change
members inside one history record, so the implementation makes no such claim.

Canonicalization rejects unknown endpoint fields and unknown response fields;
requires increasing numeric history IDs without requiring contiguity; sorts
set-like labels; collapses whitespace and case-folds `From` before protection;
converts `internalDate` milliseconds to UTC for the source event time; and
keeps all transport attempts/pages in acquisition identity rather than
semantic identity. M4A's canonical observation-set assembly deduplicates exact
observations. Generic `History.messages` entries are validated and preserved
in captured response bytes but create no duplicate semantic effect when their
specific typed changes are present.

## Acquisition scope and TARGET_LABEL projection

Acquisition scope and semantic scope are intentionally different:

```text
bounded unfiltered provider history acquisition
-> canonical typed provider observations
-> versioned local TARGET_LABEL projection
-> only legitimate label-scoped relationship effects
```

Unfiltered incremental acquisition retains admitted provider observations for
continuity, including unrelated mailbox events. The semantic projection is
limited to one configured label. An unrelated observation remains provider
evidence and cannot create a target-label transition or relationship record.

Projection policy identity is
`gmail_target_label_projection_v1` version `1.0.0`, bound to the SHA-256 of
`gmail_history_metadata_v1.json`. The target label itself is HMAC-protected.
The provider `observation_set_hash` identifies page/retry-independent provider
semantics. The separate `target_label_projection_set_hash` binds source,
policy, protected label, prior projection reference, coverage, transitions,
final states, unresolved relevance, and the provider observation-set hash. It
explicitly excludes acquisition time, capture IDs, `capture_set_hash`, page
boundaries, request attempts, and retry history.

The projection state machine distinguishes:

| Evidence and prior state | Semantic result |
|---|---|
| Target label present in admitted message-added/metadata evidence | `entered_target_label` or initial/recovery membership |
| Explicit `labelsAdded` names TARGET_LABEL | enter scope if not already inside |
| Explicit `labelsRemoved` names TARGET_LABEL and prior state is inside | `left_target_label`; never mailbox deletion |
| Explicit `messagesDeleted` and prior state is inside | `mailbox_deleted_while_in_target_scope` |
| Departure/deletion with unknown prior target relevance | unresolved `coverage_unknown` classification; no effect |
| Snapshot absence | no departure and no deletion inference |

Only the five truthful transition kinds normalize into neutral relationship
records. Clear person/display/professional fields remain empty; protected
sender/thread identifiers may be carried as restricted local identifiers.
Automatic identity merge, canonical-person selection, external authority, and
transport-topology identity are forbidden.

## Bootstrap, pagination, and anchors

Supported bootstrap begins with `users.messages.list` constrained to exactly
`labelIds=[TARGET_LABEL]`. The initial request cannot supply a page token. Each
response `nextPageToken` becomes an opaque page continuation that the
immediately following target-list request must consume exactly. Every target
page repeats the same exact label scope. Tokens cannot be skipped, changed,
replayed, or cycled; an intervening metadata/anchor operation is forbidden
while a target token is pending. Completion requires a terminal target-list
response with no `nextPageToken`.

The target enumeration has an explicit page counter. To avoid changing the
accepted policy file (which participates in witness identity), the page bound
uses `maximum_target_label_pages` if a future policy defines it and otherwise
uses the existing `maximum_operations=24`. The global operation bound remains
enforced after contract validation; the target-page check therefore reports
its specific failure when page 25 is attempted. `resultSizeEstimate`, message
count, fixture count, and page ordinal are never exhaustion proof.

After target pagination is terminal, every listed message requires one exact
`users.messages.get(format=METADATA, metadataHeaders=[From])` response. The
first listed message's admitted `historyId` is the message-derived continuation
anchor. Supported completion additionally requires eligible coverage, the
complete projection, and the full M4A verification chain before checkpoint
commit.

Two list modes remain distinct:

- **TARGET_LABEL bootstrap/recovery:** exhaust every bounded page and create
  membership only from admitted target metadata.
- **Empty TARGET_LABEL, nonempty mailbox anchor lookup:** only after a terminal
  empty target enumeration, make at most one unfiltered
  `messages.list(maxResults=1)` request and at most one metadata lookup. A
  returned `nextPageToken` or large `resultSizeEstimate` does not trigger or
  imply mailbox enumeration. The anchor message remains outside the target
  projection and creates no membership or relationship effect.

An entirely empty mailbox has no accepted message-derived history anchor and
is classified `unsupported_bootstrap_continuation`; it cannot advance a
checkpoint. Bootstrap concurrency ambiguity is classified `coverage_unknown`.
Provider evidence may be retained, but projection/checkpoint completion fails
closed and no stronger completeness claim is emitted.

## Incremental history, continuations, expiry, and recovery

Incremental continuity uses unfiltered `users.history.list`. `labelId` and
`historyTypes` are explicitly prohibited and raise
`gmail_filtered_history_forbidden`; other unknown fields raise
`gmail_history_request_field_forbidden`. Endpoint allowlists remain exact.

`nextPageToken` is an opaque within-request page continuation. It is hashed in
safe provenance, must be consumed exactly by the next history request, and can
never become a checkpoint. Only a terminal response without `nextPageToken`
may supply the current provider `historyId`. That terminal history ID is a
protected checkpoint candidate, not a timestamp and not authority to advance
state. It becomes current only after bounded material, preservation,
normalization, completed manifest, verifier authority, predecessor validation,
and commit all succeed. `getProfile.historyId` is never used as a normative
bootstrap anchor.

A synthetic HTTP 404 marks the prior continuation expired. The failure receipt
is recorded while the prior committed checkpoint remains current. Recovery is
a separate bounded current-state run with the same complete TARGET_LABEL page
exhaustion and metadata requirements as bootstrap. It may establish current
membership and a new message-derived anchor, but cannot reconstruct history
outside Gmail retention. Differences from the prior snapshot do not create
departures, deletions, or tombstones; prior evidence remains immutable. A
pending target page token, ambiguous coverage, incomplete M4A chain, or stale
predecessor prevents recovery commit.

## Metadata minimization and identity protection

The exact admitted top-level message fields are `id`, `threadId`, `labelIds`,
`historyId`, `internalDate`, and `payload`; `payload` may contain only one
nonempty `From` header. The request is exactly
`format=METADATA, metadataHeaders=[From]`.

Field decisions after code-level review:

| Field | Classification | Exact causal use |
|---|---|---|
| `historyId` | REQUIRED | Supplies the accepted message-derived bootstrap/recovery anchor; its SHA-256 participates in metadata observation identity and binds the metadata version without retaining the clear value downstream. |
| `threadId` | REQUIRED | Preserves Gmail's provider-native message/thread association as a domain-separated HMAC; it participates in typed/metadata observation identity, transition provenance, and the restricted neutral relationship identifier set. |
| `internalDate` | REQUIRED | Supplies the only admitted message event time; its hash participates in metadata observation identity and its UTC conversion becomes `source_event_time`/`occurred_at` where metadata supports the transition. History IDs are not misused as timestamps. |

`From` is the only approved header because it provides the protected sender
identity used by legitimate relationship normalization. It is normalized,
case-folded, and HMAC-protected; clear header values are not retained. No other
header has an approved projection or normalization use.

Exact negative tests reject snippet, raw, body, MIME parts, attachments,
size estimates as metadata fields, classification-label data, unexpected
top-level/payload fields, more than one header, empty/non-From headers, expanded
request header lists, malformed METADATA responses, and secret-like keys or
values. Synthetic fixture addresses use only the reserved `.invalid` domain.

Protection uses HMAC-SHA-256 with explicit namespace, semantic kind, version,
and key ID. Message, thread, label, sender, source-instance, and continuation
domains are separate. The key is caller-supplied and never serialized.
Artifacts are scanned for clear fixture identifiers outside preserved original
capture bytes; relationship privacy flags explicitly deny clear identifiers,
message bodies, snippets, and attachments.

## Determinism, replay, and transitive verification

Two synthetic incremental scripts partition the same typed observations across
different valid history pages. Their acquisition `capture_set_hash` values
differ, while provider `observation_set_hash`, target projection set, final
states, and legitimate normalized effects are equal. A separate retry-history
test proves additional failed attempts change transport evidence but not
semantic identity. Exact fixture replay recreates identical immutable captured
inputs, and exact checkpoint commit replay returns the existing immutable
bytes.

The Gmail adapter does not bypass M4A. It reloads and verifies the persisted
AcquisitionBoundary and BoundedSourceMaterial, recomputes the observation-set
hash, resolves every projected transition to M4A observation-capture
provenance, preserves the exact bounded material, emits a sealed source receipt
and projection, normalizes only legitimate transitions, and delegates completed
manifest/candidate/authority/commit enforcement to the existing M4A kernel.
Capture-body, metadata-body, capture-receipt, bounded-material, preserved-source,
projection, and manifest corruption tests all fail closed.

Checkpoint non-advancement is proved across partial acquisition, metadata-only
progress, history-page/terminal-ID capture, canonical observations, projection,
complete boundary, bounded material, preservation, normalization, downstream
output, incomplete or invalid manifest, missing/invalid verifier authority,
stale predecessor, governed processor failures, and failed commit. Only the
existing complete causal chain can advance the checkpoint; expiry and
`coverage_unknown` leave the prior checkpoint current.

## Security, privacy, and architecture evidence

Final static and focused checks establish:

- zero imports of Google auth/API clients, `requests`, `httpx`, sockets, or
  `urllib.request` in M4C1 production modules;
- zero live Gmail calls, network operations, OAuth, credential loading, token
  refresh/persistence, Gmail writes, watch, Pub/Sub, or webhook behavior;
- zero persisted forbidden provider fields, unapproved headers, or secret-key
  canaries in additive fixtures/artifacts;
- zero personal/live mailbox fixtures and one unique admitted header name,
  `From`;
- zero reverse imports from M4A, LinkedIn, or interaction-event packages into
  M4C1;
- zero changes to the existing media-opportunities Gmail reader;
- zero M4C2 paths or behavior;
- all 13 additive JSON files parsed, all 13 additive Python files compiled in
  memory, and all 27 additive files had zero trailing-whitespace lines.

The architecture schema test does not import `jsonschema`: that package is not
declared by this repository, and changing shared dependency configuration or
installing a package solely for M4C1 acceptance was not authorized. The two
additive schemas were therefore mechanically inventoried before implementing a
narrow M4C1-local standard-library validator.

The schemas use types `object`, `array`, `string`, `integer`, and `null`
(including `object|null`), with validation keywords `required`, `properties`,
`additionalProperties`, `items`, `const`, `pattern`, `minLength`, and
`minimum`. Array item schemas use `object` and `string`. `$schema`, `$id`, and
`title` are schema metadata; `format` remains an annotation, matching the
former `Draft202012Validator` invocation without a format checker. The schemas
use no `number`, `boolean` type, `enum`, `maxLength`, `maximum`, `minItems`,
`maxItems`, `uniqueItems`, combinator, or `$ref` constraint.

The local validator supports exactly that observed subset. It recursively
validates object properties, array items, object items with nested properties,
primitive items, nullable declared types, constants, lengths, numeric minima,
and regex patterns. It rejects schema keywords and declared types outside that
closed subset instead of silently ignoring them. It is not represented as a
general JSON Schema implementation, and it does not claim validation beyond
the inventoried and tested M4C1 subset.

The independent closure audit found that the first local replacement only
validated `items: {"type": "object"}` and incorrectly accepted
`semantic_identity_excludes: [42]`, contradicting the earlier claim of complete
subset coverage. The remediation replaced the divergent object-item branch
with recursive generic `items` validation. Explicit regressions now accept a
valid string array; reject `[42]` and a mixed string/integer array; preserve
object-item validation; exercise nested object/array/primitive recursion; and
adversarially check every validation constraint used by the two schemas. The
mechanical keyword/type inventory found no additional unsupported validation
feature. Existing generated projection/receipt artifacts still pass. No shared
dependency declaration or environment was changed, and no package was
installed.

The final Git-blob audit compared 54 protected M1-M4B paths with the base and
found zero drift. The focused architecture module also checks 16 pinned
raw-byte guards, including the generic runner, prior source adapters, neutral
schemas, all prior witnesses, M4A/M4B surfaces, the existing Gmail reader, and
the protected M4C1 contract review. Canonical M4A and M4B gates pass in full.

## Witness evidence

The existing M4C1 witness was not regenerated or edited.

| Witness | Filesystem SHA-256 | Internal sealed hash | Result |
|---|---|---|---:|
| M4C1 Gmail History offline | `d47fc21cd057029bf9f500af473a0cf1e0ef81c13bc58d2032d1ea9688920504` | `sha256:22914c07c53630c452c8928a18d0b5e2595ce55e3180342640a6d3fb8d5d5a76` | 1 passed exact |
| Existing LinkedIn, interaction-event, and M3 witnesses | protected pinned values | protected pinned values | 3 passed exact |
| M4B operational witness | protected pinned value | protected pinned value | 1 passed exact |

The M4C1 witness covers prior committed continuation, multi-page unfiltered
history, unrelated activity, target entry/departure/relevant explicit deletion,
metadata, terminal history ID, provider observations, target projection,
capture/observation hashes, bounded material, preservation, normalized effects,
completed manifest, candidate, verifier authority, and checkpoint commit.
Bootstrap and recovery/expiry are proved separately.

## Verification manifest

All commands used `PYTHONDONTWRITEBYTECODE=1`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, the repository-accepted
`E:\signal_agent\.venv\Scripts\python.exe -B`, and pytest
`-p no:cacheprovider`.

### M4C1 commands

```powershell
python -B -m pytest -q -p no:cacheprovider `
  tests/operational_ingestion/test_gmail_history_contracts.py `
  tests/operational_ingestion/test_gmail_history_projection.py `
  tests/operational_ingestion/test_gmail_history_architecture.py
```

Result: `80 passed in 92.97s`.

That is the historical pagination-remediation receipt. The targeted
schema-validator remediation was then run explicitly:

```powershell
python -B -m pytest -q -p no:cacheprovider `
  tests/operational_ingestion/test_gmail_history_architecture.py
```

Result: `25 passed in 36.60s`, including 18 expanded schema-scope and
adversarial regression cases beyond the prior seven-case architecture module.

```powershell
python -B -m pytest -q -p no:cacheprovider `
  tests/operational_ingestion/test_gmail_history_contracts.py `
  tests/operational_ingestion/test_gmail_history_projection.py `
  tests/operational_ingestion/test_gmail_history_architecture.py `
  tests/operational_ingestion/test_gmail_history_governance.py `
  tests/operational_ingestion/test_gmail_history_failures.py `
  tests/operational_ingestion/test_gmail_history_compatibility_witness.py
```

Complete focused result after schema remediation:
`129 passed, 0 failed, 0 deselected in 516.52s`. The count is not forced back
to the historical baseline: it includes the earlier pagination cases plus the
18 expanded validator-scope/regression cases.

```powershell
python -B -m pytest -q -p no:cacheprovider `
  tests/operational_ingestion/test_gmail_history_compatibility_witness.py
```

Pinned witness replay after schema remediation: `1 passed in 10.63s`; both
witness hashes remained exact.

The complete gate covers target bootstrap and recovery exhaustion; empty-target
anchor mode; unsupported empty mailbox; `coverage_unknown`; unfiltered history
and filtered-history error taxonomy; exact metadata minimization; typed-event
projection and generic-event suppression; unrelated-event isolation;
page-partition and retry-history equivalence; replay; expiry; corruption;
secret handling; checkpoint non-advancement; architecture guards; and witness
exactness.

### Inherited commands and results

Inherited path-bound tests were run from their canonical test/fixture roots
with M4C1 production code supplied through
`PYTHONPATH=E:\signal_agent-milestone4c1-gmail-history-offline` and pytest
`--import-mode=importlib`.

| Gate | Canonical test root / command scope | Final result |
|---|---|---:|
| M4B focused | `E:\signal_agent-milestone4b-closure`; the four M4B operational test modules | `72 passed in 1083.34s` |
| Protected M4A | `E:\signal_agent-milestone4a-closure`; the seven protected operational-ingestion modules | `115 passed in 949.03s` |
| M2/M3 closure | `E:\signal_agent-milestone2-closure`; eight `tests/corpus_import` modules, the 20-file M2 root list, five `tests/identity_reconciliation` modules, and the documented live-registry deselection | `216 passed, 1 deselected in 1003.64s` |
| Existing M1-M3 witnesses | canonical M2 root; LinkedIn, interaction-event, and M3 witness modules | `3 passed in 36.98s` |
| M4B witness | canonical M4B root; `test_operational_compatibility_witness.py` | `1 passed in 19.16s` |

The exact inherited deselection remains:

```text
tests/test_invariant_checker_v1.py::test_registry_loader_accepts_live_registry
```

It is the documented closure-only exception whose unrelated live registry
dependencies are absent from the clean closure tree.

## Remediation and deviations

The targeted remediation made four bounded changes:

1. Bootstrap/recovery TARGET_LABEL enumeration now binds and exhausts the
   complete bounded `users.messages.list` token chain, while preserving the
   deliberately non-exhaustive empty-target anchor lookup.
2. `labelId`/`historyTypes` detection now precedes the generic history request
   allowlist, producing `gmail_filtered_history_forbidden` without authorizing
   either filter or weakening unknown-field rejection.
3. The architecture test uses a narrow M4C1-local recursive standard-library
   schema validator instead of an undeclared package. A closure-audit finding
   that primitive array items were not validated was reproduced and corrected
   structurally; explicit `[42]`, mixed-item, object-item, nested-recursion, and
   used-constraint regressions now pass. Shared dependencies were not edited
   and nothing was installed.
4. This implementation report and external final inventory close the missing
   documentation surface.

No new committed pagination fixture was necessary: the tests derive bounded
multi-page scripts from the existing synthetic fixtures in pytest temporary
directories. The accepted policy was not changed, so the existing witness
identity remained stable; the target-page bound deliberately falls back to the
already accepted operation bound.

Direct inherited test execution in the M4C1 linked worktree exposed the
documented Windows `core.autocrlf` and absolute-root witness provenance
limitations. Those non-authoritative runs reported raw-byte/witness-root
differences even though Git blobs had zero drift. The final gates therefore use
the closure reports' provenance-preserving canonical roots. One M4B full run
also encountered the inherited mtime-order-sensitive candidate/authority test;
the node passed alone and the full serial rerun passed 72/72. No protected code,
fixture, or witness was changed in response.

The implementation uses the smaller coherent five-file Gmail package instead
of creating separate `protection.py` or `normalization.py` modules. No M4A,
M4B, generic relationship runner, neutral schema, identity-reconciliation, or
existing witness modification was needed.

## Unresolved limitations

- Official Gmail documentation does not prove snapshot isolation across
  bootstrap list pages. Synthetic coverage can be complete for its captured
  contract while universal live transition coverage remains unproven.
- Entirely empty mailboxes have no accepted message-derived continuation and
  remain unsupported.
- `coverage_unknown` is intentionally not checkpoint eligible.
- Recovery reconstructs bounded current target membership but cannot recover
  provider history that has expired; absence never substitutes for explicit
  departure/deletion evidence.
- Unfiltered live History would broaden privacy and retention scope. It requires
  a separate M4C2 decision covering credentials, SDK lifecycle, live capture,
  retention, filesystem protection, source identifiers, minimization, and
  privacy impact.
- The report's own final hash is necessarily external to avoid a self-reference;
  the final review inventory supplies it and the complete 27-file digest.

M4C2 was not started.
