# Governed Authoring Studio Build Options

Status: build path decision draft

## 1. Purpose

This document compares possible first build paths for Governed Authoring
Studio.

It chooses the first implementation route, not the final architecture. The goal
is to test the central product bet with the smallest useful implementation:

```text
foggy thought -> structured artifact draft
```

The first build should prove that a user can move from messy notes to a
structured spine and one reviewed draft section. It should not attempt to prove
full publishing, campaign automation, team collaboration, enterprise governance,
or the larger Signal Agent system.

## 2. Build Options Overview

The three realistic first build paths are:

A. Concierge-assisted thin UI
B. Hosted private alpha web app
C. Local-first prototype

The recommended path is:

```text
V1A concierge-assisted thin UI
-> observe 5-10 real users
-> V1B hosted private alpha web app
```

This keeps the product in contact with real user behavior before engineering
too much of the future surface.

## 3. Option A - Concierge-Assisted Thin UI

### What it is

A lightweight interface that collects project intent and source material, then
uses a partly manual operator workflow to create the spine, first draft section,
review gate summary, and export.

It is software-shaped, but not fully automated.

### What the user sees

- landing page
- project intake form
- artifact type selector
- source note capture
- clarification questions
- generated spine preview
- first section draft
- review gate summary
- export/download
- clear next-step prompt

### What remains manual behind the scenes

- operator reviews intake quality
- operator supervises spine generation
- operator checks whether the first draft follows the source
- operator runs or curates the review gate
- operator prepares the export if needed
- operator records friction, questions, and user reactions

### What data is stored

- user contact details needed for the test
- project title or working label
- artifact type
- source material
- clarification answers
- generated spine
- first draft section
- review gate summary
- export record or delivered file
- operator notes

Data should be stored minimally and explained clearly to the user.

### What can be tested

- whether users understand the promise
- whether users can submit messy notes
- whether the artifact type choices make sense
- whether the clarification prompts are enough
- whether a spine feels useful
- whether one reviewed draft section creates the aha moment
- whether users trust the no-silent-overwrite promise
- whether users would pay after seeing the transformation

### What cannot be tested well

- full self-serve retention
- dashboard engagement
- automated access control
- complex usage limits
- collaboration behavior
- scale
- infrastructure reliability
- repeat project management at volume

### Estimated complexity

Low to medium.

The interface can be simple. The complexity sits in operational discipline:
consistent intake, consistent review criteria, careful privacy language, and
clear handoff back to the user.

### Risks

- manual workflow can hide product friction
- users may experience it as a service rather than software
- operator labor may become expensive quickly
- privacy expectations must be explicit
- inconsistent operator judgment can weaken learning
- the thin UI may not test long-term retention

### Best use case

Use this when the riskiest question is whether the transformation matters to
real users.

Option A is best for testing message clarity, artifact scope, trust, review
value, and willingness to pay before investing in a full hosted app.

## 4. Option B - Hosted Private Alpha Web App

### What it is

A real hosted web application for a small private alpha group. Users sign in,
create projects, capture source material, generate spines, draft sections, run
review gates, and export drafts inside the app.

### Required components

- frontend
- authentication
- relational database
- project dashboard
- capture room
- clarify / structure room
- draft workspace
- review gate screen
- export layer
- usage limits
- admin/operator dashboard
- logging and usage events
- privacy policy and terms draft

### Auth

Users need private accounts. Authentication must support workspace-scoped
ownership from the beginning.

### Database

The data model should support users, workspaces, projects, source material,
clarifications, artifact spines, spine sections, draft sections, review gates,
review findings, generated outputs, usage events, style profiles, and export
records.

Keep the vendor decision open. A Postgres-style database with row-level access
policies is one possible future shape for enforcing per-workspace access.

### Project dashboard

The dashboard should show active projects, lifecycle state, next action, and
export status. It should not become a generic productivity dashboard.

### Capture room

The capture room stores messy notes and makes privacy visible. Source material
should remain separate from generated draft material.

### Structure room

The structure room collects clarification answers, generates an artifact spine,
and lets the user approve or edit the spine before drafting.

### Draft workspace

The draft workspace creates a draft section from an approved spine section and
source material. It should show source lineage and avoid generic writing
behavior.

### Review gate

The review gate checks clarity, coherence, audience fit, artifact alignment,
overclaiming, missing examples, and next-step readiness. It returns findings,
not forced edits.

### Export

The export layer should support plain text and markdown in the alpha. PDF and
publication packaging can wait.

### Usage limits

Usage limits can be attached to active projects, spine generation, draft
generation, review gates, and export features. Do not price by personal data
entered.

### Privacy/access model

Every query must be scoped by account, workspace, and project ownership. User
content should be private by default. Public sharing should not exist by
default.

### Estimated complexity

Medium to high.

The hosted alpha validates the real product surface, but it requires more
security, persistence, support, billing thought, and operational discipline than
Option A.

### Risks

- building too much before messaging is proven
- account and privacy work slows learning
- users may expect full SaaS polish
- infrastructure choices may harden too early
- team and campaign requests may expand scope
- billing and usage limits can distract from the aha moment

### Best use case

Use this after Option A proves that users understand the promise, reach the aha
moment, trust the workflow, and show willingness to pay.

## 5. Option C - Local-First Prototype

### What it is

A prototype that runs locally for a single user or controlled test user. Source
material, spines, drafts, reviews, and exports remain on the user's machine or
in local files.

### What runs locally

- simple project workspace
- local source capture
- local spine and draft records
- local review output
- local markdown/plain text exports

### What data remains local

- source material
- clarification answers
- generated spine
- draft sections
- review findings
- exported text/markdown

### How exports work

Exports can be written as local plain text or markdown files. The user controls
the files directly.

### What can be tested

- workflow logic
- data model shape
- source lineage
- export behavior
- privacy-sensitive use cases
- personal internal proof cases

### What cannot be tested well

- onboarding
- payment behavior
- account isolation
- hosted privacy expectations
- admin workflow
- support load
- user willingness to use a web app
- collaborative or multi-device behavior

### Estimated complexity

Low to medium, depending on interface polish.

It can be fast if it stays file-based and single-user. It can become a trap if
it starts building a parallel desktop product.

### Risks

- weak market learning
- users may not install or run it
- local storage decisions may not map to hosted alpha
- payment and onboarding remain untested
- it can become an internal tool rather than a public product

### Best use case

Use this for internal experimentation or privacy-sensitive proof work. Do not
use it as the primary public MVP path unless hosted testing is blocked.

## 6. Comparison Table

| Dimension | Option A: Concierge-assisted thin UI | Option B: Hosted private alpha | Option C: Local-first prototype |
| --- | --- | --- | --- |
| Speed to test | Fastest | Slower | Fast for internal use |
| User learning quality | High for value and messaging | Highest for product behavior | Low to medium |
| Engineering complexity | Low to medium | Medium to high | Low to medium |
| Privacy posture | Good if disclosed clearly | Strong if designed well | Strong for local data |
| Payment readiness | Manual tests only | Real pricing gates possible | Weak |
| Scalability | Low | Medium | Low |
| Data model validation | Medium | High | Medium |
| Support burden | High operator burden | Medium product/support burden | Low external support |
| Launch readiness | Low | Medium | Low |
| Risk of overbuilding | Low | High | Medium |

## 7. Recommendation

Start with Option A: Concierge-assisted thin UI.

Then graduate to Option B: Hosted private alpha after observing 5-10 real
users.

Why:

- fastest real learning
- avoids overbuilding
- protects scope
- tests messaging before architecture hardens
- allows manual quality control
- still exercises the product model
- can map directly into hosted app screens later
- lets pricing questions be asked after the user sees value
- keeps campaign, publishing, and collaboration out of the MVP

Option A is not the final product. It is the smallest disciplined test of the
core transformation.

## 8. V1A Scope

The first concierge-assisted thin UI should include:

- landing page
- project intake form
- artifact type selector
- source note capture
- clarify intent questions
- generated spine preview
- first section draft
- review gate summary
- export/download
- operator/admin notes

The core flow:

```text
landing
-> intake
-> source capture
-> clarification
-> spine preview
-> first draft section
-> review summary
-> export/download
-> follow-up question
```

V1A should feel like a product experience even when some of the work is manual
behind the scenes.

## 9. V1A Non-Scope

Exclude:

- user accounts if not needed for the first test
- persistent dashboard if not needed
- payments if manually invoiced or tested
- PDF rendering
- campaign engine
- team collaboration
- direct social posting
- analytics dashboard
- complex usage metering
- full hosted workspace model
- marketplace
- mobile app
- enterprise governance

V1A should not pretend to be a full SaaS product. It should prove whether the
first transformation creates enough value to justify the hosted build.

## 10. Private Alpha Entry Criteria

Move from V1A to hosted private alpha when:

- 5-10 users complete intake
- at least 3 users reach the aha moment
- at least 2 users say they would pay
- repeated friction points are known
- the artifact data model still holds
- privacy language is understandable
- first pricing gates are validated
- manual workflow is too slow to continue manually
- users understand the difference between source, spine, draft, review, and
  export
- users can describe what the product helped them finish

The hosted alpha should be earned by observed behavior, not excitement about
the mockup.

## 11. Hosted Private Alpha Minimum Stack

Keep the stack vendor-neutral until the V1A learning is clear.

Minimum hosted components:

- frontend
- auth
- relational database
- file/object storage if needed
- AI provider abstraction
- export layer
- admin/operator dashboard
- logging/usage events
- privacy policy / terms draft
- basic error handling and support path

Implementation requirements:

- account/workspace isolation
- private-by-default projects
- source and outputs stored separately
- review gates stored as findings
- no silent overwrite
- export available
- deletion/archive path defined before public beta

Do not choose a mandatory vendor yet.

## 12. Pricing Test During V1A

Pricing test recommendation:

- do not charge before the first transformation
- ask willingness-to-pay after the user sees a spine and reviewed draft section
- optionally test a founding-user price
- manually test Free vs Creator boundaries
- do not price by personal/private data entered
- avoid complex usage-based billing during V1A

Good questions after the aha moment:

- Would you pay to do this again with another artifact?
- Would you pay to continue drafting the full project?
- Would you pay more for saved style/voice support?
- Would you pay for publication prep or campaign generation later?

The first pricing test should measure perceived value, not billing machinery.

## 13. Data Governance During V1A

V1A must be unusually clear about trust because users are submitting private
thought material.

Rules:

- collect only needed notes
- tell users what is stored
- disclose manual operator access
- no public sharing
- provide export
- make deletion available on request
- keep source and outputs separate
- avoid silent overwrite
- do not use user projects as public examples without permission
- avoid collecting external account tokens or platform credentials

Operator notes should be professional, minimal, and tied to workflow learning.
They should not become a shadow profile of the user.

## 14. Main Risks

- manual workflow hides product friction
- users may think it is a service, not software
- too much admin labor
- unclear privacy expectations
- thin UI may not prove retention
- early users may want campaign engine immediately
- scope creep into HQ/internal system
- artifact language may need simpler onboarding copy
- operator quality may make the product seem better than automation can support
- hosted alpha may be started before the repeated workflow is clear

The most important risk is mistaking a successful assisted service for a
validated self-serve product. V1A should produce learning, not false certainty.

## 15. Decision Record

Recommended next build path:

```text
V1A concierge-assisted thin UI
```

Graduation path:

```text
V1A concierge-assisted thin UI
-> 5-10 observed users
-> hosted private alpha web app
```

Reason:

The product's riskiest question is not whether a dashboard can be built. The
riskiest question is whether people with serious unfinished ideas experience
the governed transformation as valuable, trustworthy, and worth paying for.

Next artifact:

```text
products/governed_authoring_studio/v1a_spec.md
```
