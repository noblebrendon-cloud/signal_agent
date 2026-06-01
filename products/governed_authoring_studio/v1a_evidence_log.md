# Governed Authoring Studio V1A Evidence Log

Status: V1A learning log template draft

## 1. Purpose

This document defines what to record during the first 5-10
concierge-assisted V1A users.

The evidence log exists to decide whether the V1A workflow is ready to graduate
from concierge-assisted thin UI into a hosted private alpha.

The goal is not to collect as much data as possible. The goal is to capture the
minimum useful evidence about whether users experience the core transformation:

```text
foggy thought -> structured artifact draft
```

## 2. Evidence Boundary

Record product-learning evidence, not private user profiles.

Capture:

- workflow friction
- artifact type clarity
- spine acceptance
- first draft usefulness
- privacy concerns
- willingness-to-pay signal
- time spent
- continuation request
- feature requests
- what should be automated next

Do not capture:

- unnecessary sensitive personal details
- private source material beyond what the workflow requires
- speculative personality judgments
- unrelated operator impressions
- marketing quotes without permission
- public examples without permission

## 3. Per-User Evidence Record

Use one record per V1A user/project.

Template:

```text
record_id:
date:
operator:
artifact_type:
artifact_stage:
intake_status:
source_sufficiency:
artifact_type_clarity:
clarification_needed:
spine_created:
spine_accepted:
first_draft_created:
first_draft_usefulness:
review_gate_status:
privacy_concerns:
willingness_to_pay_signal:
continuation_request:
feature_requests:
time_spent:
friction_points:
what_should_be_automated_next:
graduation_signal:
notes:
```

Keep `notes` factual, minimal, and focused on product learning.

## 4. Core Metrics

Track these across the first 5-10 users:

- number of completed intakes
- number accepted without clarification
- number needing clarification
- number out of scope
- number reaching spine preview
- number accepting spine
- number receiving first draft section
- number saying first draft was useful
- number raising privacy concerns
- number showing willingness to pay
- number requesting continuation
- average operator time per packet

These are not vanity metrics. They are graduation signals.

## 5. Aha Moment Evidence

The V1A aha moment is:

```text
The user sees messy thought become a structured artifact spine and one usable
reviewed draft section.
```

Record whether the user:

- recognized their idea in the spine
- found the structure useful
- thought the first draft sounded connected to their material
- understood the review gate
- knew what to do next
- wanted to continue the artifact

Possible values:

- clear aha
- partial aha
- no aha
- unclear

## 6. Friction Categories

Use these categories:

- landing/message confusion
- artifact type confusion
- insufficient source material
- intake form too long
- intake form too vague
- privacy hesitation
- operator clarification needed
- spine mismatch
- draft felt generic
- review felt vague
- export unclear
- pricing uncertainty
- campaign request before artifact
- out-of-scope request

Add new categories only if repeated friction appears.

## 7. Willingness-To-Pay Signal

Record willingness-to-pay after the user sees the first transformation, not
before.

Suggested values:

- no signal
- positive verbal signal
- asked for price
- requested paid continuation
- accepted founding-user offer
- declined due to price
- unclear

Suggested follow-up questions:

- Would you pay to continue this project?
- Would you pay to run another artifact through this workflow?
- Would you prefer a one-time project price or subscription?
- Which limit feels fair: active projects, reviews, exports, or drafts?

Do not pressure the user. The purpose is learning.

## 8. Privacy Concern Evidence

Record:

- whether the user hesitated to submit source material
- whether operator-assisted review was understood
- whether deletion/archive mattered
- whether user asked about AI/tool use
- whether user wanted sensitive details generalized
- whether source/output separation was reassuring

Do not record unnecessary sensitive details.

## 9. Automation Signals

Record what should be automated next only after observing repeated manual work.

Possible automation candidates:

- intake validation
- artifact type recommendation
- clarification prompt generation
- spine generation
- spine preview rendering
- draft section generation
- review gate formatting
- output packet assembly
- export generation
- evidence log summary

Do not automate a step only because it is possible. Automate when it is
repeated, bounded, and understood.

## 10. Graduation Criteria

V1A may be ready for hosted private alpha when:

- 5-10 users complete intake
- at least 3 users reach the aha moment
- at least 2 users show willingness-to-pay signal
- artifact type choices are understandable
- intake fields are stable
- spine format is stable
- first draft workflow is repeatable
- review gate criteria are useful
- privacy language is understandable
- manual workflow is becoming too slow to continue manually

Do not graduate only because the docs are strong. Graduate because observed
users prove the workflow.

## 11. Evidence Summary Template

After 5-10 users, summarize:

```text
total_users:
completed_intakes:
accepted_intakes:
needs_clarification:
out_of_scope:
clear_aha_count:
partial_aha_count:
no_aha_count:
willingness_to_pay_count:
continuation_requests:
top_friction_points:
top_privacy_concerns:
most_requested_features:
operator_time_average:
steps_to_automate_next:
private_alpha_recommendation:
```

Private alpha recommendation values:

- proceed
- proceed after fixes
- continue V1A
- pause and revise scope

## 12. Decision Use

Use the evidence log to decide:

- whether the V1A promise is clear
- whether the intake form works
- whether users trust the privacy note
- whether the output template feels productized
- whether the operator runbook is repeatable
- whether pricing interest exists
- whether hosted private alpha is justified

The evidence log should keep the team honest. The question is not "Could this
be built?" The question is "Did real users experience the transformation?"
