# ATOM-draft-is-not-release

Originating events:

- `EVT-2026-06-29-project-studio-governed-handoff`

## Concept

A draft is not a release.

## Why It Matters

Opening a work surface should not silently grant approval, readiness, scheduling, or
publication authority. In this event, a governed brief opens an editable Letter draft,
but the adapter forces draft posture and sets `release_eligible = False`.

## Evidence Trail

- `app/letters_of_light/governed_handoff.py`
- `tests/test_project_studio_governed_handoff.py::test_valid_promoted_governed_brief_opens_one_source_selected_letter_draft`
- `tests/test_project_studio_governed_handoff.py::test_no_handoff_creates_approval_readiness_release_schedule_export_publication_or_platform_state`

## Reuse Notes

Useful for explaining release gates, editor workspaces, and why draft creation must be
separate from public action.

