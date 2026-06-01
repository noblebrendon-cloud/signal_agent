# Governed Authoring Studio V1A Output Template

Status: V1A output packet template draft

## 1. Purpose

This document defines the standard V1A output packet template for Governed
Authoring Studio.

The output packet is what a user receives after a concierge-assisted V1A run.
It should make the experience feel consistent, productized, and trustworthy
instead of like a one-off custom response.

## 2. Output Packet Boundary

### It is

- a structured return artifact
- a snapshot of the user's project state
- a clarified direction
- a proposed artifact spine
- one first draft section
- a review summary
- a next-step guide
- a portable plain text or markdown export

### It is not

- a finished full book, course, or series
- publication-ready without further review
- legal, medical, financial, or other professional advice
- a public release
- a promise of guaranteed commercial success
- campaign automation
- a replacement for the user's judgment

## 3. Output Header

Template fields:

- `project_title`
- `artifact_type`
- `prepared_for`
- `prepared_on`
- `operator`
- `status`
- `version`
- `privacy_level`

Recommended status values:

- `Spine Ready`
- `Draft Reviewed`
- `Needs Revision`
- `Export Delivered`

Recommended privacy level:

- `Private by default`

## 4. Project Summary

Include:

- `user_starting_point`
- `desired_output`
- `target_audience`
- `tone_or_style`
- `constraints`
- `key_source_material_used`
- `assumptions_made`

Purpose: remind the user what the system heard before showing what it produced.

The summary should be short and specific. It should not expose more private
material than necessary.

## 5. Clarified Direction

Template:

- central thesis / outcome
- what this artifact is trying to become
- who it is for
- what it should help them understand/do
- what should remain outside this artifact

The clarified direction should preserve the user's intent while making the
artifact easier to continue.

## 6. Artifact Spine

Template:

- title option
- subtitle option if applicable
- structure summary
- parts/modules/sections
- section titles
- section purposes
- seed points
- missing material needed

Supported MVP artifact types:

- book / long-form manuscript
- essay series
- course or teaching outline

### Book / long-form manuscript spine

Suggested fields:

- working title
- subtitle option
- core thesis
- parts
- chapters
- chapter purposes
- seed points
- missing material

### Essay series spine

Suggested fields:

- series title
- central argument
- essay sequence
- role of each essay
- first essay recommendation
- missing examples or claims to clarify

### Course or teaching outline spine

Suggested fields:

- course title
- learner outcome
- modules
- lessons
- lesson purposes
- first lesson recommendation
- missing teaching material

## 7. First Draft Section

Template:

- selected section title
- why this section was drafted first
- draft body
- source notes used
- assumptions or uncertainty markers
- suggested edits

Rules:

- label the draft as assisted/generated output
- keep it distinct from original source
- include uncertainty markers where needed
- avoid overclaiming
- preserve user voice where possible

## 8. Review Gate Summary

Template:

- review status
- clarity
- coherence
- audience fit
- artifact alignment
- voice preservation
- overclaiming risk
- missing examples
- next-step readiness
- privacy/scope notes
- confidence level

Suggested review status values:

- `Ready to continue`
- `Usable with revision`
- `Needs more source`
- `Out of scope for V1A`

Suggested confidence levels:

- `High`
- `Medium`
- `Low`

The review summary should be specific enough to guide the next action. It
should not be generic encouragement.

## 9. User Next Steps

Template:

- immediate next action
- optional revision path
- optional continuation path
- what to add next
- what not to worry about yet

The next step should be obvious. Do not give the user a large menu unless the
artifact genuinely needs a decision.

## 10. Export Section

Template:

- plain text export
- markdown export
- copy-safe artifact block
- file/download placeholder if later implemented

The export should be portable. In V1A, plain text and markdown are enough.

Do not imply PDF rendering, publishing, or platform posting unless those become
explicit later workflows.

## 11. Operator Notes

### May be included

- key decisions
- assumptions
- friction points
- follow-up needed
- scope escalation
- product learning notes, if appropriate and user-safe

### Should not be exposed

- internal prompts
- private operator speculation
- unrelated product notes
- sensitive internal system details
- notes that profile the user rather than the workflow
- details that create unnecessary privacy exposure

Default rule: include only operator notes that help the user continue the
artifact.

## 12. Privacy Reminder

Standard note:

```text
Your content is private by default. Your submitted source material and this
generated output are kept separate. Nothing is shared publicly without your
approval. You can request deletion/archive according to the V1A policy. Because
V1A is operator-assisted, a human operator may have reviewed your submitted
material to prepare this packet.
```

The privacy reminder should appear in every V1A output packet.

## 13. Template Markdown

Copy/fill template:

```markdown
# Governed Authoring Studio V1A Output Packet

## Output Header

- Project title: {{project_title}}
- Artifact type: {{artifact_type}}
- Prepared for: {{prepared_for}}
- Prepared on: {{prepared_on}}
- Operator: {{operator}}
- Status: {{status}}
- Version: {{version}}
- Privacy level: {{privacy_level}}

## Project Summary

### User starting point

{{user_starting_point}}

### Desired output

{{desired_output}}

### Target audience

{{target_audience}}

### Tone or style

{{tone_or_style}}

### Constraints

{{constraints}}

### Key source material used

{{key_source_material_used}}

### Assumptions made

{{assumptions_made}}

## Clarified Direction

### Central thesis / outcome

{{central_thesis_or_outcome}}

### What this artifact is trying to become

{{artifact_direction}}

### Who it is for

{{audience_summary}}

### What it should help them understand or do

{{audience_outcome}}

### What should remain outside this artifact

{{outside_scope}}

## Artifact Spine

### Title option

{{title_option}}

### Subtitle option

{{subtitle_option}}

### Structure summary

{{structure_summary}}

### Sections

{{artifact_sections}}

### Section purposes

{{section_purposes}}

### Seed points

{{seed_points}}

### Missing material needed

{{missing_material_needed}}

## First Draft Section

### Selected section title

{{selected_section_title}}

### Why this section was drafted first

{{why_this_section_first}}

### Draft body

{{draft_body}}

### Source notes used

{{source_notes_used}}

### Assumptions or uncertainty markers

{{assumptions_or_uncertainty_markers}}

### Suggested edits

{{suggested_edits}}

## Review Gate Summary

- Review status: {{review_status}}
- Clarity: {{clarity_review}}
- Coherence: {{coherence_review}}
- Audience fit: {{audience_fit_review}}
- Artifact alignment: {{artifact_alignment_review}}
- Voice preservation: {{voice_preservation_review}}
- Overclaiming risk: {{overclaiming_risk}}
- Missing examples: {{missing_examples}}
- Next-step readiness: {{next_step_readiness}}
- Privacy/scope notes: {{privacy_scope_notes}}
- Confidence level: {{confidence_level}}

## User Next Steps

### Immediate next action

{{immediate_next_action}}

### Optional revision path

{{optional_revision_path}}

### Optional continuation path

{{optional_continuation_path}}

### What to add next

{{what_to_add_next}}

### What not to worry about yet

{{what_not_to_worry_about_yet}}

## Export

### Plain text export

```text
{{plain_text_export}}
```

### Markdown export

```markdown
{{markdown_export}}
```

### Copy-safe artifact block

```text
{{copy_safe_artifact_block}}
```

### File/download placeholder

{{file_download_placeholder}}

## Operator Notes

{{operator_notes_visible_to_user}}

## Privacy Reminder

Your content is private by default. Your submitted source material and this
generated output are kept separate. Nothing is shared publicly without your
approval. You can request deletion/archive according to the V1A policy. Because
V1A is operator-assisted, a human operator may have reviewed your submitted
material to prepare this packet.
```

## 14. Quality Checklist

Before delivery, confirm:

- user idea is recognizable
- source material is preserved
- source and generated output are separate
- spine is clear
- first draft section is usable
- review gate is specific
- assumptions are marked
- uncertainty is named where needed
- next step is obvious
- no private material is exposed unnecessarily
- packet does not overpromise
- packet does not imply publication readiness
- packet does not imply professional advice
- export is portable
- privacy reminder is included

## 15. Future Automation Notes

These parts can later become automated:

- output header
- project summary
- spine rendering
- review summary
- export generation
- user next-step prompt
- source reference summaries
- confidence-level formatting

Keep manual review for:

- privacy concerns
- scope escalation
- ambiguous user intent
- generic output detection
- willingness-to-pay follow-up
- whether the user reached the aha moment

Future automation should preserve the packet shape. The template is part of the
product experience, not just formatting.
