# Governed Authoring Studio Release Plan

Status: future release planning draft

## 1. Purpose

This document prepares release discipline for Governed Authoring Studio.

It does not publish anything. It does not create a GitHub release, Zenodo
archive, DOI, citation file, app deployment, or public distribution package.

The goal is to define what can safely become a future public release snapshot
and what must remain out of release artifacts.

Working distinction:

```text
GitHub = living repo / development history
Zenodo = archived release snapshot / DOI / citation artifact
Domain + hosting = live public app
```

Zenodo is assumed to be an archive and citation layer for release snapshots,
not live app hosting.

## 2. Release Boundary

### Include in public releases

Public releases may include:

- product docs
- MVP scope
- user flows
- conceptual data model
- build options
- V1A spec
- release plan
- static mockup artifact or stable path reference
- product README
- future citation metadata
- future source code when intentionally released
- release notes
- public examples that contain no private user data

### Exclude from public releases

Public releases must exclude:

- user data
- private notes
- private drafts
- generated local outputs unless intentionally archived
- `books/out/`
- Dust artifacts
- internal HQ materials
- secrets/tokens
- environment files
- credentials
- work-in-progress unrelated repo files
- unpublished user research notes
- operator notes that could identify users or private projects

Release artifacts should be treated as public and durable. If something should
not be public for a long time, it should not be included in a Zenodo-targeted
release.

## 3. Release Types

### A. Planning/specification release

Purpose: archive the product definition and build path before implementation.

Included artifacts:

- product spine
- MVP scope
- user flows
- data model
- build options
- V1A spec
- release plan
- product README
- static mockup path reference

Readiness conditions:

- docs are internally consistent
- release boundary is explicit
- no private material is included
- generated outputs are excluded
- README explains that this is not yet a working app
- version tag is selected

### B. Mockup/design release

Purpose: archive interface direction and design evidence.

Included artifacts:

- static HTML mockup
- product README
- release notes
- product spine or design summary
- screenshots if intentionally generated for release

Readiness conditions:

- mockup opens locally
- mockup does not contain private material
- mockup labels are accurate
- release notes explain that it is a design artifact

### C. Software prototype release

Purpose: archive a runnable prototype with source code and minimal docs.

Included artifacts:

- intentional source code
- setup instructions
- product README
- release notes
- license, if selected
- citation metadata, if ready
- test or validation notes

Readiness conditions:

- prototype can be run by another developer
- no secrets are committed
- no user data is included
- generated outputs are excluded unless intentional
- privacy limitations are documented
- version tag is selected

### D. Public app release

Purpose: archive a public app milestone and its source/documentation snapshot.

Included artifacts:

- source code intended for release
- public docs
- release notes
- citation metadata
- license, if selected
- deployment notes that do not expose secrets
- changelog

Readiness conditions:

- public README is clear
- privacy policy and terms exist
- release tag is selected
- no private or generated local artifacts are accidentally included
- security and configuration boundaries are documented
- live hosting is handled separately from Zenodo

## 4. GitHub Role

GitHub is the living development layer.

It should be used for:

- version-control history
- issue tracking
- project tracking
- pull requests
- code review
- source-of-truth development history
- release tags
- GitHub release notes
- release assets, if intentionally attached

GitHub is where the project changes over time. A GitHub release tag can become
the source snapshot that is later archived by Zenodo.

## 5. Zenodo Role

Zenodo is the archive and citation layer.

It should be used for:

- archived release snapshots
- DOI/citation records
- public artifact preservation
- durable references to planning, design, or software releases

Zenodo should not be used for:

- live app hosting
- user data storage
- private drafts
- operator notes
- active project management
- secrets or configuration values
- unreleased internal HQ material

Zenodo releases should be treated as public, durable, citable snapshots.

## 6. Live App Hosting Role

The eventual live app will need hosting and domain infrastructure separate from
Zenodo.

Live hosting will need to handle:

- public landing pages
- app frontend
- authentication
- database
- storage
- AI provider integration
- exports
- admin/operator tooling
- logging
- privacy policy and terms
- billing, when needed

The live app can cite or link to a GitHub/Zenodo release, but Zenodo is not the
place where the active SaaS application runs.

## 7. First Proposed Release

First likely release:

```text
Governed Authoring Studio V1A Planning Release
```

Release type:

```text
Planning/specification release
```

Include:

- `products/governed_authoring_studio/product_spine.md`
- `products/governed_authoring_studio/mvp_scope.md`
- `products/governed_authoring_studio/user_flows.md`
- `products/governed_authoring_studio/data_model.md`
- `products/governed_authoring_studio/build_options.md`
- `products/governed_authoring_studio/v1a_spec.md`
- `products/governed_authoring_studio/release_plan.md`
- `products/governed_authoring_studio/README.md`
- static mockup path reference:
  `books/projects/communication_architecture/mockups/governed_authoring_studio_screens.html`

Exclude:

- generated book outputs
- `books/out/`
- private user materials
- Dust outputs/specs
- internal HQ docs
- secrets/tokens
- unrelated dirty worktree files
- app code not intended for this release

The first release should be described plainly as a planning/specification
release, not a working hosted app.

## 8. Release Readiness Checklist

Before a GitHub/Zenodo release:

- all release files are ASCII/format checked
- no secrets are present
- no private user data is present
- no generated outputs are included unless intentional
- README explains the project
- release notes exist
- version tag is selected
- citation metadata is prepared
- GitHub release is created
- Zenodo archive is confirmed
- release type is labeled accurately
- included/excluded paths are reviewed
- generated artifacts are either excluded or intentionally archived

Suggested local checks before staging a release:

```text
git status --short
git diff --check -- <release paths>
git diff --cached --name-status
```

## 9. Versioning Proposal

Suggested tags:

- `v0.1.0-planning`
- `v0.2.0-v1a-prototype`
- `v0.3.0-private-alpha`
- `v1.0.0-public-v1`

Meaning:

- `v0.1.0-planning`: product/specification release
- `v0.2.0-v1a-prototype`: concierge-assisted prototype or thin UI release
- `v0.3.0-private-alpha`: hosted private alpha milestone
- `v1.0.0-public-v1`: first public app release

Version tags should describe product maturity honestly.

## 10. Citation Metadata Later

Add citation metadata before the first Zenodo-linked release.

Candidate files:

- `CITATION.cff`
- `.zenodo.json`

Do not create those files until the release scope, authorship, title, license,
and repository metadata are ready.

Citation metadata should describe the release accurately. For the first release,
the record should say that it is a planning/specification release for Governed
Authoring Studio, not a finished app.

## 11. Risk Notes

Main risks:

- accidental release of private material
- generated artifacts included unintentionally
- confusing a planning release with a working app
- publishing too early without a clear README
- exposing internal HQ/system files
- overclaiming product maturity
- including `books/out/` by accident
- including Dust artifacts by accident
- releasing operator notes or user research that should remain private
- creating citation metadata before authorship/release scope is settled

The release process should preserve the product's trust posture. If the product
is about governed artifacts, its own releases should be governed artifacts.

## 12. Next Required Artifact

Next required artifact:

```text
products/governed_authoring_studio/README.md
```

The README should be created before any GitHub/Zenodo release. It should explain
what Governed Authoring Studio is, what release stage the project is in, what is
included, what is excluded, and how the V1A planning docs relate to future app
implementation.
