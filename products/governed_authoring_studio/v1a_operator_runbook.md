# Governed Authoring Studio V1A Operator Runbook

Status: V1A operator procedure draft

## 1. Purpose

This document defines the repeatable operator procedure for the manual and
concierge side of Governed Authoring Studio V1A.

V1A is not a full hosted SaaS product. It is a concierge-assisted thin UI that
tests whether a real user can move from messy source material into a structured
artifact spine and one reviewed draft section.

The operator process converts a submitted intake packet into:

- clarified direction
- artifact spine
- first draft section
- review gate summary
- exportable output packet
- operator notes

The runbook exists so V1A is handled consistently instead of improvised for
each user.

## 2. Operator Boundary

### Operator does

- validate intake completeness
- protect user intent
- clarify ambiguity
- generate or assist with artifact spine
- draft one first section
- run review gate
- prepare export packet
- record operator notes
- flag privacy or scope issues
- preserve source material separately from generated output
- mark assumptions visibly

### Operator does not

- silently overwrite source
- invent private facts
- publish anything for the user
- expose user content publicly
- turn the work into generic AI content
- promise legal, medical, financial, or other professional advice
- complete the full artifact unless explicitly part of a later paid workflow
- use user material in marketing without explicit permission
- collect unnecessary personal data

## 3. Input Packet

The operator starts with the V1A intake packet.

Required intake fields:

- contact
- artifact type
- messy notes/source material
- desired output
- audience
- tone/style
- constraints
- examples/references if supplied
- privacy acknowledgment
- delivery preference

Expected packet fields:

- `user_name`
- `user_email`
- `preferred_follow_up_method`
- `artifact_type`
- `artifact_stage`
- `project_title`
- `source_notes`
- `important_fragments`
- `existing_structure`
- `desired_output`
- `first_section_preference`
- `usefulness_definition`
- `audience`
- `audience_outcome`
- `why_it_matters`
- `problem_answered`
- `desired_tone`
- `must_not_sound_like`
- `constraints`
- `phrases_to_preserve`
- `example_material`
- `inspirations`
- `things_to_avoid`
- `privacy_ack_operator_assisted`
- `privacy_ack_private_default`
- `privacy_ack_source_separate`
- `privacy_ack_deletion_available`
- `submitted_at`

Minimum packet required before production work:

- user contact
- artifact type or provisional artifact type
- source material
- desired output
- audience
- privacy acknowledgments

## 4. Intake Completeness Check

Every intake receives one of four statuses.

### Accepted

Criteria:

- artifact type is in V1A scope or can be treated provisionally
- source material is sufficient to create a first spine
- desired output is understandable
- audience is named
- privacy acknowledgments are complete
- request does not require professional advice or public posting

Operator action:

- create project packet
- begin artifact spine procedure
- record accepted status in operator notes

### Needs Clarification

Criteria:

- source material is too thin
- artifact type is unclear
- desired output is vague
- user goals conflict
- audience is missing or too broad
- constraints are important but absent
- privacy acknowledgment is incomplete

Operator action:

- ask one to three targeted follow-up questions
- pause production work
- record clarification request and pending status

### Out of Scope

Criteria:

- request is mainly campaign generation before artifact exists
- request asks for direct social posting
- request asks for full manuscript completion in V1A
- request requires legal, medical, financial, or other professional advice
- request requires team collaboration or enterprise workflow
- request depends on external accounts, credentials, or private third-party data

Operator action:

- explain current V1A scope
- offer a narrower artifact-first path if possible
- record out-of-scope reason

### Declined

Criteria:

- user does not consent to operator-assisted review
- request includes material the operator should not handle
- request appears unsafe, abusive, deceptive, or outside acceptable use
- user asks for public exposure of someone else's private material
- operator cannot complete the request responsibly

Operator action:

- decline clearly and briefly
- do not process source material further
- offer deletion if applicable
- record declined status with minimal notes

## 5. Clarification Procedure

Use clarification to reduce uncertainty before creating the spine. Do not use
clarification to make the user over-plan.

### Too little source material

Ask for:

- more notes or fragments
- the most important claim
- one example
- what the artifact must not become

Stop condition:

- do not create a confident spine from insufficient source.

### Unclear artifact type

Ask:

- Is this meant to teach, argue, explore, organize, or persuade?
- Would this be more useful as a book, essay series, or course outline?
- Should V1A choose the best provisional form?

Stop condition:

- proceed only with a provisional type clearly marked.

### Conflicting goals

Examples:

- user wants a personal essay and a business framework
- user wants a course and a manifesto
- user wants a book chapter and a launch sequence

Ask:

- Which outcome matters first?
- Which audience matters first?
- What should the first returned draft help you do next?

Stop condition:

- choose one first artifact path before drafting.

### Sensitive/private material

Operator action:

- avoid copying sensitive material into unnecessary tools
- minimize notes about the material
- ask whether sensitive details should be generalized
- confirm whether the user wants specific details preserved

Stop condition:

- do not proceed if the material creates privacy or safety risk the operator
  cannot responsibly handle.

### Unrealistic output request

Examples:

- full book completion
- guaranteed publication outcome
- instant course buildout
- all campaign assets

Operator action:

- restate V1A deliverable: spine, one draft section, review summary, export
- ask whether the user wants to proceed with the smaller deliverable

### User wants campaign before artifact exists

Operator action:

- explain that V1A is artifact-first
- offer to create the source artifact spine first
- defer campaign work to a later workflow

### User asks for professional advice beyond scope

Operator action:

- do not provide legal, medical, financial, therapeutic, or other professional
  advice
- reframe toward artifact structure, clarity, audience, and drafting
- ask user to consult a qualified professional for advice-dependent claims

## 6. Artifact Spine Procedure

The spine is the first visible transformation from source material into
structure.

Steps:

1. Restate user intent in one to three sentences.
2. Identify artifact type.
3. Identify central thesis, outcome, or teaching promise.
4. Identify audience.
5. Extract recurring themes from source material.
6. Identify constraints and must-not-become notes.
7. Create the overall structure.
8. Create sections in a clear order.
9. Define the purpose of each section.
10. Preserve user voice notes.
11. Mark assumptions.
12. Identify missing material.
13. Prepare the spine preview.

Spine should include:

- project title or working title
- artifact type
- clarified direction
- central thesis/outcome
- audience
- section list
- section purposes
- seed points
- assumptions
- missing material
- source lineage summary

Quality checks:

- Does the user have a recognizable path forward?
- Does the spine match the artifact type?
- Does the structure come from the source material?
- Are assumptions visible?
- Are missing pieces named without pretending certainty?
- Is source material preserved separately?

## 7. First Draft Section Procedure

The first draft section should prove that the spine can become usable prose or
teaching material.

### Choosing the first section

Choose based on:

- user preference
- strongest opening value
- section most likely to prove the concept
- section with enough source material
- section that clarifies the whole artifact

If uncertain, choose the section that best creates the user's aha moment.

### Using source material

Use:

- source notes
- important fragments
- existing structure
- clarification answers
- approved or provisional spine
- section purpose
- constraints
- phrases to preserve

Do not treat source as decoration. The draft should be shaped by the user's
material.

### Preserving voice

Preserve:

- user's conceptual language
- tone preferences
- recurring phrases
- seriousness or warmth of the source
- must-not-sound-like notes

Avoid:

- generic AI phrasing
- sales psychology tone
- over-polished sameness
- flattening the user's sharper ideas

### Uncertainty markers

Use uncertainty markers when:

- the source is ambiguous
- the operator inferred structure
- examples are missing
- claims need later evidence
- audience assumptions are provisional

Examples:

- `Assumption:`
- `Needs source:`
- `Possible direction:`
- `To verify:`

### Avoiding overclaiming

Check:

- Does the draft claim more than source supports?
- Does it promise an outcome V1A cannot prove?
- Does it turn a possibility into certainty?
- Does it sound like professional advice?

If yes, revise or mark the claim for user confirmation.

### Separating draft from source

The draft must be clearly labeled as generated/assisted output. The original
source remains separate and unmodified.

## 8. Review Gate Procedure

The review gate checks whether the first draft section is ready to continue,
revise, or export.

Review checks:

- clarity
- coherence
- audience fit
- artifact alignment
- voice preservation
- overclaiming
- missing examples
- next-step readiness
- privacy/scope concerns

Review output should include:

- summary
- strengths
- issues
- suggested edits
- next recommended step
- confidence level

Suggested confidence levels:

- high: ready for user review/export
- medium: usable with specific revisions
- low: needs more source or direction before continuing

Review rules:

- be specific
- name the section or sentence-level issue when useful
- do not silently rewrite
- do not hide weak coherence
- do not promote the work without user approval
- distinguish style preferences from structural issues

## 9. Output Packet Procedure

Final packet contents:

- project summary
- clarified direction
- artifact spine
- first draft section
- review summary
- next steps
- export text/markdown
- operator notes if appropriate
- privacy reminder

Packet should distinguish:

- original source
- clarified direction
- generated spine
- generated draft
- review findings
- exportable output

Suggested order:

1. Short project summary.
2. Clarified direction.
3. Artifact spine.
4. First draft section.
5. Review gate summary.
6. Next recommended step.
7. Export text/markdown.
8. Privacy reminder.

Do not include internal operator notes unless they are useful and appropriate
for the user.

## 10. Quality Bar

Minimum acceptable output:

- user can recognize their idea
- structure is clear
- at least one section is usable
- review gate is specific
- next step is obvious
- no silent source overwrite
- no generic filler
- assumptions are visible
- privacy handling is respected

The output fails the quality bar if it could have been generated without the
user's source material.

## 11. Failure Handling

### Source is too thin

Action:

- request more source
- provide targeted prompts
- do not create a confident spine

### Request is too broad

Action:

- narrow to one artifact type and one first section
- restate V1A deliverable

### User intent is contradictory

Action:

- name the conflict
- ask user to choose the first priority
- preserve alternate direction as a later path

### Output quality is weak

Action:

- do not deliver as complete
- revise with source material
- ask for additional material if needed
- record why quality was weak

### Privacy concern appears

Action:

- pause processing if needed
- minimize copied material
- ask whether details should be generalized
- offer deletion if appropriate

### User is dissatisfied

Action:

- ask what felt wrong: structure, voice, accuracy, scope, or usefulness
- revise once within V1A bounds if appropriate
- record friction
- do not argue the user into accepting the output

### Operator cannot complete within scope

Action:

- explain the scope issue
- offer a narrower deliverable
- mark as out of scope or declined if necessary

## 12. Data Handling

Rules:

- store only necessary intake/source/output
- keep source and generated output separate
- do not paste private material into public tools
- disclose manual operator access
- delete on request if policy allows
- no public sharing
- no training/marketing use without explicit permission
- avoid collecting external account tokens
- avoid unnecessary sensitive profile data
- keep operator notes minimal and product-relevant

Operator notes should support workflow learning. They should not become a
shadow profile of the user.

## 13. Operator Notes Format

Use this format:

```text
intake_id:
operator_name_or_initials:
date:
intake_status:
artifact_type:
key_decisions:
assumptions_made:
issues_found:
user_followup_needed:
output_status:
next_step:
```

Optional product learning fields:

```text
time_spent:
aha_moment_reached:
willingness_to_pay_signal:
privacy_concerns:
feature_requests:
repeated_friction:
```

Keep notes factual, minimal, and non-sensitive.

## 14. Timing Targets

These are hypotheses, not promises.

- intake review: same day or next working day
- clarification request: within 24 hours of intake review
- spine creation: 30-90 minutes after accepted intake
- first draft section: 45-120 minutes after spine approval
- review summary: 20-45 minutes after draft completion
- final packet delivery: within the stated V1A turnaround window

Do not publish these as guaranteed turnaround times until tested.

## 15. Scope Escalation

Offer a later workflow only after the V1A output is delivered and the user has
seen the transformation.

Possible next stages:

- more sections
- full manuscript
- launch package
- editing pass
- private alpha participation
- saved style/voice profile
- publication prep

Do not hard-sell. Frame the next stage as optional:

```text
If this was useful, the next step could be...
```

## 16. V1A Evidence Captured

Record:

- where user got stuck
- whether artifact type was clear
- whether source was sufficient
- whether spine was accepted
- whether first draft felt useful
- whether user would pay
- privacy concerns
- feature requests
- time spent
- repeated friction
- whether the output led to continuation

Evidence should help decide whether to build a hosted private alpha. It should
not be collected as surveillance.

## 17. Completion Checklist

Before marking a V1A packet complete, confirm:

- intake validated
- intent clarified
- source preserved
- privacy acknowledgment complete
- spine created
- assumptions marked
- first section drafted
- review gate completed
- output packet prepared
- export text/markdown included
- user next step clear
- operator notes recorded
- privacy handling followed
- no public sharing occurred
- no silent source overwrite occurred
