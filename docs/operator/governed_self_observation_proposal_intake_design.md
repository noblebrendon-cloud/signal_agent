# Governed Proposal Intake From Self-Observation Review Decisions

## 1. Purpose

This document defines a planning-only Phase 3 design for turning a resolved
`accepted_for_proposal` self-observation review decision into a bounded
proposal-intake candidate.

The intended future flow is:

```text
self_observation_review_resolution.v1
-> proposal-intake candidate
-> existing governance controls
-> separately authorized implementation
```

The intake candidate is only a structured handoff object. It is not a governed
proposal, not an approval, and not implementation authority.

## 2. Non-goals

Phase 3 must not implement:

- proposal execution
- governed proposal submission
- queues, schedulers, dashboards, monitors, or integrations
- policy, workflow, or transition-gate changes
- canonical state writes
- mutation of review artifacts, review events, or analytics reports
- autonomous conversion from analytics evidence into implementation work

Analytics findings, review artifacts, review events, and resolved status are
never implementation authority.

## 3. Existing Source Contracts

The existing self-observation review contracts are:

- `self_observation_review_artifact.v1` from
  `signal_agent/analytics/review_loop.py`
- `self_observation_review_event.v1` from
  `signal_agent/analytics/review_loop.py`
- `self_observation_review_resolution.v1` from
  `signal_agent/analytics/review_state.py`

The existing governance surfaces found in this branch are:

- `app/hq/governance/transition_gate.py`: validates lifecycle transitions and
  emits canonical transition events to `data/state/transition_gate_events.jsonl`
  when callers record attempts.
- `docs/architecture/TRANSITION_GATE.md`: documents that transition validation
  reads `config/state_machine.yaml`, `config/policies/*`, and
  `config/lanes.yaml`, and that the gate must sit before durable mutation.
- `signal_agent/formal_governance/models.py`: defines `TransitionProposal`,
  `PromotionDecision`, and ledger entry payloads.
- `signal_agent/formal_governance/gates.py`: defines lineage, invariant,
  branch-vector, evidence, unresolved-tension, human-authority, rollback, and
  duplicate gates.
- `signal_agent/formal_governance/decision.py`: evaluates a
  `TransitionProposal` through the formal gates and creates deterministic
  decision IDs.
- `signal_agent/formal_governance/ledger.py`: builds and appends hash-linked
  governed transition ledger entries.
- `signal_agent/formal_governance/adapters.py`: contains existing adapters for
  known runtime surfaces, including operator runtime evidence.
- `app/governed_shell/*`: provides a separate command-proposal validation and
  policy-review surface. It is execution-oriented and must not be treated as the
  default target for self-observation intake without a later design decision.

This document does not claim that any existing service already accepts
self-observation proposal-intake candidates.

## 4. Required Preconditions For Proposal Intake

A future intake candidate may be created only when all of these are true:

- The source artifact validates as `self_observation_review_artifact.v1`.
- The source decision event validates as `self_observation_review_event.v1`.
- The resolver output validates as `self_observation_review_resolution.v1`.
- The resolver output has `resolved_review_state == accepted_for_proposal`.
- The latest matching decision event is the accepted decision named by the
  resolver.
- The artifact, decision, and resolver agree on `review_artifact_id`,
  `candidate_id`, and `source_report_sha256`.
- The artifact preserves exact evidence references.
- A separate human authorization for intake is supplied. The prior
  `accepted_for_proposal` decision is not enough.

If any precondition fails, no intake candidate may be produced.

## 5. Required Source Evidence

From the artifact:

- `review_artifact_id`
- `source_report_sha256`
- `source_report_schema_version`
- `candidate_id`
- `finding_type`
- `proposal_type`
- `evidence_references`
- `evidence_quality`
- `created_by`
- `created_at`
- `non_authority_disclaimer`

From the latest accepted decision event:

- `decision_record_id`
- `review_artifact_id`
- `decision_state == accepted_for_proposal`
- `decided_by`
- `decision_reason`
- `decided_at`
- `source_report_sha256`
- `candidate_id`
- `non_authority_disclaimer`

From the resolver output:

- `schema_version`
- `review_artifact_id`
- `candidate_id`
- `source_report_sha256`
- `initial_review_state`
- `resolved_review_state`
- `matching_decision_event_count`
- `latest_decision_record_id`
- `latest_decision_line_number`
- `resolution_method`
- `non_authority_disclaimer`

The future implementation should compute a deterministic resolution reference,
such as a SHA-256 hash of canonical resolver JSON, and preserve it as
`source_resolution_hash`.

## 6. Proposed Proposal-Intake Candidate Schema

Future schema name:

```text
self_observation_proposal_intake_candidate.v1
```

Required fields:

- `schema_version`
- `proposal_intake_candidate_id`
- `source_review_artifact_id`
- `source_decision_record_id`
- `source_resolution_hash`
- `source_report_sha256`
- `candidate_id`
- `finding_type`
- `proposal_type`
- `exact_evidence_references`
- `evidence_quality`
- `human_authorization_identity`
- `human_authorization_role`
- `human_authorization_scope`
- `human_authorization_timestamp`
- `authorization_reason`
- `non_authority_to_authority_transition_rationale`
- `intake_status`
- `created_by`
- `created_at`
- `non_authority_disclaimer`

Allowed `intake_status` values for the first slice:

- `candidate_created`
- `rejected_precondition_failed`

The ID should be deterministic from:

- source artifact ID
- source decision record ID
- source resolution hash
- source report hash
- proposal type
- exact evidence hash
- explicit human authorization identity, scope, reason, and timestamp

The intake candidate must not contain executable steps, shell commands, policy
edits, workflow edits, or transition mutations.

## 7. Object Distinctions

- Review artifact: immutable evidence-backed human-review input generated from
  a self-observation report candidate.
- Accepted review event: append-only human decision saying the review artifact
  is eligible for later governed-proposal intake.
- Proposal-intake candidate: a future structured handoff object that preserves
  review evidence, accepted decision provenance, resolver status, and separate
  human intake authorization.
- Governed proposal: a later object shaped for an existing governance surface,
  such as formal governance or another separately approved proposal contract.
- Approved implementation: a separate change that has passed transition
  validation, policy evaluation, declared mutation contracts, append-only
  observability, and required human approvals.

The proposal-intake candidate is still non-authoritative. It only packages the
record so a later governed proposal can be drafted or rejected.

## 8. Human Authorization Requirements

The future Phase 3 intake command must require explicit human authorization
separate from the original `accepted_for_proposal` event.

Required authorization fields:

- stable human identity
- role
- scope
- timestamp supplied by the caller
- reason
- acknowledgement that intake does not authorize implementation

Self-certification by analytics, a model, an agent, or generated text must not
satisfy this authorization. This aligns with the formal governance
`human_authority_gate`, which rejects missing or self-certified authority for
state promotion.

## 9. Idempotency And Duplicate Prevention

Future intake must be deterministic and duplicate-resistant:

- Compute `proposal_intake_candidate_id` from canonical source material and
  explicit authorization metadata.
- Refuse to overwrite an existing candidate with the same ID.
- Refuse to create a second candidate for the same artifact, decision, and
  resolution hash unless the authorization metadata differs and the output makes
  the distinction explicit.
- Detect stale resolver output by recomputing or re-reading the current
  resolution before candidate creation.
- Do not use wall-clock time by default.

Duplicate prevention here does not replace existing formal-governance duplicate
gates. It only prevents duplicate intake artifacts.

## 10. Provenance And Lineage Requirements

Every future intake candidate must preserve:

- source review artifact path and hash
- source decision log path, line number, and decision record ID
- source resolver JSON hash
- source report hash
- candidate ID
- exact evidence references
- evidence quality
- proposal type
- human authorization identity, scope, reason, and timestamp
- non-authority-to-authority transition rationale

The rationale must explain why a human believes the accepted review item is
ready to become an intake candidate. It must not claim that implementation is
authorized.

## 11. Canonical Versus Noncanonical Storage Boundaries

Phase 1 and Phase 2 review outputs live under:

```text
data/analytics/review/
```

That location is noncanonical analytics storage. A Phase 3 intake candidate
should initially remain noncanonical, for example:

```text
data/analytics/review/intake_candidates/<proposal_intake_candidate_id>.json
data/analytics/review/intake_candidates/<proposal_intake_candidate_id>.md
```

The first implementation should not write `data/state`, formal-governance
ledgers, transition-gate events, policy files, workflow definitions, or source
modules.

Only a later approved governed-proposal step may write canonical state, and only
through the existing authority path for that state.

## 12. Connection To The Transition Gate

The proposal-intake candidate does not call the transition gate.

The connection to the transition gate is indirect and later:

1. A human-authorized intake candidate is created as noncanonical evidence.
2. A separate governed proposal is drafted from that evidence.
3. The governed proposal must choose a real existing governance surface.
4. Any state-changing implementation must run through the relevant transition
   gate, policy evaluation, mutation contract, observability, and approval
   requirements for that surface.

The transition gate remains between intent and durable mutation. Phase 3 must
not create a side path around `validate_transition()` or formal governance
evaluation.

## 13. Smallest Safe Implementation Slice

The smallest safe future build is a local, explicit intake-candidate renderer:

1. Read one review artifact from `data/analytics/review/artifacts/`.
2. Read `data/analytics/review/decisions.jsonl`.
3. Run or consume the read-only resolver result.
4. Require `resolved_review_state == accepted_for_proposal`.
5. Require the latest accepted decision event referenced by the resolver.
6. Require explicit human intake authorization fields.
7. Render deterministic JSON and Markdown under
   `data/analytics/review/intake_candidates/`.
8. Refuse duplicates and stale resolver evidence.

This slice must not create a governed proposal or write canonical state.

## 14. Likely Future Files

Likely files for the smallest implementation:

- `signal_agent/analytics/proposal_intake.py`
- `tests/test_self_observation_proposal_intake.py`
- generated, untracked or separately governed files under
  `data/analytics/review/intake_candidates/`

Potential later files, only after separate design approval:

- an adapter from `self_observation_proposal_intake_candidate.v1` to
  `signal_agent.formal_governance.models.TransitionProposal`
- formal-governance fixture tests for self-observation-derived proposals
- documentation mapping proposal-intake candidate fields to formal-governance
  evidence references

This document does not approve any of those later files.

## 15. Required Tests

Future tests should prove:

- rejected unless resolver state is `accepted_for_proposal`
- rejected when artifact, decision, and resolver hashes disagree
- rejected when latest decision record is not the accepted event named by the
  resolver
- rejected without explicit human intake authorization
- rejected when authorization is self-certified by analytics, model, or agent
- deterministic candidate ID and byte-stable JSON and Markdown
- duplicate candidate ID does not overwrite existing output
- path guard rejects `data/state`, `config`, `governance`, `constraints`,
  `formal_governance`, `signal_agent`, and `app`
- no transition emitters, state writers, registry appenders, policy writers,
  workflow writers, transport ledger appenders, proposal execution services,
  queue services, or scheduler services are imported
- existing Phase 1 and Phase 2 tests remain green
- generated intake candidates do not create formal governance ledger entries

## 16. Stop Conditions

Stop implementation if:

- an intake candidate can authorize implementation
- analytics output can bypass human intake authorization
- a candidate can write canonical state
- proposal execution, queueing, scheduling, or dashboard behavior becomes
  necessary
- implementation requires policy, workflow, gate, or detector-rule changes
- evidence references are missing, stale, or vague
- a future adapter would need to pretend that current repository services
  already support self-observation proposal intake

The correct boundary is boring on purpose: preserve evidence, require a human
handoff decision, and leave every real mutation behind the existing governance
controls.
