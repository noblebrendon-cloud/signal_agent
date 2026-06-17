# v0.2 Authority Model Spec

Version target:

```text
v0.2-local-authoring-surface
```

## Purpose

This spec defines how v0.2 may represent local human review and approval without claiming production identity, authentication, or real-world authority integration.

## Authority Boundary

v0.2 may use a local reviewer marker.

v0.2 must not claim:

- Production user identity.
- Hosted authentication.
- Legal authority.
- Organization-wide approval.
- Production publishing authorization.

## Required Fields

A local authoring review record should distinguish:

- Local reviewer marker.
- Review status.
- Evidence refs.
- Output status.
- Unresolved tensions.
- Self-certification status.

## Local Reviewer Marker

The local reviewer marker identifies who performed local review for the current proof workflow.

It is:

- A local workflow field.
- Explicitly provided.
- Suitable for local proof summaries.

It is not:

- A production identity.
- An authenticated account.
- A durable authority registry.
- A publishing approval.

## Review Status

Review status should remain explicit. Suggested statuses:

- `draft`
- `provisional`
- `approved`
- `rejected`
- `deferred`

Review status must not be inferred from generated content alone.

## Evidence Refs

Evidence refs remain required for anchored or approval-ready claims.

The model should preserve:

- Source packet evidence refs.
- Bridge evidence refs.
- Backend result evidence refs.
- Result packet evidence refs.

## Output Status

Output status must remain separate from review status.

Allowed local output statuses should stay aligned with existing proof-pack behavior:

- `provisional`
- `approved`
- `rejected`
- `deferred`

## Unresolved Tensions

Unresolved tensions must remain visible in local outputs.

Blocking unresolved tensions should defer promotion or approval in covered local workflows.

## Self-Certification Rejection

Generated/model output must not certify itself.

The local authority model must preserve rejection or blocking behavior for generator/model self-approval attempts.

## Decision Gate

Before runtime implementation, Phase 22 or a later phase must answer:

- What exact local reviewer marker format is allowed?
- Is the marker optional for draft workflows?
- Is the marker required for approved outputs?
- How are self-certification attempts detected?
- How is local review represented in proof summaries?
- How does local review map to result packets?

## Non-Goals

This authority model does not prove:

- Production identity.
- Authentication.
- Authorization.
- Legal approval.
- Publication approval.
- Repo-wide authority enforcement.
