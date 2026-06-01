# Governed Authoring Studio Data Model

Status: conceptual v1 data model draft

## 1. Purpose

This document defines the conceptual v1 data model for Governed Authoring
Studio.

It is not a migration file, ORM schema, database vendor decision, or final
implementation contract. It is a build-readiness document for the first product
model: a governed path from messy source material into a structured, reviewable
artifact draft.

The model should protect the core MVP transformation:

```text
foggy thought -> structured artifact draft
```

The first schema should make these things easy to preserve:

- user and workspace isolation
- private-by-default content
- visible lifecycle state
- source lineage
- review gates that produce findings, not forced changes
- exportable user-owned drafts

## 2. Model Principles

- User content is private by default.
- Every artifact belongs to a user-owned workspace.
- Source material is never silently overwritten.
- Generated outputs must point back to source, clarification, spine, draft, and
  review inputs where possible.
- Review gates produce findings, not forced changes.
- Lifecycle state must be explicit and visible in the product UI.
- The product should collect only necessary data.
- Export should be supported from the beginning.
- Delete/archive policy must be defined before public launch.
- Generated drafts should remain distinguishable from captured source.
- Human approval should be required before promotion to a new stage.

## 3. Entity Overview

### User

- Purpose: account identity and ownership anchor.
- Key fields: `id`, `email`, `display_name`, `plan`, `created_at`.
- Relationships: owns workspaces through `Workspace.owner_user_id`; may belong
  to workspaces through `Membership`.
- Lifecycle notes: created at signup; persists across projects and workspaces.

### Workspace

- Purpose: isolation boundary for projects, content, settings, and future team
  behavior.
- Key fields: `id`, `name`, `owner_user_id`, `created_at`.
- Relationships: belongs to one owner user; contains projects, style profiles,
  memberships, and usage events.
- Lifecycle notes: a default workspace can be created during onboarding.

### Membership

- Purpose: explicit relationship between users and workspaces.
- Key fields: `id`, `workspace_id`, `user_id`, `role`.
- Relationships: joins `User` and `Workspace`.
- Lifecycle notes: simple in v1, but keeps the model ready for later
  collaboration without making collaboration an MVP feature.

### Project

- Purpose: main artifact container and lifecycle state holder.
- Key fields: `id`, `workspace_id`, `title`, `artifact_type`,
  `lifecycle_stage`, `status`, `created_at`, `updated_at`.
- Relationships: belongs to a workspace; contains source material,
  clarifications, spines, draft sections, reviews, outputs, and exports.
- Lifecycle notes: moves through the visible progress states from `Captured` to
  `Export Ready`.

### SourceMaterial

- Purpose: raw captured material that governs later structure and drafts.
- Key fields: `id`, `project_id`, `type`, `title`, `content`,
  `source_origin`, `created_at`.
- Relationships: belongs to a project; referenced by clarification, spine,
  draft, review, and output lineage.
- Lifecycle notes: append or version rather than overwrite; source remains
  user-owned and exportable.

### Clarification

- Purpose: explicit project intent gathered from user prompts.
- Key fields: `id`, `project_id`, `user_intent`, `audience`,
  `desired_output`, `constraints`, `created_at`.
- Relationships: belongs to a project; informs artifact spine generation and
  draft behavior.
- Lifecycle notes: can be revised, but previous intent should remain
  recoverable if it shaped generated work.

### ArtifactSpine

- Purpose: inspectable structure for the artifact.
- Key fields: `id`, `project_id`, `version`, `thesis`,
  `structure_summary`, `status`, `created_at`.
- Relationships: belongs to a project; has many spine sections; is informed by
  source material and clarification.
- Lifecycle notes: versioned because a wrong spine should be recoverable rather
  than silently replaced.

### SpineSection

- Purpose: structured unit inside an artifact spine.
- Key fields: `id`, `spine_id`, `order_index`, `title`, `purpose`,
  `seed_points`, `status`.
- Relationships: belongs to one artifact spine; can produce draft sections.
- Lifecycle notes: user can edit before drafting; section status supports
  progress without requiring every section to be drafted.

### DraftSection

- Purpose: drafted artifact content tied to a spine section and source lineage.
- Key fields: `id`, `project_id`, `spine_section_id`, `version`, `title`,
  `body`, `status`, `created_at`, `updated_at`.
- Relationships: belongs to a project and spine section; can be reviewed and
  exported.
- Lifecycle notes: should support versions or revision records before public
  launch; v1 can begin with simple version integers.

### ReviewGate

- Purpose: explicit review event before promotion or export.
- Key fields: `id`, `project_id`, `target_type`, `target_id`, `gate_type`,
  `status`, `summary`, `created_at`.
- Relationships: belongs to a project; targets a draft, spine, or whole
  project; has many review findings.
- Lifecycle notes: produces findings and readiness state; does not apply
  changes automatically.

### ReviewFinding

- Purpose: individual issue, strength, or recommendation from a review gate.
- Key fields: `id`, `review_gate_id`, `finding_type`, `severity`, `note`,
  `suggested_action`.
- Relationships: belongs to one review gate.
- Lifecycle notes: can later support structured fixes, but v1 should keep
  findings readable and user-controlled.

### GeneratedOutput

- Purpose: generated or derived output content created from project material.
- Key fields: `id`, `project_id`, `output_type`, `title`,
  `content_or_file_ref`, `source_refs`, `created_at`.
- Relationships: belongs to a project; points back to drafts, spines, source,
  and reviews through `source_refs`.
- Lifecycle notes: generated output is not source of truth unless the user
  explicitly promotes it.

### UsageEvent

- Purpose: coarse metering for product limits, debugging, and abuse prevention.
- Key fields: `id`, `user_id`, `workspace_id`, `project_id`, `event_type`,
  `quantity`, `created_at`.
- Relationships: may point to user, workspace, and project.
- Lifecycle notes: should avoid storing private content; keep metadata summary
  small and non-sensitive.

### StyleProfile

- Purpose: reusable voice, tone, or style constraints for drafting.
- Key fields: `id`, `workspace_id`, `name`, `description`, `rules`, `status`.
- Relationships: belongs to a workspace; may be referenced by projects or
  drafts.
- Lifecycle notes: optional in MVP; likely Creator-tier or private alpha
  feature if included.

### ExportRecord

- Purpose: record of an export action and exported artifact reference.
- Key fields: `id`, `project_id`, `export_type`, `file_ref_or_content_ref`,
  `created_at`.
- Relationships: belongs to a project; can reference generated outputs or draft
  sections.
- Lifecycle notes: proves the user can leave with a portable artifact.

## 4. Suggested Entity Details

### User

Conceptual fields:

- `id`
- `email`
- `display_name`
- `plan`
- `account_status`
- `created_at`
- `updated_at`

Notes: `plan` can support Free, Creator, and Studio without implementing
complex billing in the data model.

### Workspace

Conceptual fields:

- `id`
- `name`
- `owner_user_id`
- `default_privacy`
- `created_at`
- `updated_at`

Notes: `default_privacy` should default to private.

### Membership

Conceptual fields:

- `id`
- `workspace_id`
- `user_id`
- `role`
- `status`
- `created_at`

Notes: v1 can create only owner memberships, but the entity prevents later team
features from requiring a full ownership rewrite.

### Project

Conceptual fields:

- `id`
- `workspace_id`
- `title`
- `artifact_type`
- `lifecycle_stage`
- `status`
- `purpose`
- `created_at`
- `updated_at`

Notes: allowed `artifact_type` values for MVP are `book_manuscript`,
`essay_series`, and `course_outline`.

### SourceMaterial

Conceptual fields:

- `id`
- `project_id`
- `type`
- `title`
- `content`
- `source_origin`
- `tags`
- `created_at`
- `updated_at`

Notes: `source_origin` can be user_paste, typed_note, imported_text,
transcript, or other simple labels. Do not store external account tokens in v1.

### Clarification

Conceptual fields:

- `id`
- `project_id`
- `user_intent`
- `audience`
- `desired_output`
- `constraints`
- `tone_notes`
- `must_not_become`
- `created_at`

Notes: clarification captures the user's declared direction. It should not
replace source material.

### ArtifactSpine

Conceptual fields:

- `id`
- `project_id`
- `version`
- `thesis`
- `structure_summary`
- `status`
- `source_refs`
- `created_at`

Notes: `source_refs` should point to source material and clarification records
that informed the spine.

### SpineSection

Conceptual fields:

- `id`
- `spine_id`
- `order_index`
- `title`
- `purpose`
- `seed_points`
- `status`
- `created_at`
- `updated_at`

Notes: use `order_index` for stable ordering instead of deriving order from
title or creation time.

### DraftSection

Conceptual fields:

- `id`
- `project_id`
- `spine_section_id`
- `version`
- `title`
- `body`
- `status`
- `source_refs`
- `created_at`
- `updated_at`

Notes: `source_refs` should capture which source, spine, and clarification
inputs shaped the draft.

### ReviewGate

Conceptual fields:

- `id`
- `project_id`
- `target_type`
- `target_id`
- `gate_type`
- `status`
- `summary`
- `created_at`
- `completed_at`

Notes: `target_type` can begin with draft_section, artifact_spine, or project.

### ReviewFinding

Conceptual fields:

- `id`
- `review_gate_id`
- `finding_type`
- `severity`
- `note`
- `suggested_action`
- `status`
- `created_at`

Notes: v1 finding types can include clarity, coherence, audience_fit,
artifact_alignment, overclaiming, missing_examples, and next_step_readiness.

### GeneratedOutput

Conceptual fields:

- `id`
- `project_id`
- `output_type`
- `title`
- `content_or_file_ref`
- `source_refs`
- `status`
- `created_at`

Notes: v1 output types can be plain_text_export, markdown_export, and
draft_snapshot.

### UsageEvent

Conceptual fields:

- `id`
- `user_id`
- `workspace_id`
- `project_id`
- `event_type`
- `quantity`
- `metadata_summary`
- `created_at`

Notes: `metadata_summary` should avoid storing private content. It can record
coarse labels such as artifact type or action result.

### StyleProfile

Conceptual fields:

- `id`
- `workspace_id`
- `name`
- `description`
- `rules`
- `status`
- `created_at`
- `updated_at`

Notes: this should not be required for the first-session success moment.

### ExportRecord

Conceptual fields:

- `id`
- `project_id`
- `export_type`
- `file_ref_or_content_ref`
- `created_at`

Notes: export records preserve user-controlled portability and can reference a
generated output or draft section.

## 5. Lifecycle State Model

### Captured

- Entry condition: at least one `SourceMaterial` record exists.
- Allowed next transitions: Clarified.
- User-visible meaning: source has been captured and the next step is to
  clarify what the artifact is trying to become.

### Clarified

- Entry condition: at least one `Clarification` record exists with minimum
  intent fields.
- Allowed next transitions: Structured, Captured.
- User-visible meaning: direction is explicit enough to generate a spine.

### Structured

- Entry condition: an `ArtifactSpine` exists.
- Allowed next transitions: Drafting, Clarified.
- User-visible meaning: the artifact has an inspectable structure that the user
  can edit or approve.

### Drafting

- Entry condition: an `ArtifactSpine` is approved or marked ready for drafting.
- Allowed next transitions: Review Ready, Structured.
- User-visible meaning: sections can now be drafted from the approved spine.

### Review Ready

- Entry condition: at least one `DraftSection` exists with status
  `ready_for_review`.
- Allowed next transitions: Reviewed, Drafting.
- User-visible meaning: the draft is ready for a review gate.

### Reviewed

- Entry condition: a `ReviewGate` has completed for the target draft or
  project.
- Allowed next transitions: Export Ready, Drafting.
- User-visible meaning: findings are visible and the user can apply edits or
  export.

### Export Ready

- Entry condition: a reviewed draft section or generated output is available.
- Allowed next transitions: Drafting, Reviewed.
- User-visible meaning: the user can export a portable draft or keep building.

## 6. Status Fields

Keep statuses simple in v1.

### Project status

- `active`
- `archived`
- `deleted_pending`

### Spine status

- `generated`
- `user_edited`
- `approved`
- `superseded`

### SpineSection status

- `planned`
- `ready_to_draft`
- `drafted`
- `skipped`

### DraftSection status

- `draft`
- `ready_for_review`
- `reviewed`
- `revision_needed`
- `export_ready`

### ReviewGate status

- `queued`
- `running`
- `completed`
- `needs_revision`
- `accepted`

### GeneratedOutput status

- `generated`
- `exported`
- `superseded`

## 7. Source Lineage Model

The app should preserve traceability across the artifact path:

```text
SourceMaterial
-> Clarification
-> ArtifactSpine
-> SpineSection
-> DraftSection
-> ReviewGate
-> GeneratedOutput
-> ExportRecord
```

Source lineage matters because the product promise depends on trust. The user
should be able to see how raw material became structure, how structure became
draft, how review findings were produced, and what was exported.

`source_refs` should be used anywhere generated or reviewed material is created
from earlier records. In v1, `source_refs` can be a simple structured list of
entity references:

```text
entity_type + entity_id + optional note
```

Examples:

- a draft section references source material, clarification, artifact spine,
  and spine section
- a review gate references the draft section it reviewed
- a generated output references the draft section and review gate it came from
- an export record references the generated output or draft section exported

Source refs do not need to solve perfect provenance in v1. They need to prevent
the product from becoming a black box.

## 8. Privacy and Access Control

- Every query must be scoped through workspace or project ownership.
- A future hosted app should use account and workspace isolation from the
  beginning.
- If PostgreSQL is used later, row-level security should be considered for
  workspace-scoped tables.
- User content should be private by default.
- No public sharing should exist by default in v1.
- Exports should be user-controlled.
- Generated drafts should not be used as public examples without explicit user
  permission.
- Delete/archive policy is required before public beta.
- Membership roles should be simple until collaboration enters scope.

Minimum access rule:

```text
User can access a project only if the user has active membership in the
project's workspace.
```

## 9. Data Minimization

Do not collect these in v1:

- unnecessary demographics
- sensitive profile categories
- social graph
- contacts
- location
- external account tokens
- platform posting credentials
- private analytics beyond product usage
- imported inbox or drive access
- public profile metadata
- behavioral surveillance data

Keep the first product narrow: private source material, project structure,
drafts, review findings, exports, and coarse usage events.

## 10. Pricing and Usage Measurement

Usage events that can support simple pricing:

- `project_created`
- `source_material_added`
- `spine_generated`
- `draft_generated`
- `review_gate_run`
- `export_created`

Do not price by personal or private data entered.

Use limits based on:

- active project counts
- generation actions
- review actions
- export features
- saved style profiles later
- collaboration later
- campaign features later

Usage measurement should not require storing private content inside usage
records. It should answer simple questions: what action happened, for which
workspace/project, and how many units should count toward a limit.

## 11. MVP Storage Recommendation

Recommended v1 storage shape:

- Use a relational database for structured entities.
- Use object/file storage only if uploads or exported files are needed.
- Store plain text and markdown content in database fields initially unless
  content size demands otherwise.
- Persist generated outputs as text records first.
- Keep source material and generated drafts in separate entities.
- Add file storage later for large uploads, PDFs, media, or archived export
  bundles.

Do not make one vendor mandatory in this document. Supabase, Firebase, a
traditional Postgres app, or another stack can be evaluated later. The durable
choice at this stage is the entity model and access boundary, not the vendor.

## 12. Open Implementation Questions

- Should the first prototype be local-first or hosted from the start?
- Should body content be stored as markdown text or as a document block model?
- How much versioning depth is required in v1?
- Is `StyleProfile` an MVP feature or Creator-tier feature?
- How should delete/archive be implemented before public beta?
- Should exports be stored as records, files, or both?
- How should `source_refs` be represented: JSON, join table, or typed lineage
  table?
- Should review findings be structured enough for later automation?
- Should a user be able to change artifact type after a spine exists?
- Should project lifecycle changes be stored as events?

## 13. Non-MVP Data

Deferred data:

- team audit logs
- direct social publishing tokens
- analytics dashboards
- campaign calendar
- marketplace data
- billing invoices beyond plan/usage reference
- advanced document collaboration
- public sharing pages
- content performance metrics
- external platform account connections
- enterprise policy templates
- full agent orchestration traces

These may matter later, but adding them now would pull the MVP toward the whole
system before the first transformation is proven.

## 14. Build Readiness Summary

The v1 data model is sufficient if it supports:

- one user
- one workspace
- multiple projects
- source capture
- spine generation
- section drafting
- review gate findings
- plain text/markdown export
- visible lifecycle state
- source lineage

The build should begin only when the implementation path can preserve these
core rules:

- users can see the current state of their artifact
- generated work points back to source material
- reviews create findings, not silent rewrites
- exports remain user-controlled
- private content stays private by default
