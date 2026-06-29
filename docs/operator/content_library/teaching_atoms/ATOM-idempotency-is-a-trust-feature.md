# ATOM-idempotency-is-a-trust-feature

Originating events:

- `EVT-2026-06-29-project-studio-governed-handoff`

## Concept

Idempotency is a trust feature.

## Why It Matters

Operators trust a system when retrying the same intent returns the same artifact
instead of creating duplicates. This event uses a deterministic handoff identity from
`proposal_id + draft_intent_ref`; the same handoff returns the existing Letter, while a
different `draft_intent_ref` can intentionally create a distinct draft.

## Evidence Trail

- `signal_agent/governed_publishing/drafting_brief.py::project_studio_draft_handoff_identity`
- `tests/test_project_studio_governed_handoff.py::test_same_proposal_plus_same_draft_intent_is_idempotent`
- `tests/test_project_studio_governed_handoff.py::test_same_proposal_with_different_draft_intent_creates_distinct_allowed_letter_draft`

## Reuse Notes

Useful for content about retries, stable identities, operator confidence, and
duplicate prevention.

