# Public Surface Governance Assessment

**Generated**: 2026-05-21
**Scope**: Read-only assessment plus schema-only bridge recommendation
**Execution wiring changed**: No
**Public content mutated**: No

## Purpose

This assessment maps the missing governance bridge between the existing execution
system and the ecosystem's public philosophical and community surfaces.

The repo already has hard controls for operational meaning:

```text
declared intent
-> bounded workflow
-> transition gate
-> governed write
-> append-only evidence
-> reconciliation
```

The public-surface bridge is not a replacement for that authority. It is the
missing layer that should make public derivatives answerable to:

- canonical primitives
- domain identity
- transform constraints
- approval boundaries
- moderation and escalation doctrine
- archive and provenance expectations

## Sources Reviewed

Primary authority and bridge-adjacent files:

- `GOVERNANCE_KERNEL.md`
- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/spine_router.yaml`
- `config/policies/publication_policy.yaml`
- `docs/architecture/ARTIFACT_MODEL.md`
- `docs/architecture/PACKAGE_LINEAGE_CONTRACT.md`
- `docs/operator/OPERATOR_INDEX.md`
- `docs/operator/repo_zone_classification.md`
- `docs/operator/reflective_pressure_spine_architecture.md`
- `docs/operator/reflective_corpus_pressure_boundary.md`
- `docs/letters_of_light/README.md`
- `docs/letters_of_light/sunday_runbook.md`
- `app/letters_of_light/`
- `signal_agent/content/wtpu_channel.py`
- `constraints/packs/domain/wtpu_pack.yaml`
- `services/release_orchestrator/`
- `services/resonance_loop/`
- `sites/brendonrcoleman/signal/`

Targeted searches were also run for `Mars Hill`, `Antigravity`, moderation,
approval matrices, primitive registries, domain profiles, and public-surface
schema names.

## Assessment Summary

The execution layer is ahead of the philosophical and community layers.

The current repo can already constrain state mutation, package lineage, local
retention, and selected content transforms. It does not yet provide a canonical
public-surface registry that answers four public questions before scale:

1. Which primitive is a derivative allowed to inherit?
2. Which domain identity is the derivative allowed to speak within?
3. Which transform path may compress or expand that primitive?
4. Which decision record proves review, hold, rejection, or emission readiness?

Until those questions have a narrow schema boundary, platform adapters can be
well-governed operationally while still becoming philosophically incoherent.

## 1. Existing Hard-Control Inventory

| Control surface | Current evidence | Bridge relevance |
|---|---|---|
| System lifecycle | `config/state_machine.yaml`, transition gate references in `GOVERNANCE_KERNEL.md` | Public artifacts should not create a second lifecycle authority. |
| Fail-closed transition behavior | `GOVERNANCE_KERNEL.md`, canonical control states `held`, `rejected`, `failed`, `aborted` | Unknown public domain or provenance should become a hold or quarantine condition later. |
| Lane and route authority | `config/lanes.yaml`, `config/spine_router.yaml` | Public domains should be profiles above lanes, not ad hoc platform routes. |
| Publication policy | `config/policies/publication_policy.yaml` | Bridge schemas should preserve provenance and staged/emitted distinction. |
| Artifact identity and lineage | `docs/architecture/ARTIFACT_MODEL.md`, `docs/architecture/PACKAGE_LINEAGE_CONTRACT.md` | Public derivatives need upstream primitive and decision references in addition to file hashes. |
| Declared execution boundaries | `docs/operator/OPERATOR_INDEX.md`, operator runtime docs | Public bridge work must remain subordinate to existing execution authority. |
| Local-only retention | retention guide and approval stages | Public subscriber/contact paths are not external-send authority. |
| Reflective-pressure safety | `docs/operator/reflective_pressure_spine_architecture.md` | The repo already has pressure, risk, and human-review patterns worth reusing. |
| Letters safety boundary | `docs/letters_of_light/README.md`, `docs/letters_of_light/sunday_runbook.md` | High-trust spiritual derivatives already require manual review and permission checks. |
| WTPU domain constraint pack | `constraints/packs/domain/wtpu_pack.yaml` | A domain profile can point to existing constraint packs instead of duplicating them. |

## 2. Public-Surface Gap Map

| Gap | Observed state | Why it matters |
|---|---|---|
| Invariant registry | Invariants are present in kernel docs, corpus language, and local subsystem rules, but no public philosophical registry was found. | Public adaptation has no canonical invariant target. |
| Domain manifests | WTPU has identity constraints and Letters has local runbooks; Signal is a site/surface; Mars Hill has no inspected local profile. | Domain boundaries remain uneven and informal. |
| Primitive registry | Claims, corpus fragments, and reflective-pressure records exist, but no canonical public primitive ledger was found. | Derivatives cannot prove what source thought they are rendering. |
| Transform-job schema | Release, claim, video, WTPU, and Letters transforms have local contracts. No public bridge contract spans them. | Tone and intent mutation stays adapter-specific. |
| Governance-decision schema | Runtime and retention decisions exist in their subsystems. No public derivative decision envelope was found. | Human approval for sensitive content stays scattered. |
| Published artifact archive | Artifact and package lineage exist. Platform/public derivative identity is not yet unified by domain and primitive. | Public outputs can be archived as files without philosophical lineage. |
| Audience-signal boundary | Facebook resonance and reflective-pressure observations exist. No shared boundary says what audience signals may alter. | Feedback can tune content shape before its authority is classified. |
| Moderation doctrine | Reflective moderation concepts and risk metrics exist, but no community moderation/escalation doctrine was found for public groups/pages. | Community growth can outrun legitimacy and repair rules. |

## 3. Drift-Risk Map By Domain

| Domain or surface | Mapping status | Drift risk | Primary bridge need |
|---|---|---|---|
| `letters_of_light` | Partially mapped | Spiritual authority creep, sentiment flattening, permission gaps | Domain profile with human approval class and facility/media boundaries. |
| `wtpu` | Partially mapped | Civic tribalization, persona bleed, conflict amplification | Domain profile tied to existing constraint pack and audience-signal limits. |
| `signal` | Partially mapped | Umbrella identity absorbs incompatible lanes | Domain profile that separates intake voice, public derivatives, and platform CTAs. |
| `signal_antigravity` | Informal | Tooling or artifact provenance mistaken for domain identity | Treat Antigravity references as unmapped context until explicitly profiled. |
| `mars_hill` | Unmapped in reviewed repo material | Domain meaning inferred by name rather than contract | Quarantine until source corpus, purpose, tone, and moderation boundary are mapped. |
| YouTube | Adapter/surface | Thumbnail, hook, and compression drift | Platform profile and transform constraint references. |
| Facebook pages/groups | Adapter plus community surface | Outrage and comment escalation | Moderation doctrine, escalation ladder, audience-signal boundary. |
| Substack | Adapter/surface | Long-form authority drift and cross-domain blending | Primitive lineage, domain profile, review decision. |
| Standalone sites | Stable surface | Stale claims or flattened ecosystem map | Published artifact/archive metadata and review cadence. |

## 4. Public Paths Missing Primitive Provenance

The following public-adjacent paths can create or package derivatives without a
repo-wide public primitive registry:

| Path family | Current source anchor | Primitive lineage gap |
|---|---|---|
| Release orchestrator | `SignalExtraction` with thesis, pillars, anchor phrases | No shared `SignalPrimitive` identity or domain authority. |
| Claim distributor | claim ids and platform outputs | Claim anchoring is narrower than ecosystem primitive lineage. |
| Source-video derivation | source artifact and workspace manifests | Public derivative path is media-strong but primitive-optional. |
| WTPU channel | raw thought plus WTPU constraints | Raw thought is not yet a governed public primitive. |
| Letters weekly render | canonical weekly letter and local output bundle | Letter has local identity; primitive references are not a shared ecosystem contract. |
| Signal capture site | direct public CTA text | Website public surface is not linked to domain profile or reviewed artifact metadata. |

## 5. Tone-Mutation Surfaces

These code paths intentionally adapt content shape. They should later consume
transform constraints instead of relying on adapter-local tone assumptions.

| Adapter or transform | Mutation surface | Current control clue |
|---|---|---|
| `services/release_orchestrator/channels/*` | long-form, compressed, thumbnail, visual, and merch variants | typed coherence checks exist inside the service |
| `signal_agent/content/claim_distributor.py` | platform-native claim rendering | deterministic renderers, but no domain profile input |
| `signal_agent/media/source_video_derivation.py` | summaries, seeds, descriptions, title candidates | media provenance exists; philosophical provenance is not required |
| `signal_agent/content/wtpu_channel.py` | raw thought to hook, script, title, and Facebook text | WTPU prompt and constraint pack exist |
| `app/letters_of_light/weekly_render.py` | letter to email, print, jail, social, and checklist outputs | local-only render and approval boundaries exist |

## 6. Community Governance Gap

Community-facing governance is currently more conceptual than canonical.

Observed pieces:

- reflective-pressure classification includes `risk_of_tribal_escalation`
- resonance constraints explicitly avoid conflict escalation
- Letters runbooks require human approval before sharing
- retention stages keep external contact execution local-only

Missing public doctrine:

- moderation philosophy for Facebook groups/pages and future community spaces
- escalation ladder for participant conflict and high-risk replies
- repair vs removal criteria
- boundary for spiritual, civic, and personal-authority claims
- reason-code format for moderation and publishing holds
- incident archive expectations

## 7. Quarantine Recommendations

Fail closed for public-domain identity when the repo cannot prove the profile.

| Domain | Immediate treatment |
|---|---|
| `mars_hill` | Quarantine until a source inventory and domain profile exist. |
| `signal_antigravity` | Do not treat Antigravity artifact references as public domain authority. |
| New public domains | Require a profile before transform or emission wiring. |
| Cross-domain primitives | Hold until compatible domains and prohibited transforms are recorded. |

Quarantine here means no new public-surface automation authority. It does not
mean delete references, hide research, or block manual operator assessment.

## 8. Narrow Implementation Recommendation

The first implementation slice should remain schema-only:

1. keep this assessment under `docs/operator/`
2. add a schema plan that names the public bridge envelopes
3. add example domain profiles under `config/public_surfaces/`
4. add an example primitive registry under `config/public_surfaces/`
5. do not wire those files into transition, publication, or emission code yet

This keeps the bridge aligned with existing `config/`, `data/state/`,
`docs/operator/`, and `shared/` patterns while avoiding a competing runtime
authority.

## Files Not To Touch Yet

Do not widen this slice into these files yet:

- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/spine_router.yaml`
- `config/policies/publication_policy.yaml`
- `app/hq/governance/transition_gate.py`
- `data/artifact_registry.jsonl`
- `data/state/artifact_registry.jsonl`
- existing public site copy
- existing Letters of Light public materials
- WTPU generation or posting paths
- external sender or posting adapters

The bridge should become legible before it becomes executable.
