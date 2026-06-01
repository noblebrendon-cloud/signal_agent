# Governed Authoring Studio V1A Spec

Status: concierge-assisted thin UI specification draft

## 1. Purpose

This document defines V1A of Governed Authoring Studio: a concierge-assisted
thin UI that tests the core product transformation before building a full
hosted SaaS product.

V1A should prove:

```text
foggy thought -> structured artifact draft
```

It should simulate the product experience with a lightweight user-facing
surface and an operator-assisted backend workflow. The goal is real learning
from real users, not automation completeness.

## 2. Product Boundary

V1A is a public-facing test surface for Governed Authoring Studio.

It is not:

- the internal HQ cockpit
- a full hosted private alpha
- a publishing platform
- a campaign engine
- a team collaboration system
- a marketplace
- a full AI agent orchestration product

V1A should feel like a product, but it can rely on manual operator steps behind
the scenes as long as those steps are disclosed where trust requires it.

## 3. Target User

The first user is a person with serious unfinished ideas.

They have notes, fragments, rough outlines, recurring thoughts, teaching ideas,
or partial drafts. They believe there is a real artifact inside the material,
but they do not yet have a stable path from source material to finished shape.

Supported V1A artifact types:

- book / long-form manuscript
- essay series
- course or teaching outline

## 4. V1A Success Moment

The user reaches the V1A success moment when they receive:

- a structured artifact spine
- one usable draft section
- a review gate summary
- a portable plain text or markdown export

The user should be able to say:

```text
This turned my scattered thought into something I can continue.
```

## 5. User-Facing Screens

### Screen 1: Landing Page

Purpose: explain the product promise and invite a narrow first action.

Primary message:

```text
Turn serious unfinished ideas into structured, reviewable draft artifacts.
```

Required elements:

- short product promise
- artifact examples
- privacy reassurance
- one primary CTA: `Start an artifact`
- secondary link: `How it works`

Do not include:

- broad AI writing claims
- campaign engine promises
- enterprise language
- dashboard-heavy screenshots

### Screen 2: Project Intake

Purpose: create the initial project packet.

Required fields:

- name
- email
- project working title
- artifact type
- artifact stage
- desired outcome
- deadline or urgency, optional
- consent checkbox for operator-assisted review

Artifact type options:

- book / long-form manuscript
- essay series
- course or teaching outline
- not sure yet

Artifact stage options:

- loose notes
- rough outline
- partial draft
- scattered materials
- restarting a stalled project

### Screen 3: Source Capture

Purpose: collect messy source material without forcing the user to organize it.

Required fields:

- source notes
- important fragments
- existing outline or structure, optional
- examples or references, optional
- what this must not become

Supported input:

- pasted notes
- rough claims
- outline fragments
- voice memo transcript
- teaching notes
- chapter ideas
- essay ideas
- course module ideas

V1A should avoid file uploads unless needed. Pasted text is enough for the
first test.

### Screen 4: Clarify Intent

Purpose: collect the minimum direction needed to create a useful spine.

Required fields:

- intended audience
- core idea or thesis
- why this artifact matters
- desired tone
- constraints
- success definition

Optional fields:

- known sections or chapters
- examples to include
- examples to avoid
- voice notes

### Screen 5: Submission Confirmation

Purpose: set expectations after intake.

Required elements:

- confirmation that source was received
- summary of what was submitted
- privacy note
- expected turnaround time
- what the user will receive
- contact path for changes or deletion request

Expected deliverable:

```text
artifact spine + first draft section + review gate summary + export
```

### Screen 6: Spine Preview

Purpose: show the first visible transformation.

Required elements:

- project title
- artifact type
- core thesis or direction
- spine sections
- section purposes
- assumptions made
- source lineage summary
- user response controls

User response controls:

- approve spine
- request changes
- mark wrong assumption
- add missing source
- change artifact type

### Screen 7: Draft Section Delivery

Purpose: deliver one usable section tied to the approved or revised spine.

Required elements:

- selected section title
- section purpose
- draft body
- source references summary
- review readiness status
- user feedback controls

User feedback controls:

- this feels usable
- this feels generic
- missing example
- wrong direction
- revise with note

### Screen 8: Review Gate Summary

Purpose: make the review state visible before export.

Review checks:

- clarity
- coherence
- audience fit
- artifact alignment
- overclaiming
- missing examples
- next-step readiness

Required elements:

- summary
- strengths
- issues
- recommended edits
- readiness state
- next recommended action

The review gate must not silently rewrite the draft.

### Screen 9: Export / Next Step

Purpose: give the user a portable artifact and ask what should happen next.

Required elements:

- export as plain text
- export as markdown
- copyable text
- next-step prompt
- willingness-to-pay question
- optional follow-up call request

Next-step options:

- continue drafting this artifact
- revise the spine
- add more source material
- start another artifact
- stop and export

## 6. Operator Workflow

V1A depends on an operator-assisted workflow behind the scenes.

### Operator Step 1: Review Intake

Check:

- artifact type is clear enough
- source material is sufficient
- privacy expectations are understood
- user gave consent for assisted review
- project is within V1A scope

Possible operator actions:

- accept intake
- ask clarification question
- request more source material
- reject as out of scope

### Operator Step 2: Build Project Packet

Create a working packet containing:

- user identity/contact
- project title
- artifact type
- source material
- clarification answers
- constraints
- must-not-become notes
- operator notes

### Operator Step 3: Generate Artifact Spine

Use the source packet to create:

- thesis or central direction
- artifact structure
- section list
- section purposes
- assumptions
- source lineage summary

Operator checks:

- spine matches artifact type
- spine reflects user source
- spine avoids generic AI structure
- assumptions are visible
- no source is silently overwritten

### Operator Step 4: Send Spine Preview

Send the user:

- spine preview
- assumptions
- approval/change options
- request for missing source if needed

Stop until the user approves or requests changes.

### Operator Step 5: Draft First Section

After spine approval, create one draft section.

Draft should use:

- approved spine
- selected spine section
- source material
- clarification answers
- constraints
- must-not-become notes

Operator checks:

- draft sounds connected to the user source
- draft follows section purpose
- draft avoids generic phrasing
- draft is not over-polished into a different voice

### Operator Step 6: Run Review Gate

Create a review summary for the draft section.

Review outputs:

- strengths
- issues
- suggested edits
- readiness state
- next recommended action

The operator may lightly format the review, but should not hide meaningful
weaknesses.

### Operator Step 7: Deliver Export

Deliver:

- spine
- first draft section
- review summary
- plain text or markdown export
- next-step prompt

### Operator Step 8: Record Learning

Record non-sensitive learning:

- time to complete
- where the user hesitated
- whether artifact type was clear
- whether source was sufficient
- whether the user reached the aha moment
- willingness-to-pay signal
- privacy concerns
- next requested feature

Operator notes should not become a shadow user profile.

## 7. Input Packet

V1A input packet fields:

- user_name
- user_email
- project_title
- artifact_type
- artifact_stage
- desired_outcome
- deadline_or_urgency
- source_notes
- important_fragments
- existing_structure
- intended_audience
- core_idea
- why_it_matters
- desired_tone
- constraints
- must_not_become
- success_definition
- consent_for_operator_assisted_review

Minimum viable packet:

- user_email
- artifact_type
- source_notes
- intended_audience
- core_idea
- desired_outcome
- consent_for_operator_assisted_review

If the minimum packet is incomplete, V1A should ask for clarification before
creating the spine.

## 8. Output Packet

V1A output packet fields:

- project_title
- artifact_type
- artifact_spine
- spine_assumptions
- source_lineage_summary
- selected_section
- first_draft_section
- review_gate_summary
- review_findings
- readiness_state
- export_plain_text
- export_markdown
- next_recommended_action
- willingness_to_pay_prompt

The output should distinguish:

- user source
- generated structure
- generated draft
- review findings
- export artifact

## 9. Manual Steps To Preserve

Do not automate these too early:

- judging whether the intake is in scope
- deciding whether source material is sufficient
- checking whether the spine feels specific
- detecting generic draft voice
- deciding whether review findings are useful
- interpreting user hesitation
- pricing and willingness-to-pay conversation

These manual steps are where V1A learns.

## 10. Manual Steps To Avoid Hiding

These should be disclosed or made legible:

- a human/operator may review submitted source material
- output is assisted, not fully automated
- source material is private by default
- source and generated output remain separate
- user can request deletion
- user controls whether work continues

Trust loss here would poison the product. The assisted nature of V1A is allowed;
surprise operator access is not.

## 11. State Model For V1A

V1A should use a simplified visible state model:

### Submitted

- Meaning: intake and source material received.
- Next action: operator reviews intake.

### Needs Clarification

- Meaning: source or direction is insufficient.
- Next action: user answers follow-up question.

### Spine Ready

- Meaning: artifact spine is ready for user approval.
- Next action: user approves or requests changes.

### Draft In Progress

- Meaning: approved spine is being used to draft one section.
- Next action: operator prepares draft and review.

### Review Ready

- Meaning: draft and review gate summary are ready.
- Next action: deliver to user.

### Export Delivered

- Meaning: user has received a portable artifact.
- Next action: ask next-step and willingness-to-pay questions.

## 12. Data Handling During V1A

Store only what is needed:

- contact info
- project intake
- source notes
- clarification answers
- generated spine
- draft section
- review summary
- export record
- operator learning notes

Do not collect:

- demographics
- social graph
- contacts
- location
- external platform credentials
- unnecessary analytics
- public profile data

Privacy rules:

- no public sharing by default
- disclose operator access
- provide export
- delete on request
- keep source and generated outputs separate
- do not use user projects in marketing without explicit permission

## 13. Pricing Test

Do not charge before the user sees the first transformation.

Ask after delivery:

- Would you pay to continue this project?
- Would you pay to start another artifact?
- Would you prefer a one-time project price or subscription?
- Which limit feels fair: active projects, reviews, exports, or drafts?

Possible V1A pricing tests:

- free first artifact test
- founding-user paid continuation
- manual invoice for continued drafting
- Creator tier interest list

Do not price by personal/private data entered.

## 14. Success Criteria

V1A is successful if:

- 5-10 users complete intake
- at least 3 users reach the aha moment
- at least 2 users say they would pay
- users understand what the product does without long explanation
- users trust the handling of private source material
- the artifact data model still holds
- the operator workflow exposes repeated friction
- users can describe what became clearer
- users know what to do next after export

The strongest signal is not praise. It is a user continuing the artifact or
asking to run another serious idea through the workflow.

## 15. Failure Criteria

V1A is not ready to graduate if:

- users submit too little usable source
- users think it is generic AI writing
- users do not understand artifact type choices
- users do not trust operator-assisted review
- users like the output but do not continue
- operator labor is too high before value is proven
- review gates feel vague
- the draft feels disconnected from source
- people mainly ask for campaign generation instead of artifact creation

Failure is useful if it shows what to simplify before hosted alpha.

## 16. Private Alpha Graduation Checklist

Graduate to hosted private alpha only when:

- the intake fields are stable
- the spine format is stable
- the first draft workflow is repeatable
- review gate criteria are useful
- privacy language is understandable
- users reach the aha moment
- at least some users show willingness to pay
- manual operator steps are well understood
- the hosted app can map directly to observed behavior

The private alpha should automate a proven workflow, not rescue an unclear one.

## 17. Next Build Artifacts

Before implementation, create:

- `v1a_intake_form.md`
- `v1a_operator_runbook.md`
- `v1a_output_template.md`
- `v1a_privacy_note.md`

These should be created before choosing a frontend stack.
