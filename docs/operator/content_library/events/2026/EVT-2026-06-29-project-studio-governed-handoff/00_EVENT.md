# EVT-2026-06-29-project-studio-governed-handoff

Status: captured
Captured: 2026-06-29
Title: Project Studio governed handoff

## Summary

Project Studio gained a backend governed-handoff adapter that opens a promoted
Governed Publishing drafting brief into one editable, source-selected Letter draft.
The adapter lives on the Project Studio side, calls the existing
`create_project_letter(...)` path, preserves governed provenance in operational and
immutable metadata locations, and keeps the opened Letter in draft posture.

This event captures the evidence and reusable concepts. It does not create public
social content.

## Scope Captured

- Adapter placement in Project Studio.
- Use of the existing `create_project_letter(...)` source-selected Letter path.
- Authority boundary between Project Studio and Governed Publishing.
- Operational and immutable provenance locations.
- Idempotency and repair behavior.
- Unavailable or deleted linked Letter behavior.
- Draft-only and `release_eligible = False` boundary.
- Focused handoff, governed-publishing slice, and Project Studio test counts.
- Source paths, design docs, and repository reference at capture time.

## Source Paths

- `app/letters_of_light/governed_handoff.py`
- `app/letters_of_light/project_studio.py`
- `signal_agent/governed_publishing/drafting_brief.py`
- `tests/test_project_studio_governed_handoff.py`
- `tests/test_governed_publishing_*.py`
- `tests/test_letters_project_studio.py`
- `tests/test_creation_manager.py`
- `tests/test_multi_brand_studio.py`
- `docs/operator/governed_authoring_studio_publishing/14_PHASE_1I_PROJECT_STUDIO_HANDOFF_INTEGRATION_GATE.md`

## Repository References

- Source baseline observed at capture start: `8e71b10e312cfee01063dc94b95cf9df08e04260`.
- The governed-handoff implementation files were present in the working tree at
  capture time.
- This content-library event does not modify Project Studio, Governed Publishing,
  release behavior, runtime state, or external services.

## Boundaries

The captured implementation does not add a UI route, API route, or
`release_server.py` handoff path. It does not create release approval, package
readiness, schedule, queue, export, publication, platform action, OAuth activity, or
governed-ledger mutation.

Governed Publishing remains authoritative for lineage, promotion, and source
snapshots. Project Studio stores an operational copy for editor workflow and repair.

