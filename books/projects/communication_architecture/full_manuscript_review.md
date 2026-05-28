# Full Manuscript Coherence Review

Review date: 2026-05-27

## Argument Arc

The full manuscript now forms a coherent four-part argument:

1. Part I establishes that communication is architectural: language shapes
   perception, attention, identity, emotion, memory, legitimacy, and action.
2. Part II explains the influence systems moving through that architecture:
   coercion, persuasion, resonance, governance, resistance, narrative gravity,
   and the ethical boundary between clarification and capture.
3. Part III diagnoses modern discourse collapse as a systems failure: emotional
   velocity, procedural opacity, identity pressure, and AI-accelerated rhetorical
   scale reward capture more reliably than clarification.
4. Part IV answers the collapse diagnosis constructively: governance matters
   because conditions shape discourse, coherence is continuity under pressure,
   governed communication preserves agency without enforcing sameness, and
   legitimate systems remain visible, constrained, corrigible, coherent, and
   answerable when pressure arrives.

The manuscript does not read as a sequence of isolated essays. Each part adds a
distinct layer and hands off to the next: architecture, influence, collapse, and
governance.

## Strengths

- The governing vocabulary is stable across the draft: agency, truth,
  legitimacy, procedure, coherence, governance, clarification, capture, and
  architecture.
- The book consistently treats influence as pressure within conditions, not as
  deterministic control.
- Governance is framed as visible, constrained, accountable structure rather
  than domination.
- Coherence is framed as continuity under pressure rather than sameness or rigid
  consistency.
- AI is treated as acceleration infrastructure under governance failure, not as
  magic, independent moral agent, or doom object.
- The final chapter closes the book by returning to the whole arc without
  becoming a product pitch or utopian conclusion.

## Issues Found

- The non-mechanical-control disclaimers are still slightly repetitive across
  the full manuscript, but most are doing useful boundary work in chapters where
  the subject could otherwise sound deterministic.
- The first draft currently prioritizes conceptual continuity over concrete
  examples. A second draft should add more grounded examples where abstraction
  becomes dense.
- Chapter-level transitions are strong, but a later layout pass should consider
  whether Part openings or Part pages would help readers feel the section shifts.
- The source system still renders chapter authoring metadata as part of the
  manuscript body. That is acceptable for this pipeline stage, but a later
  publication pass should decide whether those fields remain visible.

## Edits Made

No chapter prose edits were needed during this review pass. The review artifact
was added so the next checkpoint has an explicit editorial boundary.

## Vocabulary Rules

- Use `architecture` for arranged conditions, incentives, procedures, and
  constraints that shape communication before individual messages are judged.
- Use `influence` for pressure that changes attention, judgment, recognition,
  behavior, or conditions without assuming mechanical control.
- Use `agency` for a person's ability to perceive, judge, refuse, revise,
  appeal, and act responsibly inside pressure.
- Use `legitimacy` for trust produced by visible, constrained, corrigible,
  coherent, answerable process.
- Use `procedure` for the visible process by which decisions, corrections,
  rankings, moderation, claims, or system actions become accountable.
- Use `coherence` for continuity under pressure, not sameness or immobility.
- Use `governance` for structured conditions around communicative power, not
  domination or control for its own sake.
- Use `clarification` for influence that preserves judgment, agency, procedure,
  and truth.
- Use `capture` for influence that hides constraint, bypasses judgment, or
  recruits identity, emotion, attention, or resonance against agency.

## Second-Draft Priorities

1. Add grounded examples to the densest conceptual sections without turning the
   book into a tactics manual.
2. Trim repeated non-determinism disclaimers only where nearby chapters already
   carry the boundary clearly.
3. Decide whether authoring metadata should remain visible in rendered
   manuscript output.
4. Add Part-page rendering or equivalent section markers only after the reviewed
   draft checkpoint is secure.
5. Review title casing and acronym handling in the generated output.
6. Consider citations, notes, or a source strategy only after the conceptual
   draft has been stabilized.

## Readiness for Checkpoint

The first full manuscript draft is ready for a reviewed-full-draft checkpoint
after the compile, render, test, typeset, and preservation loop passes.

The recommended checkpoint should include source-of-truth files:

- `books/projects/communication_architecture/**`
- `books/specs/communication_architecture.yaml`
- `tests/test_bookgen_project_compile.py`

Generated outputs under `books/out/communication_architecture/` should remain
untracked unless a deliberate release/archive snapshot is being created.
