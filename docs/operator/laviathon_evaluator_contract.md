# Laviathon Evaluator Contract

## Purpose

This contract defines the smallest local-only Laviathon evaluator layer over Stage 1 Spine Observability. The evaluator records structured observations about system design, AI orchestration, execution integrity, and coherence risks without performing any external action.

The current implementation normalizes observation records, rejects unsafe or malformed records, and can append validated observations to a local-only JSONL ledger.

## Identity Boundary

Laviathon is a governed synthetic systems evaluator.

It may act as:

- A systems design critic.
- An AI orchestration evaluator.
- An execution integrity observer.
- A coherence and risk reviewer.

It must not act as:

- A human.
- An autonomous agent.
- A contact, posting, or messaging authority.
- A public-facing publisher.
- A source of externally approved action.

Laviathon output is human-approved output only.

## Safety Contract

- Local validation first.
- Append-only local persistence only.
- Runtime writes are limited to `data/state/laviathon_observations.jsonl` under the active `SIGNAL_AGENT_ROOT`.
- No network calls.
- No APIs.
- No scraping.
- No posting.
- No messaging.
- No scheduling.
- No autonomous external action.
- `external_action_allowed` must always be `false`.
- `review_status` defaults to `pending`.
- `requires_human_review` defaults to `true`.
- `public_post_candidate` observations must require human review and start as `pending`.
- The human operator remains the approving authority.

## What This Patch Does

- Adds a pure Laviathon observation validator under `app/spine_observability/laviathon.py`.
- Adds a minimal append-only observation store under `app/spine_observability/laviathon_store.py`.
- Defines narrow allowed values for `spine_target`, `observation_type`, and `review_status`.
- Normalizes valid observation records into a deterministic shape.
- Generates deterministic `observation_id` values from stable observation content.
- Rejects invalid, unsafe, or identity-confused records fail-closed.
- Appends only validated observations to `data/state/laviathon_observations.jsonl`.
- Adds tests for valid normalization, invalid values, safety gates, defaults, determinism, append-only persistence, and source-level external-action primitives.

## What This Patch Does Not Do

- Does not add a CLI.
- Does not integrate with external services.
- Does not collect metrics.
- Does not publish or message.
- Does not approve public output.
- Does not change existing spine observability runtime behavior.
- Does not commit generated runtime state.

## Persistence Boundary

The observation store is intentionally narrow:

- It validates every observation with `normalize_observation` before append.
- It writes only to `data/state/laviathon_observations.jsonl` at runtime.
- It reuses the existing local JSONL hash-chain store pattern.
- It lists stored observations read-only.
- It can list read-only human-review candidates without changing review status.
- It rejects invalid observations before a state file is created or appended.
- It does not create external side effects.

## Review Candidates

The review-candidates helper is read-only. It returns observations where `requires_human_review` is `true`, defaults to `review_status=pending`, and can explicitly include all review statuses for audit views.

It may filter by `observation_type`, including `public_post_candidate`, but it does not approve, reject, post, schedule, message, or otherwise act on the candidate.

## Observation Fields

Normalized observations include:

- `schema_version`
- `observation_id`
- `created_at`
- `source_context`
- `spine_target`
- `observation_type`
- `claim`
- `evidence`
- `recommendation`
- `public_safe`
- `requires_human_review`
- `review_status`
- `external_action_allowed`

Allowed `spine_target` values:

- `reflective`
- `governance`
- `retention`
- `dashboard`
- `unknown`

Allowed `observation_type` values:

- `critique`
- `risk`
- `opportunity`
- `coherence_check`
- `public_post_candidate`

Allowed `review_status` values:

- `pending`
- `approved`
- `rejected`

## Validation Rules

- Missing required fields fail closed.
- Unknown fields fail closed.
- Invalid `spine_target` fails closed.
- Invalid `observation_type` fails closed.
- Invalid `review_status` fails closed.
- `external_action_allowed=True` fails closed.
- `public_post_candidate` must require human review.
- `public_post_candidate` must start with `review_status=pending`.
- `review_status` defaults to `pending` if omitted.
- `requires_human_review` defaults to `true` if omitted.
- Human self-representation is rejected.
- Observation IDs are deterministic from stable observation content.

## Relationship To Spine Observability

Stage 1 Spine Observability tracks local spines, platform accounts, and manual metric snapshots. Laviathon observations sit above that layer as local structured evaluations of system coherence and risk.

This validator does not depend on live platform data. It can target the conceptual spine areas `reflective`, `governance`, `retention`, `dashboard`, or `unknown`.

## Next Step

After the validator, append-only store, and read-only review candidate helper remain stable, the next safe step is a small operator-facing surface for listing observations. Any future status transition or CLI patch should remain local-only, fail-closed, and human-review gated.
