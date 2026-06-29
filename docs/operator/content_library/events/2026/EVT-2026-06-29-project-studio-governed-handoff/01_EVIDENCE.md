# Evidence

Event ID: `EVT-2026-06-29-project-studio-governed-handoff`

## Verified Implementation Facts

| Fact | Evidence |
| --- | --- |
| The adapter lives in Project Studio scope. | `app/letters_of_light/governed_handoff.py` imports Project Studio helpers and exposes `open_governed_drafting_brief_in_project_studio(...)`. |
| The adapter calls the existing source-selected Letter path. | `app/letters_of_light/governed_handoff.py` calls `project_studio.create_project_letter(...)`; `app/letters_of_light/project_studio.py` defines `create_project_letter(project_id, body)`. |
| No handoff UI or API route is part of this capture. | The design gate keeps route/UI exposure out of Phase 1I; `rg "governed_handoff|open_governed_drafting_brief" app/letters_of_light/release_server.py` returned no matches during capture. |
| Project Studio stores an operational index. | `project.json["governed_handoffs"][handoff_id]` is written through `GOVERNED_HANDOFF_INDEX_KEY = "governed_handoffs"`. |
| Letter provenance is immutable metadata. | The adapter writes `metadata.governed_handoff` and `metadata.governed_handoff_id` into both `letter.json` and `manifest.json`. |
| The Project Studio output mirror is updated. | The matching `letter_outputs[]` entry receives `governed_handoff` metadata and the linked `letter_id`. |
| Governed Publishing remains authoritative for lineage, promotion, and source snapshots. | The handoff payload marks `governed_publishing_ledger_authoritative = True` and `project_studio_operational_copy = True`. |
| Handoff identity is deterministic. | `project_studio_draft_handoff_identity(...)` derives identity from `proposal_id` plus `draft_intent_ref`. |
| Same handoff returns the existing Letter. | Focused test: `test_same_proposal_plus_same_draft_intent_is_idempotent`. |
| Different `draft_intent_ref` creates an allowed distinct Letter. | Focused test: `test_same_proposal_with_different_draft_intent_creates_distinct_allowed_letter_draft`. |
| Missing operational index can be repaired from Letter metadata. | Focused test: `test_retry_after_missing_index_finds_matching_letter_and_repairs_without_duplicate`. |
| Duplicates raise an integrity conflict. | Focused test: `test_duplicate_matching_letters_cause_visible_integrity_conflict`. |
| Unavailable or deleted linked Letters are not recreated. | Focused test: `test_unavailable_deleted_linked_letter_conflicts_and_does_not_recreate`. |
| Opened Letters remain draft posture. | The adapter sets `lifecycle_state = "draft"` on `letter.json`, `manifest.json`, and the creation job. |
| The creation job is not release eligible. | The adapter sets `release_eligible = False` and adds the governed handoff release blocker. |
| No release, approval, package, schedule, queue, export, publication, platform, OAuth, or governed-ledger mutation is created. | Focused test: `test_no_handoff_creates_approval_readiness_release_schedule_export_publication_or_platform_state`; governed drafting-brief tests also assert no execution or publication state. |

## Test Evidence

| Slice | Command | Result |
| --- | --- | --- |
| Focused handoff | `python -m pytest tests/test_project_studio_governed_handoff.py` | 13 passed |
| Governed Publishing slice | `$files = (Get-ChildItem -LiteralPath tests -Filter 'test_governed_publishing_*.py').FullName; python -m pytest @files` | 112 passed |
| Focused Project Studio | `python -m pytest tests/test_letters_project_studio.py tests/test_creation_manager.py::test_revision_creates_new_letter_and_preserves_parent_id tests/test_multi_brand_studio.py::test_active_brand_can_create_project tests/test_multi_brand_studio.py::test_existing_letters_default_flow_remains_functional tests/test_multi_brand_studio.py::test_wtpu_release_blocks_when_required_evidence_missing tests/test_multi_brand_studio.py::test_clone_to_brand_preserves_parent_source_linkage` | 16 passed |

## Design Evidence

- `docs/operator/governed_authoring_studio_publishing/14_PHASE_1I_PROJECT_STUDIO_HANDOFF_INTEGRATION_GATE.md`
- `docs/operator/governed_authoring_studio_publishing/13_PHASE_1H_DRAFTING_BRIEF_AND_HANDOFF_CONTRACT.md`

## Capture Note

This evidence record points to source paths and test commands. It does not duplicate
source docs, implementation files, or runtime state.
