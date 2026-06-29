# ATOM-authority-boundaries-prevent-drift

Originating events:

- `EVT-2026-06-29-project-studio-governed-handoff`

## Concept

Authority boundaries prevent system drift.

## Why It Matters

Governed Publishing remains authoritative for lineage, promotion, and source
snapshots. Project Studio receives an operational copy so editors can work, link, and
repair drafts. The adapter explicitly does not create release, approval, schedule,
export, publication, platform, OAuth, or governed-ledger mutations.

## Evidence Trail

- `app/letters_of_light/governed_handoff.py::_handoff_payload`
- `docs/operator/governed_authoring_studio_publishing/14_PHASE_1I_PROJECT_STUDIO_HANDOFF_INTEGRATION_GATE.md`
- `tests/test_project_studio_governed_handoff.py::test_no_handoff_creates_approval_readiness_release_schedule_export_publication_or_platform_state`

## Reuse Notes

Useful for governance architecture, multi-system integration, and explaining why
cross-system metadata should not erase ownership boundaries.

