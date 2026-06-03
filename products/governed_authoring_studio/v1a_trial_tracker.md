# Governed Authoring Studio V1A Trial Tracker

Status: V1A trial tracker draft

## 1. Purpose

This document defines a lightweight tracker for the first 5-10 Governed
Authoring Studio V1A trial participants.

The tracker should convert trial activity into product evidence without
becoming a CRM, analytics dashboard, or user research database.

Use it to track whether the concierge-assisted workflow helps people move from
scattered material to a structured, usable artifact direction.

## 2. Tracker Boundary

The tracker records workflow status and product-learning signals.

It should not store:

- private source material
- full user notes
- sensitive personal details
- unnecessary demographics
- operator speculation
- public testimonials without permission

Keep private content in the intake/output workflow, not in this tracker.

## 3. Core Tracker Fields

Required fields:

- `participant_id`
- `invite_sent`
- `accepted`
- `intake_received`
- `output_delivered`
- `feedback_received`
- `aha_moment`
- `would_pay`
- `privacy_concern`
- `main_friction`
- `next_action`
- `status`

Optional fields:

- `artifact_type`
- `operator`
- `time_spent`
- `continuation_request`
- `automation_candidate`
- `notes`

Keep `notes` short and non-sensitive.

## 4. Tracker Table

Use this table for the first trial group:

Current internal participant key:

- `001`: Justin. Keep this key internal and remove or anonymize it before any
  public release snapshot unless explicit permission exists.

| participant_id | invite_sent | accepted | intake_received | output_delivered | feedback_received | aha_moment | would_pay | privacy_concern | main_friction | next_action | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 001 | ready | pending | no | no | no |  |  |  |  | send invite/intake | invited |
| P02 |  |  |  |  |  |  |  |  |  |  |  |
| P03 |  |  |  |  |  |  |  |  |  |  |  |
| P04 |  |  |  |  |  |  |  |  |  |  |  |
| P05 |  |  |  |  |  |  |  |  |  |  |  |
| P06 |  |  |  |  |  |  |  |  |  |  |  |
| P07 |  |  |  |  |  |  |  |  |  |  |  |
| P08 |  |  |  |  |  |  |  |  |  |  |  |
| P09 |  |  |  |  |  |  |  |  |  |  |  |
| P10 |  |  |  |  |  |  |  |  |  |  |  |

## 5. Field Definitions

### participant_id

Anonymous trial identifier.

Use `001`, `002`, etc. Do not use full names in the tracker table.

### invite_sent

Whether the trial invite was sent.

Suggested values:

- `yes`
- `no`
- `scheduled`

### accepted

Whether the participant agreed to try V1A.

Suggested values:

- `yes`
- `no`
- `pending`

### intake_received

Whether the intake form was submitted.

Suggested values:

- `yes`
- `no`
- `partial`
- `needs clarification`

### output_delivered

Whether the V1A output packet was delivered.

Suggested values:

- `yes`
- `no`
- `in progress`
- `blocked`

### feedback_received

Whether the participant answered the feedback form or equivalent follow-up.

Suggested values:

- `yes`
- `no`
- `partial`
- `pending`

### aha_moment

Whether the participant experienced the core value moment.

Suggested values:

- `clear`
- `partial`
- `no`
- `unclear`

### would_pay

Whether the participant showed willingness to pay.

Suggested values:

- `yes`
- `maybe`
- `no`
- `unclear`

### privacy_concern

Whether privacy concerns appeared.

Suggested values:

- `none`
- `minor`
- `major`
- `unclear`

### main_friction

The main observed friction point.

Use short labels:

- `artifact type`
- `source too thin`
- `intake unclear`
- `privacy`
- `spine mismatch`
- `draft generic`
- `review vague`
- `pricing`
- `scope`
- `none`

### next_action

What happens next.

Suggested values:

- `send intake`
- `request clarification`
- `prepare output`
- `send feedback form`
- `offer continuation`
- `close`
- `follow up later`

### status

Overall participant state.

Suggested values:

- `invited`
- `accepted`
- `intake`
- `in production`
- `delivered`
- `feedback`
- `completed`
- `closed`
- `blocked`

## 6. Optional Detail Table

Use only if useful:

| participant_id | artifact_type | operator | time_spent | continuation_request | automation_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- |
| 001 |  |  |  |  |  |  |
| P02 |  |  |  |  |  |  |
| P03 |  |  |  |  |  |  |
| P04 |  |  |  |  |  |  |
| P05 |  |  |  |  |  |  |

Do not use the optional table to store private source details.

## 7. Summary Metrics

After 5-10 participants, summarize:

```text
invites_sent:
accepted:
intakes_received:
outputs_delivered:
feedback_received:
clear_aha:
partial_aha:
would_pay_yes:
would_pay_maybe:
privacy_concerns_major:
continuation_requests:
top_friction:
top_automation_candidate:
private_alpha_recommendation:
```

Suggested `private_alpha_recommendation` values:

- `proceed`
- `proceed after fixes`
- `continue V1A`
- `pause and revise`

## 8. Decision Rule

Do not graduate to hosted private alpha only because the tracker is full.

Consider graduating only if:

- at least 5 users complete intake
- at least 3 users reach clear or partial aha
- at least 2 users show willingness-to-pay signal
- privacy concerns are understandable and manageable
- operator workflow is repeatable
- main friction points are known
- the next automation targets are obvious

The tracker should make the decision harder to self-deceive.

## 9. Next Action

Next practical action:

```text
products/governed_authoring_studio/prototype_v1a/
```

Do not create a summary template until after the first few trials produce
actual evidence.
