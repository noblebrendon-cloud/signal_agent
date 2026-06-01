# Governed Authoring Studio V1A Intake Form

Status: V1A intake form specification draft

## 1. Purpose

This document defines the first user-facing intake form for Governed Authoring
Studio V1A.

V1A is a concierge-assisted thin UI. The intake form should collect enough
source material, direction, and consent to let an operator create:

- an artifact spine
- one draft section
- a review gate summary
- a plain text or markdown export

The form should feel lightweight, but not vague. It should help the user move
from foggy thought into a clear first project packet.

## 2. Intake Goal

The intake should support the core V1A transformation:

```text
messy source material
-> clarified direction
-> artifact spine
-> one reviewed draft section
```

The form should not ask for every future detail. It should collect enough
signal to create the first useful transformation.

## 3. User Promise

User-facing promise:

```text
Share the rough material. We will turn it into a structured artifact spine,
draft one section, review it, and send back a portable draft you can keep using.
```

The promise should be careful:

- not "we will finish your book"
- not "AI will write everything"
- not "instant publishing"
- not "campaign automation"

## 4. Form Structure

Recommended sections:

1. Contact
2. Artifact Type
3. Current Material
4. Desired Output
5. Audience and Purpose
6. Voice, Tone, and Constraints
7. Examples and References
8. Privacy Acknowledgment
9. Delivery Expectations
10. Submit

## 5. Section 1: Contact

Purpose: identify the user and delivery path.

Fields:

### Name

- Type: short text
- Required: yes
- Help text: Your name for follow-up and delivery.

### Email

- Type: email
- Required: yes
- Help text: Where we should send the spine, draft, review summary, and export.

### Preferred follow-up method

- Type: select
- Required: no
- Options:
  - email
  - short call
  - async notes only

## 6. Section 2: Artifact Type

Purpose: identify the shape the user's idea is trying to become.

### What are you trying to create?

- Type: single select
- Required: yes
- Options:
  - book / long-form manuscript
  - essay series
  - course or teaching outline
  - not sure yet

### What stage is it in?

- Type: single select
- Required: yes
- Options:
  - loose notes
  - rough outline
  - partial draft
  - scattered materials
  - restarting a stalled project

### Working title

- Type: short text
- Required: no
- Help text: A rough title is fine. Leave blank if it does not have one yet.

## 7. Section 3: Current Material

Purpose: collect messy source material without forcing premature organization.

### Paste your rough material

- Type: long text
- Required: yes
- Minimum guidance: at least 300 words is recommended, but shorter fragments
  are allowed for early tests.
- Help text: Paste notes, fragments, claims, outlines, teaching ideas, chapter
  ideas, voice memo transcripts, or rough thinking.

### What parts feel most important?

- Type: long text
- Required: no
- Help text: Point to the lines, ideas, or fragments that should not get lost.

### Do you already have a rough structure?

- Type: long text
- Required: no
- Help text: Paste any outline, section list, course module list, or sequence
  you already have.

## 8. Section 4: Desired Output

Purpose: define what the user wants back from the V1A workflow.

### What do you want this to become?

- Type: long text
- Required: yes
- Help text: Describe the finished artifact in ordinary language.

### What should we create first?

- Type: single select
- Required: yes
- Options:
  - first chapter or section
  - first essay
  - first lesson
  - strongest opening section
  - recommend the best first section

### What would make this useful to you?

- Type: long text
- Required: yes
- Help text: Tell us what would make the returned spine and draft worth
  continuing.

## 9. Section 5: Audience and Purpose

Purpose: clarify who the artifact is for and why it matters.

### Who is this for?

- Type: long text
- Required: yes
- Help text: Describe the reader, learner, or audience.

### What should they understand, feel, or be able to do afterward?

- Type: long text
- Required: yes

### Why does this artifact matter?

- Type: long text
- Required: yes

### What problem does this artifact answer?

- Type: long text
- Required: no

## 10. Section 6: Voice, Tone, and Constraints

Purpose: preserve the user's voice and prevent generic output.

### Desired tone

- Type: multi-select
- Required: yes
- Options:
  - clear
  - reflective
  - analytical
  - practical
  - warm
  - direct
  - serious
  - conversational
  - teaching-oriented
  - other

### What should this not sound like?

- Type: long text
- Required: yes
- Help text: Name styles, tones, or genres to avoid.

### Constraints

- Type: long text
- Required: no
- Help text: Include length, format, audience sensitivity, claims to avoid, or
  boundaries that matter.

### Words, phrases, or ideas to preserve

- Type: long text
- Required: no

## 11. Section 7: Examples and References

Purpose: capture optional examples without turning V1A into research ingestion.

### Example material

- Type: long text
- Required: no
- Help text: Paste short excerpts, references, or examples that show the kind
  of artifact you want.

### Inspirations

- Type: long text
- Required: no
- Help text: Name books, essays, courses, or creators that give useful
  direction. Do not paste copyrighted full works.

### Things to avoid

- Type: long text
- Required: no
- Help text: Name examples, tropes, or patterns that would make the output feel
  wrong.

## 12. Section 8: Privacy Acknowledgment

Purpose: make operator-assisted review and data handling explicit.

Required acknowledgment text:

```text
I understand this V1A workflow is operator-assisted. A human operator may review
my submitted source material to create the artifact spine, first draft section,
review summary, and export. My material will not be made public without my
explicit permission.
```

Checkboxes:

- I understand this workflow is operator-assisted.
- I understand my source material is private by default.
- I understand generated output will remain separate from my original source.
- I can request deletion of my submitted material.

All checkboxes are required for V1A.

## 13. Section 9: Delivery Expectations

Purpose: set expectations before submission.

User-facing copy:

```text
You will receive:

1. a structured artifact spine
2. one draft section
3. a review gate summary
4. a plain text or markdown export
5. a suggested next step
```

Turnaround field:

- Type: display text
- Suggested copy: V1A turnaround will be confirmed after intake review.

Limitations copy:

```text
This is not a full publishing service, campaign engine, or complete manuscript
generation workflow. V1A tests the first transformation from source material to
structured draft.
```

## 14. Section 10: Submit

Primary button:

```text
Submit artifact intake
```

After submit, show confirmation:

```text
Your artifact intake was received. We will review the source material and
follow up with either a clarification question or your first spine preview.
```

Confirmation should include:

- submitted project title
- artifact type
- what happens next
- privacy reminder
- contact path for changes or deletion request

## 15. Validation Rules

Required fields:

- name
- email
- artifact type
- artifact stage
- rough material
- desired output
- first thing to create
- usefulness definition
- audience
- desired audience outcome
- why it matters
- desired tone
- what it should not sound like
- privacy acknowledgments

Soft warnings:

- source material under 300 words
- artifact type is "not sure yet"
- desired output is vague
- audience is too broad
- no constraints provided
- no "must not sound like" answer

The form should allow submission with soft warnings, but the operator may ask
follow-up questions before producing a spine.

## 16. Operator Intake Review

After submission, the operator should check:

- Is the artifact type in V1A scope?
- Is there enough source material to create a spine?
- Is the desired output clear enough?
- Is the audience clear enough?
- Are constraints or must-not-become notes present?
- Does the source contain private or sensitive material that requires extra
  care?
- Did the user acknowledge operator-assisted review?

Operator decision:

- accept intake
- request clarification
- request more source material
- mark out of scope

## 17. Data Fields

Suggested packet fields:

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

## 18. Non-Goals

The intake form should not:

- collect payment
- create user accounts unless needed for the test
- ask for external account tokens
- request contacts or social graph
- ask for sensitive demographics
- support uploads by default
- promise PDF publishing
- promise campaign generation
- promise full manuscript completion
- imply the app is fully automated

## 19. Success Criteria

The intake form is working if:

- users understand what they are submitting
- users can submit messy notes without over-formatting
- users understand operator-assisted review
- operators can produce a spine without excessive follow-up
- operators can identify insufficient submissions quickly
- privacy expectations are clear
- the returned output can be traced back to the intake packet

The form is too heavy if users abandon before submitting useful source
material. It is too light if operators cannot create a specific artifact spine.

## 20. Next Artifact

Next artifact:

```text
products/governed_authoring_studio/v1a_operator_runbook.md
```

The runbook should define exactly how the operator turns an intake packet into
a spine, draft section, review summary, and export.
