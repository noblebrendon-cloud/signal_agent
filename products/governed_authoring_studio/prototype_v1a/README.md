# Governed Authoring Studio Prototype V1A

This repository contains a static V1A workflow prototype for Governed Authoring Studio.

It demonstrates the intended user/operator flow for a concierge-assisted thin UI:

```text
Intake
-> Operator packet
-> Spine
-> Draft
-> Review
-> Output
-> Evidence
```

This is not a production app, hosted SaaS product, public beta, publishing platform, or full Governed Authoring System.

The prototype is static and local/browser-based. It has no backend, no database, no authentication, no analytics, no file upload system, and no live user account model.

The purpose is to show the workflow shape before building a hosted private alpha.

## 1. Purpose

The purpose of this repository is to prove that a static browser prototype exists for the V1A concierge-assisted workflow.

It gives the workflow a visible shape before a hosted app is built.

## 2. What This Prototype Shows

- Intake.
- Operator packet.
- Spine.
- Draft.
- Review.
- Output.
- Evidence.
- Source/output separation.
- Human operator disclosure.
- Non-sensitive evidence capture.

## 3. What This Prototype Does Not Do

- It does not run as a production app.
- It does not provide hosted SaaS access.
- It does not represent a public beta.
- It does not provide a full publishing platform.
- It does not run a campaign engine.
- It does not operate as an automated agent system.
- It does not expose or replace the internal HQ cockpit.
- It does not implement the full Governed Authoring System.
- It does not replace human judgment, authorship, or review.

## 4. Workflow Gates

The prototype follows this gate sequence:

```text
Intake
-> Operator packet
-> Spine
-> Draft
-> Review
-> Output
-> Evidence
```

Each gate is intended to make the V1A workflow visible for review. The generated text is deterministic prototype output and should not be treated as final product behavior.

## 5. Public-Safety Boundary

The prototype uses `P01 - Example participant` as an anonymized example participant.

Do not add real participant names, private source material, personal emails, secrets, API keys, tokens, passwords, generated trial outputs, or private local path references to this repository.

The repository is public-facing documentation and static prototype code only.

## 6. Relationship To V1A Planning Docs

This prototype follows the V1A planning/specification spine in the `governed-authoring-studio-v1a-planning` repository.

The planning repo documents the product boundary, MVP scope, workflow, intake form, operator runbook, output template, privacy note, trial plan, evidence log, and release plan.

This prototype shows the workflow shape those documents describe.

## 7. Local Use

Open `index.html` in a browser.

No install step, build step, backend, database, server, analytics, or external dependency is required.

The prototype stores local browser state in `localStorage` under:

```text
gas_v1a_prototype_state
```

Use the `Reset local state` button to clear the local prototype run.

## 8. Static Bridge Packet Surface

The output screen can export a backend-compatible governed authoring bridge packet as JSON and can import a backend output manifest or prototype result packet as JSON.

Static prototype packet export/import only.
No backend submission occurs from this UI.
No production writes occur from this UI.

The export/import panel preserves evidence refs, unresolved tensions, review status, and output status for the documented Phase 7 bridge contract. It flags publication-ready packets that lack evidence refs and generator/model self-approval before any backend run occurs elsewhere.

This is still a static browser prototype. The panel does not call Python, add a server, make network requests, write ledgers, create production authoring artifacts, or make the UI backend-governed.

## 9. Release Status

This repository is prepared as a static V1A prototype proof object.

No GitHub release should be created until the prototype text and UI have been reviewed.

Do not connect Zenodo, DOI, ORCID, OpenAIRE, or other publication records until release text is stable and explicitly approved.
