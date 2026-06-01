# Governed Authoring Studio MVP Scope

Status: MVP scope draft

## 1. Product Boundary

Governed Authoring Studio is a public-facing creative artifact app for turning
serious unfinished ideas into structured, reviewable draft artifacts.

The MVP is not the whole Signal Agent system. It is not HQ, which remains the
internal cockpit. It is not a full publishing platform, campaign engine, agent
orchestration layer, marketplace, or team operating system.

The MVP should prove one transformation:

```text
foggy thought -> structured artifact draft
```

The first version should stop before full launch automation. It should help a
user capture source material, clarify direction, create an artifact spine,
draft sections, pass a review gate, and export a usable draft.

## 2. Target User

The first user is a person with serious unfinished ideas.

They have notes, fragments, private language, outlines, voice memos, research,
screenshots, drafts, or recurring thoughts. They know there is something real
inside the material, but they struggle to turn it into a coherent artifact.

This first user is likely a writer, founder, educator, researcher, operator,
coach, artist, or builder who wants to finish meaningful work without turning
their voice into generic AI output.

## 3. Core Job

Help the user move from foggy thought to structured draft with visible progress
and review gates.

The job is not merely to generate text. The job is to preserve continuity while
the idea becomes more structured:

- capture the user's source material
- clarify what the artifact is trying to become
- produce a spine the user can inspect
- draft sections from the spine and source
- review the draft against explicit standards
- show the current state and next action
- export a useful draft artifact

## 4. MVP Transformation

The MVP transformation is:

```text
Foggy Thought
-> Captured Source
-> Clarified Direction
-> Artifact Spine
-> Draft Sections
-> Review Gate
-> Exportable Draft
```

The product should make this transformation visible. The user should not feel
as if material disappeared into a black box and returned as generic prose. They
should see how source material becomes structure, how structure becomes draft,
and how review gates shape the draft without silently replacing the source.

## 5. Supported Artifact Types for MVP

The MVP should support a small set of artifact types:

- book / long-form manuscript
- essay series
- course or teaching outline

These are close enough to share one core workflow: source capture, intent,
spine, sections, review, and export.

Optional later artifact types, not MVP:

- podcast season
- sermon series
- launch campaign
- business framework
- research report

## 6. MVP Feature Set

The MVP includes only:

- account/login
- create project
- choose artifact type
- capture/paste notes
- clarify intent
- generate artifact spine
- create sections/chapters
- draft section
- run review gate
- visible progress map
- export markdown/plain text
- save project state

The feature set should be boring on purpose. The value is the governed path
from thought to draft, not feature volume.

## 7. Explicit Non-MVP Features

The MVP deliberately excludes:

- full campaign engine
- PDF rendering
- team collaboration
- direct social posting
- marketplace
- mobile app
- deep analytics
- advanced version control UI
- complex billing
- custom AI agent marketplace
- public community features
- multi-platform publishing
- full AI agent orchestration
- enterprise governance

These exclusions protect the product from expanding into the entire system
before the core transformation is proven.

## 8. Data Model v1

### User

Purpose: account identity and ownership boundary.

Key fields:

- id
- email
- display_name
- created_at
- account_status

### Workspace

Purpose: isolation boundary for a user's projects and content.

Key fields:

- id
- user_id
- name
- created_at
- default_privacy

### Project

Purpose: the active artifact container.

Key fields:

- id
- workspace_id
- artifact_type
- title
- purpose
- current_stage
- status
- created_at
- updated_at

### SourceMaterial

Purpose: raw captured material that governs later outputs.

Key fields:

- id
- project_id
- source_type
- title
- body
- tags
- created_at
- lineage_note

### ArtifactSpine

Purpose: structured plan for the artifact.

Key fields:

- id
- project_id
- version
- title
- sections
- assumptions
- status
- created_at

### DraftSection

Purpose: generated or user-edited section draft tied to the spine.

Key fields:

- id
- project_id
- spine_id
- section_key
- title
- body
- draft_status
- source_refs
- created_at
- updated_at

### ReviewGate

Purpose: explicit review state before promotion.

Key fields:

- id
- project_id
- gate_type
- criteria
- result
- notes
- required_changes
- reviewed_at

### GeneratedOutput

Purpose: exportable or derived artifact output.

Key fields:

- id
- project_id
- output_type
- title
- body
- source_refs
- generated_at
- export_status

### UsageEvent

Purpose: coarse metering for limits, debugging, and abuse prevention without
pricing against private data volume.

Key fields:

- id
- workspace_id
- project_id
- event_type
- quantity
- created_at
- metadata_summary

## 9. Data Governance v1

Data governance should be designed from day one, even in a small MVP.

- Users should only access their own workspace and project data.
- Collect only necessary data for the product to function.
- Avoid pricing around the amount of personal or private data entered.
- Store user content as private by default.
- Support export of source material and generated drafts.
- Define a future delete/archive policy before public launch.
- Keep source lineage visible to the user.
- Review outputs should never silently overwrite source.
- Generated drafts should remain distinguishable from captured source.
- Workspace-level isolation should be part of the core data model, not an
  enterprise add-on.

The product should treat private thought material as sensitive by default, even
when it is not legally classified as sensitive data.

## 10. Pricing Hypothesis

Pricing should use simple subscription tiers with active-project and feature
limits.

Do not price by personal data entered. Usage-based billing can come later if a
clear value metric emerges, but it would add complexity before the product has
proved its core transformation.

### Free

Hypothesis: free tier for trial and trust-building.

Possible limits:

- 1 active project
- limited source capture
- spine generation
- limited drafting/review
- plain text export

### Creator

Hypothesis: primary individual paid tier.

Possible limits:

- multiple active projects
- full drafting/review
- markdown export
- higher generation limits
- saved style/voice profile

### Studio

Hypothesis: advanced individual or small studio tier.

Possible limits:

- more active projects
- higher generation/review limits
- collaboration later
- campaign engine later
- approval gates later

All prices are hypotheses and should not be locked before alpha learning.

## 11. Launch Path

### Internal Proof

Purpose: prove the workflow with controlled projects.

Move on when:

- the Communication Architecture proof case maps cleanly into the product model
- source capture, spine, draft sections, review gate, and export are coherent
- the UI can show state without requiring explanation

### Private Alpha

Purpose: test with a small number of trusted users.

Move on when:

- users can create projects with minimal guidance
- messy notes can become useful artifact spines
- at least one draft section feels usable to the user
- privacy and export expectations are clear

### Paid Beta

Purpose: test willingness to pay and repeated use.

Move on when:

- users return to continue projects
- users understand plan limits
- support needs are manageable
- the core workflow does not require concierge explanation every time

### Public v1

Purpose: launch the narrow product with confidence.

Move on when:

- onboarding is understandable
- data governance and export are documented
- account isolation is tested
- billing is simple
- the product has a clear promise that does not sound like generic AI writing

## 12. Success Criteria

The MVP is validated when:

- users can create a project without explanation
- users can turn messy notes into a spine
- users can produce at least one usable draft section
- users understand the progress state
- users understand what to do next
- users trust that source material is not being silently overwritten
- at least some users say this helps them finish what they could not finish
  before

The strongest validation is not novelty. It is completion: users finish
artifact work that previously stayed fragmented.

## 13. Main Risks

- Scope creep into the full Signal Agent system.
- Users expect generic AI writing.
- Users do not understand governed artifact language.
- Privacy concerns around private thoughts.
- Pricing confusion.
- Too much dashboard, not enough creative flow.
- Campaign engine distracts from the core MVP.
- The product overexplains governance before the user feels creative progress.
- The first artifact types are too broad to share one workflow.

## 14. Next Build Decision

Before building, decide whether v1 is:

A. single-user local-first prototype
B. hosted private alpha web app
C. manual concierge workflow with thin UI

Recommendation: start with a concierge-assisted thin UI, then move into a
hosted private alpha.

Reason: the core risk is not whether the interface can be built. The core risk
is whether users experience the transformation as valuable, trustworthy, and
clear. A concierge-assisted thin UI lets the workflow be tested with real users
while keeping implementation narrow. It also gives enough structure to learn
from actual projects without prematurely building a full public SaaS surface.

The first build should prove:

```text
user source material
-> clarified artifact intent
-> artifact spine
-> one reviewed draft section
-> exportable markdown/plain text
```
