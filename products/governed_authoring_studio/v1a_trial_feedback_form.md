# Governed Authoring Studio V1A Trial Feedback Form

Status: V1A trial feedback form draft

## 1. Purpose

This document defines the post-delivery feedback form for Governed Authoring
Studio V1A trial participants.

The form should capture whether the concierge-assisted workflow helped the user
move from scattered material to a structured, usable artifact direction.

The goal is learning, not praise.

## 2. When To Send

Send after the participant has received:

- artifact spine
- first draft section
- review summary
- exportable output packet
- next-step suggestion

Do not send before the user has seen the first transformation.

## 3. Short Intro Copy

```text
Thank you for testing Governed Authoring Studio V1A.

This feedback form helps me understand whether the workflow actually helped you
move from scattered notes or a foggy idea into a clearer artifact direction.

Short, honest answers are best. The goal is to improve the workflow, not to get
polite praise.
```

## 4. Core Feedback Questions

### Did the spine make your idea clearer?

- Type: single select
- Options:
  - yes, clearly
  - somewhat
  - not really
  - it made it more confusing

Optional follow-up:

```text
What became clearer or less clear?
```

### Did the first draft section feel usable?

- Type: single select
- Options:
  - yes, I could build from it
  - somewhat, with edits
  - not yet
  - no

Optional follow-up:

```text
What would make it more usable?
```

### Did the output still feel like your idea?

- Type: single select
- Options:
  - yes
  - mostly
  - only partly
  - no

Optional follow-up:

```text
Where did it feel most connected or disconnected from your source material?
```

### What felt generic or wrong?

- Type: long text
- Required: no

Prompt:

```text
If anything sounded generic, too polished, off-tone, inaccurate, or unlike your
idea, describe it here.
```

### What was confusing?

- Type: long text
- Required: no

Prompt:

```text
Was anything unclear in the intake, output packet, review summary, privacy
note, or next-step guidance?
```

## 5. Continuation Questions

### Would you use this again?

- Type: single select
- Options:
  - yes, for this same project
  - yes, for another project
  - maybe
  - probably not
  - no

### What would you expect the next step to be?

- Type: long text
- Required: no

Prompt:

```text
If you continued, what would you expect the workflow to help with next?
```

### Would you pay for this?

- Type: single select
- Options:
  - yes
  - maybe
  - not yet
  - no

Optional follow-up:

```text
What would need to be true for this to feel worth paying for?
```

### Preferred pricing shape

- Type: single select
- Required: no
- Options:
  - one-time project fee
  - monthly subscription
  - pay per artifact
  - not sure
  - I would not pay

## 6. Privacy and Trust Questions

### Did the operator-assisted privacy note feel clear?

- Type: single select
- Options:
  - yes
  - mostly
  - somewhat unclear
  - no

### What privacy concerns did you have?

- Type: long text
- Required: no

Prompt:

```text
Were you concerned about submitting notes, unfinished thoughts, private
material, or anything else?
```

### Did you understand that a human operator may review submitted material?

- Type: single select
- Options:
  - yes
  - no
  - I missed that at first

### Did source/output separation matter to you?

- Type: single select
- Options:
  - yes, it made me trust the process more
  - somewhat
  - not really
  - I did not notice it

## 7. Automation Questions

### What should be automated next?

- Type: long text
- Required: no

Prompt:

```text
Which part felt like software should handle it next: intake, clarification,
spine, drafting, review, export, progress tracking, or something else?
```

### What should stay human for now?

- Type: long text
- Required: no

Prompt:

```text
Was there any part where human judgment felt important?
```

## 8. Product Fit Questions

### What kind of artifact would you use this for next?

- Type: multi-select
- Required: no
- Options:
  - book / long-form manuscript
  - essay series
  - course or teaching outline
  - business framework
  - research report
  - launch/campaign later
  - not sure
  - other

### What did this replace for you?

- Type: long text
- Required: no

Prompt:

```text
Did this replace staring at notes, asking a collaborator, hiring an editor,
using a generic AI chat, outlining manually, or something else?
```

## 9. Aha Moment Rating

Question:

```text
Did you have a moment where the idea felt more real or more finishable?
```

- Type: single select
- Options:
  - yes, clearly
  - somewhat
  - not really
  - no

Follow-up:

```text
If yes, when did that happen?
```

## 10. Final Open Question

```text
What is the one thing you would change before this became a real product?
```

## 11. Operator Scoring Notes

After reviewing feedback, operator records:

```text
record_id:
clear_aha:
spine_useful:
draft_useful:
voice_preserved:
privacy_understood:
willingness_to_pay:
continuation_requested:
top_friction:
automation_candidate:
private_alpha_signal:
```

Suggested values for `private_alpha_signal`:

- strong
- promising
- unclear
- weak

## 12. Evidence Log Mapping

Map feedback into `v1a_evidence_log.md`:

- spine clarity -> `spine_accepted`
- first draft usefulness -> `first_draft_usefulness`
- output still felt like user's idea -> `aha_moment_reached`
- generic/wrong feedback -> `friction_points`
- confusing areas -> `friction_points`
- use again -> `continuation_request`
- pay signal -> `willingness_to_pay_signal`
- privacy concerns -> `privacy_concerns`
- automation request -> `what_should_be_automated_next`

## 13. Form Boundary

The feedback form should not:

- ask for more private source material
- pressure the user to pay
- ask for a public testimonial by default
- imply the product is already launched
- ask for social sharing
- collect unnecessary demographic data

If a testimonial is desired later, request it separately and explicitly.

## 14. Next Artifact

Next likely artifact:

```text
products/governed_authoring_studio/v1a_trial_tracker.md
```

That document should define a lightweight table for tracking the first 5-10
participants from invite through feedback and evidence summary.
