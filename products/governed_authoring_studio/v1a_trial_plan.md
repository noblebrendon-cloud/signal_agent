# Governed Authoring Studio V1A Trial Plan

Status: V1A trial planning draft

## 1. Purpose

This document defines how to run the first 5-10 Governed Authoring Studio V1A
trials.

V1A is a concierge-assisted thin UI. The trial should test whether real users
experience the core transformation as valuable:

```text
foggy thought -> structured artifact draft
```

The trial is not a launch. It is a learning loop.

## 2. Trial Goal

The goal is to determine whether the V1A workflow is strong enough to justify a
hosted private alpha.

The trial should answer:

- Do users understand the promise?
- Can users submit useful source material?
- Do users understand the artifact type choices?
- Does the spine feel useful?
- Does the first draft section feel connected to their source?
- Does the review gate help them know what to do next?
- Do users trust the privacy/operator-access model?
- Do some users show willingness to pay?

## 3. Trial Size

Start with:

```text
5-10 users
```

This is enough to expose repeated friction without creating a support burden
before the workflow is stable.

Do not expand the trial until:

- intake fields are stable
- output packet is repeatable
- operator runbook is usable
- privacy note is understandable
- evidence log can be filled consistently

## 4. Invite Criteria

Invite people who:

- have a serious unfinished idea
- have notes, fragments, rough outlines, or partial drafts
- are willing to share source material under the V1A privacy note
- can give direct feedback
- are not expecting a complete done-for-you product
- understand this is an early concierge-assisted trial

Good early users:

- writers
- educators
- founders
- researchers
- operators
- coaches
- artists
- builders with a concrete artifact idea

Avoid for the first trial:

- users who need legal, medical, financial, or regulated advice
- users who primarily want campaign automation
- users who want team collaboration
- users who need enterprise privacy/security review
- users who want a full manuscript/course completed immediately

## 5. Trial Invitation Copy

Draft invitation:

```text
I am testing an early version of Governed Authoring Studio, a concierge-assisted
workflow for turning serious unfinished ideas into a structured artifact spine
and one reviewed draft section.

This is not a finished app yet. For the trial, you would submit notes or rough
material, answer a few direction questions, and receive a structured spine, one
draft section, a review summary, and a portable export.

The goal is to learn whether this helps people make real progress on work that
has been stuck in fragments.
```

Include:

- expected time to submit
- what they receive
- privacy/operator-access note
- no obligation to continue
- feedback request

## 6. Trial Flow

Use this flow for each participant:

```text
invite
-> consent/privacy note
-> intake form
-> operator review
-> clarification if needed
-> spine preview
-> first draft section
-> review gate summary
-> output packet
-> feedback questions
-> evidence log
```

Do not skip the evidence log. The trial exists to produce learning.

## 7. Participant Experience

The participant should experience:

- clear explanation of V1A
- simple intake
- privacy and operator-access disclosure
- no pressure to submit sensitive material
- visible transformation from source to spine
- one usable draft section
- specific review summary
- clear next step
- optional continuation path

The participant should not experience:

- surprise manual review
- pressure to publish
- pressure to pay before seeing value
- generic AI writing
- scope creep into campaign work
- hidden use of their material

## 8. Operator Procedure

For every trial:

1. Review intake.
2. Mark status: Accepted, Needs Clarification, Out of Scope, or Declined.
3. Ask clarification questions if needed.
4. Create artifact spine.
5. Send spine preview or proceed according to trial workflow.
6. Draft one section.
7. Run review gate.
8. Prepare output packet.
9. Deliver export.
10. Ask feedback questions.
11. Fill evidence log.

Use:

- `v1a_intake_form.md`
- `v1a_operator_runbook.md`
- `v1a_output_template.md`
- `v1a_privacy_note.md`
- `v1a_evidence_log.md`

## 9. Feedback Questions

Ask after the output packet:

- Did the spine reflect your idea?
- Did the first draft section feel useful?
- Did the draft sound connected to your source material?
- Was the review summary specific enough?
- Did you know what to do next?
- Did anything feel too generic?
- Did anything feel too heavy or confusing?
- Did the privacy/operator-access explanation feel clear?
- Would you pay to continue this project?
- Would you run another artifact through this workflow?
- What would you want automated next?

Do not ask all questions if the user is tired. Prioritize the evidence needed
for the graduation decision.

## 10. Success Criteria

The trial is successful if:

- 5-10 users complete intake
- at least 3 users reach the aha moment
- at least 2 users show willingness-to-pay signal
- most users understand the privacy note
- most users understand what they receive back
- spine format is accepted or easy to revise
- first draft section feels useful to at least some users
- operator time is understandable
- repeated friction points are visible

The strongest signal is continuation: a user wants to keep working on the same
artifact or submit another serious idea.

## 11. Failure Criteria

Pause or revise V1A if:

- users do not understand the product promise
- users submit unusable source material repeatedly
- artifact type choices confuse most users
- operator-assisted review creates trust problems
- output feels generic
- review gates feel vague
- users do not want to continue after output
- operator time is too high before value is proven
- users mainly want non-MVP features

Failure should produce a simpler next trial, not immediate feature expansion.

## 12. What Not To Build Yet

Do not build yet:

- full hosted SaaS
- team collaboration
- campaign engine
- PDF publishing
- direct social posting
- analytics dashboard
- marketplace
- mobile app
- complex billing
- automatic Zenodo/ORCID/OpenAIRE submission
- advanced version control UI

Build only after evidence shows the workflow needs automation.

## 13. Hosted Private Alpha Decision

Move to hosted private alpha only if:

- V1A produces repeated aha moments
- users understand the workflow
- users trust the privacy model
- users show willingness to pay
- operator steps are repeatable
- intake/output formats stabilize
- the data model still holds
- manual workflow becomes too slow to continue

If these conditions are not met, continue V1A or revise the product boundary.

## 14. Trial Summary Template

After the first 5-10 users, summarize:

```text
trial_dates:
participants_invited:
participants_completed:
accepted_intakes:
needs_clarification:
out_of_scope:
clear_aha_count:
partial_aha_count:
no_aha_count:
willingness_to_pay_count:
continuation_requests:
top_friction_points:
privacy_concerns:
most_requested_features:
average_operator_time:
recommended_next_step:
```

Recommended next step values:

- continue V1A
- revise V1A
- prepare hosted private alpha
- pause product build

## 15. Next Artifact

Next likely artifact after the trial plan:

```text
products/governed_authoring_studio/v1a_trial_invite.md
```

That document should turn the trial plan into invitation copy, consent copy,
and follow-up questions ready for actual participants.
