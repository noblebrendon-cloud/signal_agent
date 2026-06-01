# Governed Authoring Studio

## Status

This is a planning/specification artifact for a V1A concierge-assisted thin UI.

It is not yet a hosted public app.

## One-Sentence Description

A governed creative workspace for turning unclear thought into structured,
reviewed, launchable artifacts.

## Product Boundary

Governed Authoring Studio is the public-facing creative artifact app.

It is distinct from HQ, which is the internal cockpit for operating the larger
system. It is also distinct from the Communication Architecture book, which is
the first proof case and demo project for the app model.

This product is not the whole Signal Agent system.

## Core Problem

Many people have serious unfinished ideas, notes, fragments, and vision, but no
stable path from fog to finished artifact.

They can capture thoughts, but lose continuity. They can generate text, but
lose voice, structure, review, and legitimacy. They can publish content, but
the output often becomes disposable rather than durable.

Governed Authoring Studio is designed around the missing path between scattered
source material and a finished artifact.

## Core Transformation

```text
Foggy Thought
-> Captured Source
-> Clarified Direction
-> Artifact Spine
-> Draft Sections
-> Review Gate
-> Exportable Draft
-> Later Launch / Deployment
-> Evidence
```

The product treats creation as a visible state transition, not a single prompt.

## MVP Scope

The MVP proves:

```text
foggy thought -> structured artifact draft
```

Supported MVP artifact types:

- book / long-form manuscript
- essay series
- course or teaching outline

The MVP does not attempt to prove full publishing, campaign automation,
collaboration, analytics, marketplace behavior, or a mobile app.

## V1A Build Path

V1A is a concierge-assisted thin UI.

The user sees:

- intake
- clarification
- spine preview
- first draft section
- review summary
- export

Behind the scenes, an operator manually supervises the workflow. This is
intentional. The goal is to learn whether real users experience the core
transformation as valuable before building a full hosted SaaS product.

The V1A path is:

```text
concierge-assisted thin UI
-> observe 5-10 real users
-> hosted private alpha only after evidence
```

## What Is Included In This Folder

- `product_spine.md`: product boundary, promise, transformation, and governing
  principles.
- `mvp_scope.md`: MVP scope, target user, feature boundaries, pricing
  hypothesis, and launch path.
- `user_flows.md`: first-session behavior, supported artifact flows, review
  gate flow, progress states, recovery paths, and trust touchpoints.
- `data_model.md`: conceptual v1 data model for source capture, spines, drafts,
  review gates, lineage, usage, and exports.
- `build_options.md`: comparison of concierge-assisted thin UI, hosted private
  alpha, and local-first prototype.
- `v1a_spec.md`: buildable specification for the concierge-assisted V1A thin UI.
- `release_plan.md`: future GitHub and Zenodo release boundary.
- `README.md`: project orientation for future GitHub and Zenodo readers.

## Mockup

Static mockup:

```text
books/projects/communication_architecture/mockups/governed_authoring_studio_screens.html
```

The mockup is a design artifact, not the production app.

It shows the broader governed workspace direction: project overview, drafting
workspace, review/stage gate, publication prep, campaign concepts, and artifact
boundary. The V1A build should stay narrower than the full mockup.

## Data and Privacy Principles

- User content is private by default.
- Collect only necessary data.
- Do not silently overwrite source material.
- Keep source lineage visible.
- Keep captured source separate from generated drafts and outputs.
- Review gates produce findings, not forced changes.
- Exports are user-controlled.
- Deletion/archive policy is required before public beta.
- Do not price by personal/private data entered.
- Do not use user projects as public examples without explicit permission.

## Pricing Hypothesis

The pricing hypothesis uses simple tiers:

- Free
- Creator
- Studio

Limits should be based on:

- active projects
- generation/review actions
- export features
- saved style/voice profile later
- collaboration later
- campaign features later

Do not price by personal or private data entered.

Pricing should not appear before the user sees the first transformation: a
structured spine and one reviewed draft section.

## Release Plan

The first likely release is:

```text
Governed Authoring Studio V1A Planning Release
```

This is a planning/specification release, not a working hosted app.

Release roles:

```text
GitHub = living repo / development history
Zenodo = archived release snapshot / DOI / citation artifact
Domain + hosting = live public app
```

Zenodo is for archived, citable release snapshots. It is not live app hosting
and should not contain user data, private notes, internal HQ material, secrets,
or local generated outputs unless intentionally archived.

## Non-Goals

- Not generic AI writing software.
- Not a full SaaS yet.
- Not the internal HQ.
- Not a campaign engine in the MVP.
- Not direct social posting.
- Not team collaboration yet.
- Not a marketplace.
- Not a mobile app.
- Not a replacement for human judgment, taste, or authorship.

## Next Steps

- Create `v1a_intake_form.md`.
- Create `v1a_operator_runbook.md`.
- Create `v1a_output_template.md`.
- Create `v1a_privacy_note.md`.
- Test with 5-10 real users.
- Graduate to hosted private alpha only after V1A evidence.

## Release Caution

Do not include these in public release snapshots:

- user data
- private notes
- secrets/tokens
- generated local outputs
- `books/out/`
- Dust artifacts
- internal HQ materials
- unrelated work-in-progress repo files

Treat any future GitHub or Zenodo release as public, durable, and citable.
