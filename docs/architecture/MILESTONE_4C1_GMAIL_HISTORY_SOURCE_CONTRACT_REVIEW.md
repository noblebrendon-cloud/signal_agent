# M4C1 Gmail History Source Contract Review

## Review status

This document records the M4C1 provider/source contract review completed on
2026-08-10. It is planning evidence only.

- Canonical protected base: `f804f41e92ca87777213ac1450f64c4549955b39`
- Canonical branch: `codex/milestone4b-closure`
- Canonical worktree: `E:\signal_agent-milestone4b-closure`
- Planning worktree: `E:\signal_agent-milestone4c1-contract-review`
- Planning checkout: detached at the canonical base; no branch created
- Implementation: not started
- M4C2: not started and not authorized
- Network/API execution: none
- Authentication, credentials, tokens, or mailbox access: none
- Git staging/commit/push: none

The canonical worktree was kept clean. A separate detached planning worktree
was necessary because amending the tracked canonical plan directly would have
modified the protected closure worktree.

## Decision

Reject this acquisition contract:

```text
users.history.list(labelId=TARGET_LABEL)
-> claimed complete TARGET_LABEL history
```

Adopt this planning contract:

```text
unfiltered Gmail mailbox history acquisition
-> canonical typed provider observation set
-> immutable governed local TARGET_LABEL membership projection
-> label-scoped semantic evidence
-> legitimate neutral relationship normalization
```

The revised contract is defensible for a future **offline M4C1 implementation**
only under explicit bootstrap and coverage limitations. It is not evidence that
a live bootstrap is universally gap-free, and it does not authorize M4C2.

## Official documentation reviewed

Only official Google Gmail API documentation was used for provider claims.

| Official source | Provider facts used |
|---|---|
| [`users.history.list`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list) | Global mailbox changes; chronological increasing history IDs; non-contiguous IDs; page token; terminal current history ID; expiry/invalid ID typically returns 404; label filter wording; typed changes; generic-message duplication caveat; supported scopes |
| [Synchronize clients with Gmail](https://developers.google.com/workspace/gmail/api/guides/sync) | Full versus partial synchronization; recent-message history ID bootstrap; first listed message described as most recent; expired history requires full synchronization |
| [`users.messages.list`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) | Label filters require all named labels; page tokens; list results contain only message ID/thread ID; `q` is unavailable with `gmail.metadata`; supported scopes |
| [`users.messages.get`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get) | `format` and `metadataHeaders`; supported read scopes |
| [Message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages) | Immutable message ID; thread ID; label IDs; message history ID; internal date; body/snippet/raw fields that the contract must reject |
| [Message `Format`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format) | `METADATA` returns message ID, labels, and headers; `FULL` and `RAW` expose bodies and are unavailable under `gmail.metadata` |
| [`users.getProfile`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile) | Profile exposes the mailbox's current history ID, but does not state that this value is a valid `history.list.startHistoryId` source |
| [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) | `gmail.metadata` permits labels/headers but not body; it is still a restricted scope; M4C1 performs no authorization |

Reference pages were reviewed on 2026-08-10. Their displayed last-updated dates
ranged from 2025-03-24 through 2026-07-22.

## Provider facts accepted by the contract

### History and continuations

- `users.history.list` lists mailbox changes in chronological order by
  increasing `historyId`.
- History IDs are provider sequence/continuation values, not contiguous local
  sequence numbers or timestamps.
- `pageToken` selects another response page. It is not a history continuation
  and cannot become a local checkpoint.
- The terminal response's `historyId` is the mailbox's current history record
  and can be stored for a future request when no `nextPageToken` remains.
- Invalid or out-of-range start history typically returns HTTP 404 and requires
  full synchronization.
- The accepted `startHistoryId` sources named by the reference are a message,
  thread, or previous history-list response.

### Typed events

- `messagesAdded` means a message was added to the mailbox.
- `messagesDeleted` means a message was permanently deleted from the mailbox,
  not merely moved to Trash.
- `labelsAdded` and `labelsRemoved` name labels added to or removed from a
  message.
- Generic `History.messages` entries can duplicate the messages represented in
  the specific change collections. The specific collections are the semantic
  source; generic entries are preservation-only when duplicated.

### Messages and metadata

- Gmail message ID is documented as immutable.
- `messages.list` returns only message ID and thread ID; details require
  `messages.get`.
- `messages.list(labelIds=[...])` returns messages matching all supplied labels.
- `messages.list.q` cannot be used with `gmail.metadata` and is outside this
  source contract.
- `messages.get(format=METADATA, metadataHeaders=[...])` is the approved shape
  for a future metadata lookup. The first implementation must use an exact
  allowlist and reject snippet, raw, body data, MIME children, attachments,
  classification-label data, and unknown fields.

## Original contract rejection

The official label-filter description does not define whether matching occurs
against:

- the message's state before the event;
- the message's state after the event;
- the labels named by `labelsAdded`/`labelsRemoved`; or
- some other provider-internal evaluation.

That ambiguity prevents a claim that a label-filtered stream includes every
event in which a message leaves the label or is deleted after previously being
in the label. It also prevents claiming that recovery from a filtered stream is
complete for label departures and deletions.

The conflict is provider-documentation-level, not an M4A implementation defect.
No M4A/M4B change, local inference, or synthetic fixture can turn the missing
provider guarantee into evidence.

## Chosen source and projection contract

### Source of truth

The provider source is **Gmail mailbox history**. Partial acquisition after an
established checkpoint uses unfiltered `users.history.list`.

The target label is a local versioned projection policy. The projection makes
only a derived claim from captured provider history and prior committed state;
it is not a Gmail-native materialized view.

### Scope separation

| Layer | Scope and authority |
|---|---|
| Provider acquisition | Unfiltered mailbox typed events needed for continuity |
| Provider observation set | Canonical unfiltered events, including unrelated messages |
| Target-label projection | One configured label interpreted from events and prior state |
| Relationship output | Only truthful records supported by the unchanged neutral schema |

Unrelated mailbox changes remain in provider evidence and observation identity
but create no target-label transition or relationship effect.

## Membership projection model

The future projection is immutable and predecessor-bound. Its key input is:

```text
protected Gmail message identity
+ previous committed membership state/reference
+ chronologically ordered typed event
+ exact projection-policy identity/version/hash
```

Its result is a new state/transition artifact with capture provenance. Required
outcomes are:

| Input | Output |
|---|---|
| Outside + target label added | Entered scope; state true |
| Inside + target label removed | Left scope; state false |
| Inside + explicit mailbox deletion | Mailbox-deleted target observation; state inactive |
| Message added with approved metadata showing target label | Entered scope under policy |
| Unrelated event | Provider evidence only |
| Deletion with unknown prior target relevance | Provider deletion retained; target relevance `coverage_unknown` |

Label departure is not deletion. Absence is neither departure nor deletion.

## Identity and hash boundaries

The future contract must distinguish:

- exact `capture_set_hash` for transport provenance;
- provider `observation_set_hash` for canonical unfiltered Gmail events; and
- `target_label_projection_set_hash` for the policy-bound local interpretation.

The projection hash must incorporate the prior projection reference and exact
policy hash. The M4A checkpoint candidate must bind all relevant hashes and the
completed governed manifest. A provider page token or terminal Gmail history ID
alone cannot advance state.

## Bootstrap decision

### Normative continuation

The first contract uses a **recent message's history ID** as the overlap/start
anchor. This is the route stated by the synchronization guide and accepted by
the `history.list` reference.

`messages.list` yields a message reference and `messages.get` yields approved
metadata. A body-bearing format is prohibited. Any required top-level field not
explicitly guaranteed under `METADATA` must be separately proven before it can
become mandatory.

### `getProfile.historyId`

`users.getProfile` calls its value the mailbox's current history ID, but the
`history.list.startHistoryId` reference does not name profile output as an
accepted source. The first contract therefore does not use it normatively.

### Nonempty target label

A bounded target-label enumeration may establish initial members, required
metadata observations, and a recent message-derived overlap anchor. Every page
and required lookup must complete. Policy-bound exhaustion or lookup failure is
incomplete bootstrap, not partial success.

## Empty-label decision

Two cases are distinct:

1. **Target label empty, mailbox nonempty:** a bounded unfiltered
   `messages.list(maxResults=1)` and approved metadata lookup may provide the
   recent-message anchor described by the synchronization guide. It is provider
   acquisition evidence only and does not create a target member.
2. **Mailbox empty:** no message/thread/history-list continuation source exists.
   The profile value is not normatively accepted. Classification is
   `unsupported_bootstrap_continuation`.

M4C1 must test both. M4C2 cannot silently broaden the contract.

## Bootstrap race and overlap analysis

The synchronization guide prescribes a full sync followed by retaining the
history ID of the most recent listed message. The official documents do not
state that paginated list results are a snapshot, that later message lookups are
atomic with the list, or that a deletion during enumeration carries enough
prior label state to establish target relevance.

The future offline implementation may prove deterministic behavior for captured
fixtures by:

- selecting a message-derived anchor before or during bootstrap;
- preserving the target-label snapshot separately from the unfiltered history
  catch-up interval;
- canonically deduplicating provider observations represented in both;
- applying ordered typed events idempotently to membership state; and
- classifying unresolved target relevance as `coverage_unknown`.

It may not claim that this proves undocumented live snapshot isolation. In
particular, a message deleted during bootstrap may be absent from the target
snapshot while the deletion event lacks enough prior label state to classify it
as a target member. The provider deletion is still preserved, but no target
tombstone is invented.

Consequently:

- established-checkpoint partial synchronization is provider-defensible;
- captured-fixture bootstrap behavior is implementation-testable;
- universal gap-free live bootstrap transition history is not provider-proven;
  and
- any policy requiring complete classification must block checkpoint eligibility
  when bootstrap coverage remains unknown.

## Partial synchronization contract

After a committed continuation exists:

```text
history.list(startHistoryId=COMMITTED_HISTORY_ID)
```

is unfiltered by label. All pages and admitted metadata lookups must verify.
The target-label projection consumes the canonical typed event sequence. The
terminal mailbox `historyId` remains a candidate until M4A verifies the complete
boundary, projection, bounded material, preservation, normalization, governed
run, manifest, authority, predecessor, and exclusive commit.

## Expiry recovery

HTTP 404 is an explicit history-expiry condition. It leaves the prior checkpoint
current and requires bounded bootstrap recovery.

Recovery can reconstruct current target membership and establish a new overlap
anchor. It cannot reconstruct label departures or deletions outside Gmail's
retained history. Snapshot absence remains non-deletion. Lost history is an
explicit coverage limitation and cannot be converted to empty success.

## Deletion and label-removal conclusions

Under unfiltered history, an explicit `messagesDeleted` record is defensible
mailbox-deletion evidence. It creates a target-scoped tombstone only if prior
committed/proven projection state establishes target relevance.

An explicit `labelsRemoved` record naming TARGET_LABEL can create
`left_target_label` when the prior projection establishes membership. It never
becomes a mailbox-deletion tombstone.

Unrelated deletion/removal events remain provider evidence only.

## Privacy consequence

Unfiltered history is a material privacy expansion over label-filtered
acquisition. M4A's exact-response preservation could retain identifiers and
typed events for mailbox activity outside TARGET_LABEL even though they produce
no semantic relationship record.

M4C1 remains synthetic-only. Before any M4C2 proposal, reviewers must decide:

- whether mailbox-wide metadata capture is proportionate;
- exact-response retention duration and filesystem protection;
- treatment of provider message/thread/history IDs;
- permitted headers and metadata minimization;
- whether pre-persistence extraction could coexist with M4A evidence
  guarantees;
- credentials, least-privilege scope, and dependency reproduction; and
- whether bootstrap/expiry coverage limitations are acceptable.

This review does not pre-decide those questions.

## Revised offline fixture requirements

A future M4C1 fixture set must include:

- target and other-label events in one unfiltered interval;
- unrelated messages and deletion;
- target entry, target departure, and relevant permanent deletion;
- generic-message duplication;
- history pagination and terminal ID;
- alternate valid partitioning with equal provider/projection semantic hashes;
- bootstrap snapshot and overlap;
- empty target/nonempty mailbox anchor;
- empty-mailbox unsupported result;
- ambiguous bootstrap deletion;
- expired history and recovery; and
- body, snippet, attachment, unknown-field, header, and secret failures.

No personal Gmail data, Google SDK, network operation, OAuth material, token,
or credential path belongs in those fixtures or tests.

## Unresolved provider ambiguities

| Ambiguity | Contract disposition |
|---|---|
| `history.list(labelId=...)` departure/deletion completeness | Filtered continuity contract rejected |
| `getProfile.historyId` as valid `startHistoryId` | Not normative without explicit official documentation |
| Snapshot isolation across `messages.list` pages | Not claimed |
| Atomicity between list and metadata lookups | Not claimed |
| Target relevance of deletion during ambiguous bootstrap | `coverage_unknown`; no target tombstone |
| Entirely empty mailbox continuation | Unsupported in first lane |
| History lost beyond retention during expiry | Explicit coverage limitation |
| Exact top-level fields guaranteed by `format=METADATA` beyond ID/labels/headers | Must be proven before being required |

## Updated stop conditions

Stop later work if it requires:

- label-filtered history as the continuity feed;
- profile history ID as a normative start without new documentation;
- a complete empty-mailbox bootstrap;
- undocumented snapshot isolation;
- treating coverage unknown as complete;
- inferring deletion or departure from absence;
- collapsing label removal into mailbox deletion;
- discarding unrelated provider events needed for continuity;
- changing M4A/M4B or another protected boundary;
- storing bodies/snippets/attachments or secrets;
- networking, OAuth, credentials, Google SDK execution, or Gmail writes; or
- starting M4C2.

## Recommendation

The revised M4C1 contract is **defensible for offline implementation** if its
claim is limited to:

> Complete deterministic processing of the unfiltered Gmail history interval
> represented by the captured provider evidence, with a governed local
> projection into one configured label scope, subject to explicit Gmail history
> retention and bootstrap coverage limitations.

It is not defensible as proof of universally gap-free live bootstrap or as
authorization for mailbox-wide live acquisition. Separate approval of this
contract is required before implementation, and a further privacy/provider gate
is required before M4C2.

