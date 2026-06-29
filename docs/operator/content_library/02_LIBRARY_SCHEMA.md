# Library Schema

The content library uses Markdown records and stable IDs. Records should be readable
by humans and simple tools.

## Event ID

Event IDs use:

```text
EVT-YYYY-MM-DD-short-kebab-name
```

Example:

```text
EVT-2026-06-29-project-studio-governed-handoff
```

## Event Folder

Each event folder contains five standard files:

| File | Purpose |
| --- | --- |
| `00_EVENT.md` | Summary, scope, source paths, boundaries, and status. |
| `01_EVIDENCE.md` | Verified facts, test evidence, and references. |
| `02_TEACHING_ATOMS.md` | Event-local atom extraction and links to canonical atom records. |
| `03_DERIVATIVE_BACKLOG.md` | Queued derivative ideas only. |
| `04_PUBLICATION_LEDGER.md` | Publications derived from the event. Empty until something goes public. |

## Teaching Atom ID

Teaching atoms use:

```text
ATOM-short-kebab-concept.md
```

Each atom must link back to at least one originating event ID.

## Derivative State

Derivatives are separated by intent:

| Folder | Meaning |
| --- | --- |
| `derivatives/queued/` | Candidate outputs. No draft exists yet. |
| `derivatives/drafted/` | Draft artifacts intentionally created later. |
| `derivatives/published/` | Final published-source records or archived delivered artifacts. |

## Publication Records

Publication records must include:

- publication ID or URL;
- date published;
- public surface;
- source event IDs;
- source atom IDs;
- derivative file, if any;
- operator note on what changed between evidence and public content.

