# Teaching Atoms

Event ID: `EVT-2026-06-29-project-studio-governed-handoff`

The reusable concepts extracted from this event are canonicalized in
`docs/operator/content_library/teaching_atoms/`.

| Atom | Concept | Origin |
| --- | --- | --- |
| [ATOM-draft-is-not-release](../../../teaching_atoms/ATOM-draft-is-not-release.md) | A draft is not a release. | Opened Letters remain draft-only and `release_eligible = False`. |
| [ATOM-idempotency-is-a-trust-feature](../../../teaching_atoms/ATOM-idempotency-is-a-trust-feature.md) | Idempotency is a trust feature. | Same `proposal_id + draft_intent_ref` returns the existing Letter. |
| [ATOM-provenance-is-portable-memory](../../../teaching_atoms/ATOM-provenance-is-portable-memory.md) | Provenance is portable memory. | Governed metadata is mirrored across Project Studio and Letter records. |
| [ATOM-repair-is-not-recreation](../../../teaching_atoms/ATOM-repair-is-not-recreation.md) | Repair is not recreation. | Missing operational index is repaired from Letter metadata without duplicate creation. |
| [ATOM-authority-boundaries-prevent-drift](../../../teaching_atoms/ATOM-authority-boundaries-prevent-drift.md) | Authority boundaries prevent system drift. | Governed Publishing keeps lineage authority; Project Studio keeps editor workflow authority. |

## Extraction Boundary

These atoms are not public posts. They are reusable teaching concepts available for
future deliberate drafting.
