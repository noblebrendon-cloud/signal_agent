# ATOM-provenance-is-portable-memory

Originating events:

- `EVT-2026-06-29-project-studio-governed-handoff`

## Concept

Provenance is portable memory.

## Why It Matters

The handoff does not rely on a single local pointer. It mirrors governed metadata into
the Project Studio operational index, the matching `letter_outputs[]` entry, and both
`letter.json` and `manifest.json` metadata. That makes lineage, source snapshots, and
draft intent available across tools without copying the full source docs.

## Evidence Trail

- `app/letters_of_light/governed_handoff.py`
- `tests/test_project_studio_governed_handoff.py::test_letter_contains_immutable_governed_handoff_metadata_and_source_grounding`
- `tests/test_project_studio_governed_handoff.py::test_project_metadata_contains_compact_handoff_index_reference`

## Reuse Notes

Useful for content about metadata, lineage, source grounding, and future tool
interoperability.

