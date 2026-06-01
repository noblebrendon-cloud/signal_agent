# Governed Authoring Studio User Flows

Status: MVP user flow draft

## 1. Purpose

This document defines the first-session and MVP user paths for Governed
Authoring Studio.

It translates the product spine and MVP scope into concrete behavior: what a
first-time user does, what they see, what decisions they make, where the system
helps, where the system stops, and what state transition proves value.

The MVP proves:

```text
foggy thought -> structured artifact draft
```

It does not prove campaign automation, full publishing, team workflows, or the
larger Signal Agent system.

## 2. Primary First-Session Flow

### Step 1: Landing / Login

- User goal: understand what the product does and enter a private workspace.
- Screen/state: landing page or login screen.
- User action: signs in or creates an account.
- System response: creates or loads `User` and default `Workspace`.
- State transition: unauthenticated -> authenticated workspace.
- Possible failure/friction: user thinks this is generic AI writing; landing
  copy must make the governed artifact promise clear.

### Step 2: Create Project

- User goal: start turning a serious idea into an artifact.
- Screen/state: project dashboard empty state.
- User action: clicks `Create project`.
- System response: opens project setup with artifact type options.
- State transition: no active project -> project setup.
- Possible failure/friction: user may not know what to call the project; title
  can be optional until the spine exists.

### Step 3: Choose Artifact Type

- User goal: select the shape the idea is trying to become.
- Screen/state: artifact type selection.
- User action: chooses book / long-form manuscript, essay series, or course /
  teaching outline.
- System response: creates `Project` with artifact_type and initial stage.
- State transition: project setup -> Captured-ready project.
- Possible failure/friction: user may not know the artifact type yet; the UI
  should offer `Help me choose` without blocking source capture.

### Step 4: Enter Messy Notes

- User goal: get fragments out of their head without organizing them first.
- Screen/state: capture room.
- User action: pastes notes, fragments, outlines, links, private language, or a
  rough description.
- System response: saves `SourceMaterial` and shows that the project is private
  by default.
- State transition: empty project -> Captured.
- Possible failure/friction: user enters too little material; system asks for
  more context or offers guided prompts instead of pretending certainty.

### Step 5: Clarify Intent

- User goal: tell the system what the artifact is for.
- Screen/state: clarify / structure room.
- User action: answers a short set of prompts about audience, purpose, desired
  artifact, tone, and what the artifact must not become.
- System response: saves intent fields on `Project` and prepares spine
  generation.
- State transition: Captured -> Clarified.
- Possible failure/friction: prompts may feel like homework; keep them few and
  visibly tied to better structure.

### Step 6: Generate Artifact Spine

- User goal: see scattered thought become an inspectable structure.
- Screen/state: structure room with source lineage visible.
- User action: clicks `Generate spine`.
- System response: creates `ArtifactSpine` with sections, assumptions, and
  source references.
- State transition: Clarified -> Structured.
- Possible failure/friction: generated spine may be wrong or too generic; user
  needs direct edit controls and a `Regenerate with guidance` path.

### Step 7: Approve / Edit Spine

- User goal: make the structure feel true enough to draft from.
- Screen/state: artifact spine editor.
- User action: edits section titles, deletes weak sections, adds missing
  material, and approves the spine.
- System response: saves a spine version and marks it approved for drafting.
- State transition: Structured -> Drafting.
- Possible failure/friction: user may over-edit before drafting; UI should
  encourage "good enough to draft" rather than perfection.

### Step 8: Draft One Section

- User goal: get one usable section from the approved spine.
- Screen/state: draft workspace.
- User action: chooses a section and clicks `Draft section`.
- System response: creates `DraftSection` from the approved spine, source
  material, and project intent.
- State transition: Drafting -> Review Ready.
- Possible failure/friction: draft feels generic; system should show source
  references and offer a voice/precision revision path.

### Step 9: Run Review Gate

- User goal: understand whether the draft is usable and what needs attention.
- Screen/state: review gate.
- User action: clicks `Run review`.
- System response: creates `ReviewGate` with findings, strengths, risks, and
  required changes.
- State transition: Review Ready -> Reviewed.
- Possible failure/friction: review may feel judgmental or vague; it must be
  specific, bounded, and tied to next edits.

### Step 10: Export / Save Draft

- User goal: leave with a portable artifact, not only an in-app state.
- Screen/state: export / next-step screen.
- User action: exports plain text or markdown.
- System response: creates `GeneratedOutput`, records source references, and
  offers next action.
- State transition: Reviewed -> Export Ready.
- Possible failure/friction: free-tier export limits can appear here, but plain
  text should remain available so the first transformation is not blocked.

### Step 11: Next-Step Prompt

- User goal: know what to do after the first useful draft.
- Screen/state: project dashboard with progress map.
- User action: chooses continue drafting, refine spine, add source material, or
  export.
- System response: shows allowed next actions based on project state.
- State transition: Export Ready -> continued project work.
- Possible failure/friction: too many next actions can feel like a dashboard;
  present one recommended next step and secondary options.

## 3. First-Session Success Moment

The key aha moment is:

```text
The user sees messy thought become a structured artifact spine and one usable
reviewed draft section.
```

The user should feel that the system preserved their idea while making it more
finishable. The proof is not that text appeared. The proof is that the user can
recognize their thought in a clearer structure and a usable first draft.

## 4. Flow A: Book / Long-Form Manuscript

Path:

```text
notes/fragments
-> thesis
-> parts/chapters
-> chapter purpose
-> draft first chapter/section
-> review gate
-> export markdown/plain text
```

Behavior:

- User captures fragments, thesis notes, possible title ideas, chapter ideas,
  and themes.
- System asks for core thesis, audience, tone, and what the book must not
  become.
- System generates parts and chapters as an artifact spine.
- User approves or edits the structure.
- User selects the first chapter or section to draft.
- System drafts from the spine and source material.
- Review gate checks whether the section anchors the larger artifact.
- User exports markdown/plain text.

Value proof: the user moves from scattered notes to a recognizable manuscript
structure and one reviewed chapter section.

## 5. Flow B: Essay Series

Path:

```text
topic fragments
-> central argument
-> essay sequence
-> individual essay outline
-> draft first essay
-> review gate
-> export
```

Behavior:

- User captures topic fragments, claims, examples, personal notes, or source
  ideas.
- System asks for central argument, intended reader, series length, and tone.
- System generates an essay sequence with each essay's role in the argument.
- User edits sequence and chooses the first essay.
- System creates an outline and drafts the first essay.
- Review gate checks clarity, argument shape, overclaiming, examples, and
  series continuity.
- User exports the essay.

Value proof: the user sees fragments become a coherent series arc and a usable
first essay.

## 6. Flow C: Course or Teaching Outline

Path:

```text
teaching idea
-> learner outcome
-> modules
-> lessons
-> first lesson draft
-> review gate
-> export
```

Behavior:

- User captures teaching ideas, audience needs, examples, outcomes, and rough
  lesson notes.
- System asks for learner outcome, learner starting point, desired change, and
  teaching style.
- System generates modules and lessons as an artifact spine.
- User edits modules and selects one lesson.
- System drafts the first lesson or teaching segment.
- Review gate checks clarity, learner fit, sequence, examples, and next-step
  readiness.
- User exports the lesson draft.

Value proof: the user sees a teaching idea become a course structure and one
teachable lesson.

## 7. Review Gate Flow

The review gate checks:

- clarity
- coherence
- audience fit
- artifact alignment
- overclaiming
- missing examples
- next-step readiness

It returns:

- pass / needs revision
- short summary
- strengths
- issues
- recommended edits
- next allowed action

How edits are applied:

- review findings are saved as `ReviewGate`
- user chooses which changes to apply
- applied edits update `DraftSection`
- source material remains unchanged
- review history remains visible

The review gate must not:

- silently overwrite source
- erase user voice
- turn the artifact into generic AI writing
- promote to next stage without user approval
- hide the criteria used for review

## 8. Progress State Model

### Captured

- Meaning: source material exists.
- Entry condition: user has saved at least one `SourceMaterial` record.
- Allowed next action: clarify intent.

### Clarified

- Meaning: project intent is explicit enough to structure.
- Entry condition: user has answered the minimum intent prompts.
- Allowed next action: generate artifact spine.

### Structured

- Meaning: artifact spine exists and can be inspected.
- Entry condition: `ArtifactSpine` exists.
- Allowed next action: edit/approve spine.

### Drafting

- Meaning: spine is approved and sections can be drafted.
- Entry condition: user approves spine for drafting.
- Allowed next action: draft section.

### Review Ready

- Meaning: at least one draft section exists.
- Entry condition: `DraftSection` exists with draft_status ready_for_review.
- Allowed next action: run review gate.

### Reviewed

- Meaning: review gate has run and findings are visible.
- Entry condition: `ReviewGate` exists for the section.
- Allowed next action: apply edits or export.

### Export Ready

- Meaning: draft can leave the system as a portable artifact.
- Entry condition: reviewed draft section exists.
- Allowed next action: export plain text/markdown or continue project.

## 9. Empty State UX

### No projects exist

Show one primary action: `Create your first artifact`.

Support copy: paste messy notes and leave with a structured draft.

### Project exists but no source material exists

Show the capture room with examples of acceptable messy input: notes,
fragments, outlines, voice memo transcript, screenshots transcribed elsewhere,
or rough claims.

### Source exists but no spine exists

Show captured source summary and one primary action: `Clarify direction`.

### Spine exists but no draft exists

Show the spine with editable sections and one primary action: `Draft first
section`.

### Draft exists but no review has run

Show the draft and one primary action: `Run review gate`.

## 10. Failure / Recovery Flows

### User enters too little information

- System response: ask for more context with three targeted prompts.
- Recovery action: user adds more source or selects guided capture.
- Stop condition: do not generate confident structure from insufficient source.

### Generated spine is wrong

- System response: show assumptions and source references.
- Recovery action: user edits spine, marks wrong assumptions, or regenerates
  with guidance.
- Stop condition: do not move to drafting until user approves spine.

### User does not know artifact type

- System response: offer `Help me choose`.
- Recovery action: ask whether the goal is to teach, argue, explore, document,
  or organize.
- Stop condition: allow provisional artifact type and later change.

### Draft feels generic

- System response: show source references and ask what feels missing.
- Recovery action: revise for voice, specificity, examples, or constraints.
- Stop condition: do not hide generic output behind polish.

### Review finds weak coherence

- System response: explain the coherence issue and identify the affected spine
  section.
- Recovery action: revise section, edit spine, or add source material.
- Stop condition: do not mark export ready until user accepts or resolves the
  finding.

### User wants to change direction

- System response: preserve existing source and create a new spine version.
- Recovery action: user clarifies new direction and regenerates or edits spine.
- Stop condition: do not overwrite previous spine without version history.

### User wants to export before review

- System response: allow plain text export with an `unreviewed draft` label.
- Recovery action: recommend review gate before treating it as ready.
- Stop condition: do not block user ownership of their content.

## 11. Data Touchpoints

| Flow step | Data entities touched |
| --- | --- |
| Landing / login | `User`, `Workspace`, `UsageEvent` |
| Create project | `Project`, `Workspace`, `UsageEvent` |
| Choose artifact type | `Project`, `UsageEvent` |
| Enter messy notes | `SourceMaterial`, `Project`, `UsageEvent` |
| Clarify intent | `Project`, `SourceMaterial`, `UsageEvent` |
| Generate artifact spine | `ArtifactSpine`, `SourceMaterial`, `Project`, `UsageEvent` |
| Approve/edit spine | `ArtifactSpine`, `Project`, `UsageEvent` |
| Draft one section | `DraftSection`, `ArtifactSpine`, `SourceMaterial`, `UsageEvent` |
| Run review gate | `ReviewGate`, `DraftSection`, `UsageEvent` |
| Export/save draft | `GeneratedOutput`, `DraftSection`, `ReviewGate`, `UsageEvent` |
| Continue project | `Project`, `UsageEvent` |

## 12. Pricing Gate Touchpoints

Free-tier limits should not appear before the user sees the first
transformation.

Good places for limits:

- project count limit at create-project time after the first project
- generation/review action limit after the first spine and first reviewed
  section
- export format limit at export screen
- saved style profile limit when user tries to save reusable style settings
- higher project limits when user starts a second or third artifact

Avoid:

- charging by personal data entered
- blocking initial source capture
- blocking the first spine
- blocking the first reviewed draft section

Recommendation: let the first session prove value before presenting paid
limits.

## 13. Privacy / Trust Touchpoints

The UI should reassure users at these moments:

- Login: private workspace by default.
- Capture room: source material remains private and exportable.
- Clarify room: intent prompts shape structure but do not overwrite source.
- Spine room: source lineage is visible.
- Draft workspace: generated drafts are distinguishable from captured source.
- Review gate: findings do not silently apply edits.
- Export screen: user can export their draft and source.
- Project settings later: delete/archive policy will be visible before public
  launch.

Trust rule: the user controls promotion to the next stage.

## 14. MVP Screens Implied

Minimum screens required:

- Landing / login
- Project dashboard
- Capture room
- Clarify / structure room
- Draft workspace
- Review gate
- Export / next-step screen

These screens can be simple. The important behavior is visible state and
recoverable progress.

## 15. Non-MVP Flows

Deferred flows:

- campaign engine
- PDF publishing
- team collaboration
- direct social posting
- analytics dashboard
- marketplace
- mobile app
- full launch/deployment automation
- custom AI agent marketplace
- enterprise approval workflows

These flows can be suggested in product direction, but they should not be part
of the first build.

## 16. Open Questions

- Should onboarding ask artifact type first or collect notes first?
- Should the first export be plain text or markdown?
- Should style/voice profile exist in MVP or Creator tier only?
- How much review should be free?
- What is the smallest useful project limit?
- Should users be allowed to change artifact type after spine generation?
- Should the first session require login before source capture?
- How visible should usage limits be during private alpha?
