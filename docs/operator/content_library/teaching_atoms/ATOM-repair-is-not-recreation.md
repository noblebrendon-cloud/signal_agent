# ATOM-repair-is-not-recreation

Originating events:

- `EVT-2026-06-29-project-studio-governed-handoff`

## Concept

Repair is not recreation.

## Why It Matters

When the Project Studio operational index is missing, the adapter can repair it from
the existing Letter metadata. It does not create another Letter for the same handoff.
When the linked Letter is unavailable or deleted, the adapter raises
`linked_draft_unavailable` rather than recreating under the same intent.

## Evidence Trail

- `app/letters_of_light/governed_handoff.py::_repair_index_from_letter`
- `tests/test_project_studio_governed_handoff.py::test_retry_after_missing_index_finds_matching_letter_and_repairs_without_duplicate`
- `tests/test_project_studio_governed_handoff.py::test_unavailable_deleted_linked_letter_conflicts_and_does_not_recreate`

## Reuse Notes

Useful for explaining recovery behavior, operational indexes, and why repair should
preserve identity.

