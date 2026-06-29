# Capture Loop

Use this loop each time a system feature reaches a real passing boundary.

```text
Build completed
  ->
Run content-event capture
  ->
Record verified facts, boundaries, tests, and source references
  ->
Extract 3-7 teaching atoms
  ->
List possible derivatives without drafting them
  ->
Mark event captured
  ->
Later, choose one atom or derivative when content is needed
  ->
Publish deliberately and log the result
```

## Capture Standard

A captured event should include:

- stable event ID;
- short title and capture date;
- implementation facts supported by source paths, tests, docs, or commits;
- explicit authority boundaries;
- test commands and passing counts;
- source files and design docs;
- 3-7 reusable teaching atoms;
- queued derivative ideas only;
- publication ledger state.

## Anti-Recreation Rule

Each event has a stable ID. The scaffold tool must treat that ID as the identity of
the record:

```text
same event ID exists
  -> reopen existing record
  -> create missing standard files only
  -> never overwrite evidence, atoms, backlog, or publication history

new event ID
  -> create new event folder from templates
  -> add one row to CONTENT_LIBRARY_INDEX.md
```

This makes the documentation layer behave like a governed handoff: repeatable,
repairable, and hostile to accidental duplication.

## Non-Goals

The capture loop does not:

- draft public posts automatically;
- create release approvals;
- create publication schedules;
- mutate runtime state;
- call external services;
- replace source docs, tests, or implementation files.

