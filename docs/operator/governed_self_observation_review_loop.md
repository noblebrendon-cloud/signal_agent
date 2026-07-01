# Governed Self-Observation Review Loop

## 1. Purpose

This document defines a planning-only human review layer for converting
`self_observation_report.v1` findings into bounded review artifacts.

The loop is:

```text
observed pressure pattern
-> evidence-backed review artifact
-> human accepts, rejects, defers, or requests refinement
-> accepted item becomes a governed proposal
-> any implementation still passes existing transition and approval controls
```

Analytics findings are never authority. They are signals for review. A
candidate, metric, repeated pattern, or generated report does not approve
changes to policy, workflows, gates, code, canonical state, or operator behavior.

## 2. Non-goals

This layer does not:

- mutate canonical state
- rewrite old ledgers
- change transition gate behavior
- change policy behavior
- change workflow behavior
- create queues, schedulers, dashboards, monitors, or external integrations
- execute remediation
- auto-generate approved implementation work
- treat an analytics candidate as a real subsystem
- treat a human-accepted review item as implementation authorization

No runtime behavior is proposed in this document. This is a planning artifact
only.

## 3. Terms and state model

### Object distinction

```text
candidate -> review finding -> governed proposal -> approved implementation
```

- `candidate`: an observed pattern from analytics. It is not a finding of fact.
- `review finding`: a human-review artifact that preserves report evidence and
  states why a candidate or metric deserves review.
- `governed proposal`: a bounded proposal accepted for the existing governance
  process. It is still not implementation authorization.
- `approved implementation`: a separate change that has passed the existing
  transition gate, policy evaluation, declared mutation contracts,
  append-only observability requirements, and required human approvals.

### Human decision states

Review artifacts use this decision state model:

```text
observed
-> queued_for_review
-> accepted_for_proposal
-> rejected
-> deferred
-> superseded
```

- `observed`: a report-backed signal exists but has not been triaged.
- `queued_for_review`: a human has selected the item for review.
- `accepted_for_proposal`: a human agrees that a governed proposal may be
  drafted.
- `rejected`: a human rejects the item as not useful, not supported, or out of
  scope.
- `deferred`: a human preserves the item for later review.
- `superseded`: a newer report, candidate, or decision replaces the item.

Only `accepted_for_proposal` may produce a governed proposal. It still does not
authorize code, policy, workflow, gate, or state changes.

## 4. Inputs from `self_observation_report.v1`

The review loop may read:

- `schema_version`
- `source_files`
- `metrics`
- `repeated_patterns`
- `subsystem_candidates`
- `warnings`
- `recommendations` only when they are non-mutating review suggestions

The review loop must compute and preserve the full SHA-256 hash of the exact
report file reviewed. The report hash, schema version, and source path bind the
review artifact to a fixed input snapshot.

The review loop must not derive authority from:

- candidate names
- confidence scores alone
- repeated pattern counts alone
- legacy `unknown_denial` rows alone
- any metric without exact source evidence

## 5. Evidence requirements

Every review item must preserve exact evidence references from the source report.
Acceptable evidence includes:

- `candidate_id` when present
- candidate `repeated_pattern`
- candidate `involved_files_or_events`
- candidate evidence rows with line numbers and line hashes
- source file path and source file SHA-256 from `source_files`
- metric key and value used to create the finding
- evidence-quality labels such as `explicit_classification`, `legacy_reason`,
  `legacy_policy_failure`, or `legacy_unknown`
- report path, report SHA-256, and report schema version

Evidence requirements:

- No vague "insight" claims.
- No candidate may be described as a real subsystem.
- Legacy evidence must stay labeled as legacy evidence.
- `legacy_unknown` evidence must not be merged with explicit
  `denial_category="unknown"` evidence.
- A review item without exact evidence references is invalid.
- A stale report hash invalidates the review item until regenerated or marked
  superseded.

## 6. Review-artifact schema

Future review artifacts should use a deterministic schema such as
`self_observation_review_artifact.v1`.

Required fields:

```text
review_artifact_id
schema_version
source_report_path
source_report_sha256
source_report_schema_version
candidate_id
finding_type
proposal_type
evidence_references
evidence_quality
decision_state
decision_trail
created_at
created_by
updated_at
updated_by
non_authority_disclaimer
```

`candidate_id` is required when the review item comes from a subsystem candidate.
It is null only for metric-only findings that have no candidate.

`non_authority_disclaimer` must state that the artifact is a review input and
does not authorize mutation, implementation, policy change, workflow change,
gate change, or state change.

`decision_trail` must be append-only in future implementations. A later decision
adds a new trail entry instead of editing prior human decisions.

## 7. Proposal types

Review artifacts may classify their proposed next step as one of:

- `instrumentation_proposal`: improve event fields, report fields, tests, or
  evidence capture without changing behavior.
- `workflow_proposal`: propose a workflow change for later governed review.
- `policy_proposal`: propose a policy change for later governed review.
- `no_action_monitor_only`: record the finding and keep observing.

The proposal type does not authorize implementation. It only narrows what kind
of governed proposal may be drafted if a human accepts the review item.

## 8. Human-decision record requirements

Future decision records must preserve:

- actor identity or stable operator label
- decision state
- decision reason
- timestamp from the decision event
- prior decision state
- source report hash
- review artifact ID
- candidate ID when present
- evidence references reviewed
- whether refinement was requested

Decision records must be append-only or otherwise auditable. A decision update
must not erase earlier decisions.

Human decisions may:

- queue a finding for review
- accept a finding for proposal drafting
- reject a finding
- defer a finding
- supersede a finding with a newer report or artifact

Human decisions may not directly mutate policy, workflows, gates, code, or
canonical state.

## 9. Governance boundaries

The review loop must never call mutation helpers or canonical write paths from
analytics. It must not import or invoke:

- transition event emitters
- state record writers
- registry appenders
- policy writers
- workflow writers
- transport ledger appenders
- autonomous execution tools

Analytics output is read-only input. The review layer may render artifacts and,
in a future approved slice, append review decision records. It must not write to
canonical governance ledgers unless a future governed design explicitly adds a
decision ledger and tests its boundary.

## 10. Future append-only decision-ledger design

A future implementation may introduce an append-only decision ledger after
separate review. A likely path is:

```text
data/state/self_observation_review_decisions.jsonl
```

This document does not create that ledger.

If implemented later, each row should include:

- `record_type: self_observation_review_decision`
- `record_version`
- `review_artifact_id`
- `source_report_sha256`
- `source_report_schema_version`
- `candidate_id`
- `previous_decision_state`
- `decision_state`
- `decision_reason`
- `decided_by`
- `decided_at`
- `evidence_references`
- `record_hash`

The ledger must be append-only, deterministic where possible, and tested for
path boundaries. It must not be used as policy authority.

## 11. Smallest safe implementation slice

The smallest safe future implementation is a local artifact renderer:

1. Read one existing `data/analytics/self_observation_report.json`.
2. Validate `schema_version == self_observation_report.v1`.
3. Compute `source_report_sha256`.
4. Select explicit candidates or metrics with exact evidence references.
5. Render deterministic JSON and Markdown review artifacts under a non-canonical
   analytics artifact path.
6. Include `decision_state: observed`.
7. Include an empty append-only `decision_trail`.
8. Refuse to render if evidence references are missing.

This slice should not create a decision ledger, queue, scheduler, dashboard, or
integration.

## 12. Likely future files

Likely future files for an implementation, if separately approved:

- `signal_agent/analytics/review_loop.py`
- `tests/test_self_observation_review_loop.py`
- `data/analytics/review/*.json`
- `data/analytics/review/*.md`

Only a later approved slice should consider:

- `data/state/self_observation_review_decisions.jsonl`

No future implementation should modify analytics detection rules merely to make
review artifacts appear more useful.

## 13. Test plan and stop conditions

Future tests should prove:

- analytics findings remain non-authoritative
- missing report hash blocks artifact creation
- missing evidence references block artifact creation
- candidate IDs are preserved when present
- metric-only findings preserve metric key, value, and report hash
- legacy evidence remains labeled as legacy
- explicit unknown classification remains separate from legacy unknown evidence
- decision state transitions are valid
- decision trail entries append instead of overwrite
- output paths cannot resolve into canonical state, config, source, governance,
  policy, workflow, or transition-gate directories
- generated artifacts are deterministic for identical inputs

Stop implementation if:

- a review artifact could authorize mutation
- analytics can write canonical state
- a candidate can become a governed proposal without human decision
- accepted review items bypass transition or policy controls
- evidence references are absent or vague
- implementation requires changing transition gates, policies, workflows, or
  analytics detector rules

## 14. Explicit connection to the governance kernel

The governance kernel invariant remains:

```text
No state change without validated, observable, governed transition.
```

The review loop connects to the kernel only as a bounded pre-proposal review
surface. It does not add a new authority path.

If a human accepts a review finding, the result is only a governed proposal. Any
actual implementation must still pass:

- transition gate validation
- policy evaluation
- declared mutation contracts
- append-only observability
- state and path boundary checks
- required human approval

The review loop therefore preserves the decision point instead of collapsing
observation into action.
