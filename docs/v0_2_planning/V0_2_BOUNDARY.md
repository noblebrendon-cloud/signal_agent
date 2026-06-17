# v0.2 Boundary

Version target:

```text
v0.2-local-authoring-surface
```

## Current Public Boundary

The v0.1 boundary remains intact:

```text
v0.1-local-proof-pack verifies a local proof pack for formal governance and covered Governed Authoring paths. It is not a production Governed Authoring app, not a backend-wired UI, not repo-wide governance, and not complete IBVM proof.
```

v0.2 planning must not weaken or inflate that claim.

## v0.2 Intended Boundary

v0.2 may aim to claim:

```text
v0.2 defines and, if later approved, implements a controlled local authoring surface over covered local proof-pack paths.
```

It must remain:

- Local.
- Non-production.
- Explicit-path only.
- No default production writes.
- No production authoring artifact store.
- No default production canonical ledger writes.
- No repo-wide governance claim.
- No complete IBVM claim.

## Non-Goals

v0.2 does not aim to prove:

- Production Governed Authoring app.
- Backend-wired production UI.
- Public hosted app.
- Server/app surface for production use.
- Browser-backend submission for production use.
- Production authoring artifact writes.
- Default production canonical authoring ledger writes.
- Repo-wide governance.
- All state-mutating paths gated.
- Universal self-certification prevention.
- Complete IBVM proof across every path.

## Boundary Risks

| Risk | Boundary concern | Required guard |
| --- | --- | --- |
| Local server prototype | May sound like production backend wiring | Call it local-only and keep explicit paths |
| Browser submission | May imply backend-wired UI | Require a decision gate before implementation |
| Output persistence | May become production artifact writes | Use explicit temp/user output directories only |
| Canonical ledger writes | May imply default production ledger policy | Allow only configured explicit paths |
| Human approval | May imply real authority integration | Define local authority representation before implementation |
| Generated content | May self-certify | Require evidence and review gates |

## Release Language

Allowed:

- "v0.2 planning defines the next controlled local authoring surface."
- "v0.2 planning preserves the v0.1 proof-pack boundary."
- "v0.2 is not production."

Disallowed:

- "v0.2 is a production app."
- "The UI is backend-wired for production."
- "All authoring is governed."
- "Repo-wide governance is complete."
- "Complete IBVM proof exists."
