# Governed Authoring Studio V1A Prototype

Status: dependency-free local browser prototype

This folder contains the first runnable V1A prototype for Governed Authoring
Studio. It is intentionally small: plain HTML, CSS, and JavaScript.

The prototype exercises the concierge-assisted V1A workflow:

```text
intake -> operator packet -> spine -> draft -> review -> output -> evidence
```

## What It Is

- a local browser prototype
- a workflow simulator for the first V1A trial
- a product surface for testing the core transformation
- a place to inspect screen shape before building a hosted app

## What It Is Not

- a hosted SaaS app
- a React scaffold
- an AI backend
- a database implementation
- a production privacy system
- a publishing or campaign engine

## How To Open

Open this file directly in a browser:

```text
products/governed_authoring_studio/prototype_v1a/index.html
```

No install step is required.

The app stores local prototype state in `localStorage` under:

```text
gas_v1a_prototype_state
```

Use the `Reset local state` button to clear the local prototype run.

## Seeded Trial

The prototype is seeded for:

```text
participant_id: 001
participant: Justin
```

The app can copy a send-ready invite and intake note, but it does not send
external messages.

## Workflow Screens

1. Intake
2. Operator packet
3. Spine
4. Draft
5. Review
6. Output
7. Evidence

The generated spine, draft, review, and output packet are deterministic local
prototype outputs. They are not AI-generated and should not be treated as final
product behavior.

## Governance Rules Preserved

- Source and generated output stay separate.
- No silent overwrite of user material.
- Human operator access is disclosed.
- Review findings guide action but do not force edits.
- Evidence capture is non-sensitive and product-learning oriented.

## Next Build Use

Use this prototype to run the first concierge-assisted trial path and observe:

- whether the intake fields are understandable
- whether the workflow state is obvious
- whether the spine step creates the value moment
- whether the review gate feels specific
- whether the evidence capture is lightweight enough
- what should be automated next
