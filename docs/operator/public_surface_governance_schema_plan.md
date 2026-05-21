# Public Surface Governance Schema Plan

**Generated**: 2026-05-21
**Scope**: Schema proposal only
**Runtime authority changed**: No

## Purpose

This plan defines a minimal public-surface governance bridge above existing
execution governance. It does not introduce a second state machine, replace
artifact lineage, or authorize external posting.

The bridge should make this path auditable later:

```text
reviewed source
-> canonical primitive
-> domain profile
-> bounded transform job
-> governance decision
-> published artifact record
-> bounded audience signal
```

## Design Rules

1. Reuse existing lifecycle, lane, publication, artifact, and ledger authority.
2. Treat these schemas as public-surface envelopes, not runtime replacements.
3. Fail closed when domain identity, primitive provenance, or approval class is
   unknown.
4. Keep raw audience response diagnostic until a governed decision promotes any
   learning into constraints.
5. Prefer examples and validation plans before wiring registries into execution.

## Proposed Schema Set

### `SignalPrimitive`

Purpose: identify the smallest reviewed philosophical/content unit allowed to be
expanded, compressed, or referenced by public derivatives.

Required fields:

| Field | Meaning |
|---|---|
| `primitive_id` | Stable identifier for the canonical unit. |
| `schema_version` | Primitive schema version. |
| `status` | Candidate, reviewed, approved, held, rejected, or archived. |
| `canonical_text` | The exact governed text or concise canonical claim. |
| `source_refs` | Source corpus, artifact, or decision references. |
| `invariant_refs` | Invariants the primitive must preserve. |
| `compatible_domain_ids` | Domains allowed to render this primitive. |
| `prohibited_transforms` | Transform classes disallowed for the primitive. |
| `risk_class` | Risk level before derivative generation. |
| `approval_class` | Approval boundary required for public derivative use. |

Optional near-term fields:

- `aliases`
- `pressure_tags`
- `tone_notes`
- `supersedes_primitive_id`
- `reviewed_by`
- `reviewed_at_utc`

### `DomainProfile`

Purpose: define the public identity boundary for a philosophical, civic,
spiritual, or umbrella domain.

Required fields:

| Field | Meaning |
|---|---|
| `domain_id` | Stable domain key. |
| `status` | Example, candidate, active, held, quarantined, or archived. |
| `purpose` | Public role of the domain. |
| `audience_boundary` | Audience and trust conditions. |
| `tone_constraints` | Required tone markers and disallowed tone shifts. |
| `allowed_output_classes` | Formats allowed before transform wiring. |
| `forbidden_output_classes` | Formats not admitted for the domain. |
| `required_approval_class` | Minimum review boundary. |
| `provenance_requirements` | Primitive, source, and decision references required. |
| `moderation_profile_ref` | Community doctrine reference or explicit missing marker. |

Optional near-term fields:

- `constraint_pack_refs`
- `platform_surface_refs`
- `quarantine_reason`
- `owner`
- `review_cadence`

### `TransformJob`

Purpose: bind a derivative operation to source, domain, format, and policy
without making the platform adapter the authority.

Required fields:

| Field | Meaning |
|---|---|
| `transform_job_id` | Stable transform request identity. |
| `primitive_refs` | Source primitive ids. |
| `domain_id` | Domain profile selected for the job. |
| `target_output_class` | Essay, post, monologue, script, prompt, policy seed, etc. |
| `target_surface` | Platform or local staging target. |
| `transform_constraints` | Length, tone, audience, and prohibited mutation rules. |
| `source_artifact_refs` | Existing artifact or bundle references when applicable. |
| `approval_class` | Approval boundary required before emission. |
| `state_ref` | Existing runtime state reference once execution is wired. |

### `GovernanceDecision`

Purpose: record public-surface review without inventing a parallel mutation path.

Required fields:

| Field | Meaning |
|---|---|
| `decision_id` | Stable decision identity. |
| `subject_type` | Primitive, domain profile, transform job, published artifact, or audience signal. |
| `subject_id` | Governed subject reference. |
| `decision` | Approve, hold, reject, quarantine, release, or archive. |
| `actor_type` | Human operator, policy gate, or bounded system reviewer. |
| `actor_id` | Actor identity or policy identity. |
| `reason_codes` | Bounded reasons for the decision. |
| `evidence_refs` | Source, artifact, or report references. |
| `decided_at_utc` | Decision time. |

Optional near-term fields:

- `expires_at_utc`
- `supersedes_decision_id`
- `required_followup`

### `PublishedArtifact`

Purpose: preserve public derivative provenance after publication or local
publication-ready staging.

Required fields:

| Field | Meaning |
|---|---|
| `published_artifact_id` | Public derivative identity. |
| `artifact_ref` | Existing artifact identity or local durable path reference. |
| `primitive_refs` | Source primitive ids. |
| `domain_id` | Public domain authority used. |
| `transform_job_ref` | Transform that produced the derivative. |
| `governance_decision_refs` | Approval/hold/release decisions. |
| `surface` | Local staging or public platform surface. |
| `publication_state` | Draft, staged, emitted, audited, archived, or held. |
| `content_hash` | Immutable content hash where available. |
| `published_at_utc` | Time of emission when externally emitted. |

### `AudienceSignal`

Purpose: capture response evidence without letting engagement become doctrine.

Required fields:

| Field | Meaning |
|---|---|
| `audience_signal_id` | Stable signal record identity. |
| `published_artifact_ref` | Public derivative receiving response. |
| `surface` | Platform or community surface. |
| `observation_window` | Time window observed. |
| `metrics` | Bounded observed metrics. |
| `qualitative_labels` | Recognition, constructiveness, pressure, risk labels. |
| `risk_flags` | Escalation, dependency, conflict, or moderation flags. |
| `allowed_feedback_use` | Diagnostic, review_input, constraint_candidate, or disallowed. |
| `captured_at_utc` | Capture time. |

## Example Files In This Slice

| File | Role |
|---|---|
| `config/public_surfaces/domain_profiles.example.yaml` | Example-only domain profile shapes and quarantine flags. |
| `config/public_surfaces/primitive_registry.example.jsonl` | Example-only primitive registry records. |

These files are not live registry authority. Their purpose is to let the next
review tighten field names, approval classes, and fail-closed behavior before
code loads anything.

## Recommended Folder Structure

Near-term, stay inside existing roots:

```text
config/
  public_surfaces/
    domain_profiles.example.yaml
    primitive_registry.example.jsonl

docs/
  operator/
    public_surface_governance_assessment.md
    public_surface_governance_schema_plan.md
```

Only after the schema is accepted and a live registry boundary is authorized:

```text
config/
  public_surfaces/
    domain_profiles.yaml
    approval_classes.yaml
    platform_profiles.yaml

data/
  state/
    public_surface_governance_decisions.jsonl
    public_surface_primitives.jsonl
    public_surface_published_artifacts.jsonl
    public_surface_audience_signals.jsonl
```

The live files above are intentionally not created in this slice.

## Narrow First Implementation Slice

This slice is intentionally limited to:

1. repository assessment
2. schema proposal
3. example domain profiles
4. example primitive registry rows

Do not add:

- transition-gate changes
- lane or router changes
- publication-policy changes
- live ledgers
- posting adapters
- audience scraping
- public-content rewrites

## Validation Plan

Schema validation should be introduced only after the example fields are
reviewed.

First validation pass should check:

1. domain profile ids are unique
2. quarantined domains cannot advertise active transform permission
3. primitives carry at least one source reference
4. primitives cannot name unknown compatible domains when a live registry
   exists
5. transform jobs require both primitive and domain authority
6. governance decisions always include reason codes
7. published artifacts cannot be emitted without transform and decision refs
8. audience signals cannot declare doctrine or automatic publishing authority

## Tests Needed When Wiring Begins

No runtime tests are required for the docs/config example slice itself.

When the bridge moves from examples to loaded schemas, add targeted tests for:

- example/live schema parser rejection on missing required fields
- fail-closed domain quarantine behavior
- transform-job denial on missing primitive provenance
- published-artifact denial on missing governance decision refs
- audience-signal feedback-use allowlist
- no external posting or sending admitted by public-surface registry loading
- no conflict with `config/state_machine.yaml`, lane authority, or artifact
  registration authority

## Files That Should Not Be Touched Yet

Hold these until the schema boundary is accepted:

- `app/hq/governance/transition_gate.py`
- `shared/authority.py`
- `shared/artifact_identity.py`
- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/spine_router.yaml`
- `config/policies/publication_policy.yaml`
- `data/artifact_registry.jsonl`
- `data/state/artifact_registry.jsonl`
- public website copy and platform-ready content files

The next code slice should validate a small live registry boundary, not rush to
orchestration.
