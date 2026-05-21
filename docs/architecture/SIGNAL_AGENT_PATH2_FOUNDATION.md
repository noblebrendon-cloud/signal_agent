# Signal Agent Path 2 Foundation

Status: bounded Path 2 foundation
Last updated: 2026-03-14
Scope: ontology clarity, governed state transitions, artifact schema discipline, lane formalization, and auditability

## System Identity Statement

Signal Agent is an artifact-governed operational system for converting volatile inbound signals into governed records, durable artifacts, lane-specific outputs, and auditable evidence. Path 2 prioritizes internal operational truth over public framework extraction: append-only ledgers, explicit governance gates, deterministic routing, durable artifact registration, and inspectable lineage are the intended authority surfaces.

This phase does not claim that the repo is a generic orchestration framework. It defines the canonical internal model that later framework extraction can be based on.

## Committed Foundation Scope

The committed HQ transition-governance foundation currently includes:

- `app/hq/governance/transition_gate.py`
- `config/state_machine.yaml`
- `config/lanes.yaml`
- `config/policies/intake_policy.yaml`
- `config/policies/promotion_policy.yaml`
- `config/policies/routing_policy.yaml`
- `config/policies/publication_policy.yaml`
- direct proof in `tests/test_hq_transition_gate.py`

That foundation does not by itself claim completed capture/intake adoption, activation-governor adoption, shared lifecycle migration, operator/security integration, registry reconciliation, external execution, production deployment, or automated approvals.

## Repo-Native Architecture Anchors

The broader Path 2 model is anchored to repo-native operational surfaces and planned integration targets:

- `app/intake/intake.py` and `data/intake/intake.jsonl` for ingest and append-only intake records.
- `app/hq/capture/capture.py` and `data/capture/capture_log.jsonl` for volatile raw capture.
- `app/hq/capture/promote.py` and `data/capture/promotion_log.jsonl` for deterministic bundle promotion.
- `app/hq/capture/router.py` and `data/capture/routing_log.jsonl` for deterministic spine routing.
- `app/hq/curation/curate.py` and `data/artifact_registry.jsonl` for durable artifact registration.
- `app/governor/__init__.py` and `app/governor/activation_governor.py` as an adjacent enforcement, lock, override, and event-logging surface.
- `signal_agent/content/lineage_status.py` as a lineage reconstruction surface.
- `signal_agent/media/source_video.py` and `signal_agent/media/video_loop_builder.py` for media artifact manifests and package outputs.
- `services/clipboard_intake_spine/` and `services/concept_formalization_spine/` as typed intake, normalization/classification, and downstream transform surfaces.

These anchors explain the model. They are not evidence that every adjacent surface is integrated with the committed transition gate today.

## Canonical First-Class Objects

| Object | Canonical meaning in Path 2 | Repo-native anchors |
| --- | --- | --- |
| Signal | A volatile inbound input before durable artifact registration. Signals may be text, URLs, files, clipboard payloads, or other inbound fragments. | `app/hq/capture/capture.py`, `app/intake/intake.py`, `services/clipboard_intake_spine/` |
| Record | A persisted structured entry describing a signal, transition, result, or materialized metadata. Records include ledgers, manifests, registries, and summaries. | `data/intake/intake.jsonl`, `data/capture/*.jsonl`, `artifacts/videos/*/package_index.json` |
| Artifact | A durable governed output with identity, path, provenance, and audit relevance. Not every record is an artifact. | `app/hq/curation/curate.py`, `data/artifact_registry.jsonl`, `signal_agent/media/source_video.py` |
| Lane | A governed processing corridor that combines routing destination, governing policies, transforms, emission surfaces, and failure behavior. A spine is a routing destination inside the lane model, not the whole lane. | `config/spine_router.yaml`, `constraints/spines/`, `config/lanes.yaml` |
| Policy | A declarative constraint set that determines whether a transition or action is allowed. | `config/policies/*.yaml`, `app/governor/` |
| Gate | A concrete decision point where policy is applied before state transition or mutation. | Governor enforcement, routing threshold checks, curation gate, publication readiness checks |
| Transition | An allowed movement between canonical states. Transitions must be observable through one or more records. | `docs/architecture/STATE_MACHINE.md`, `config/state_machine.yaml` |
| Run | A bounded execution instance that produces records, artifacts, or both. A CLI invocation, packaging build, audit run, or transform pass is a run. | `signal_agent/media/video_loop_builder.py`, `signal_agent/leviathan/diagnostic/drift_audit/run.py` |
| Ledger Event | An append-only event describing a decision, transition, or enforcement action. Every ledger event is a record, but not every record is a ledger event. | `data/intake/intake.jsonl`, `data/capture/*.jsonl`, governor event logs |
| Bundle | A promoted grouping of related signals or records that becomes the routable unit. A bundle is not automatically a durable artifact. | `app/hq/capture/promote.py`, `constraints/spines/*/incoming/` |

## Canonical Verbs

| Verb | Canonical meaning in Signal Agent | Existing anchors |
| --- | --- | --- |
| capture | Persist an inbound signal with enough metadata to reference it later. | `app/hq/capture/capture.py`, `app/intake/intake.py` |
| normalize | Convert raw payloads into canonical text or structured form without changing semantic intent. | `app/intake/intake.py`, `services/clipboard_intake_spine/normalize_payload.py` |
| classify | Assign an initial routing or processing class. | `services/clipboard_intake_spine/classify_clipboard_task.py`, routing feature extraction in `app/hq/capture/router.py` |
| constrain | Apply policies, governance locks, thresholds, or approval logic before advancing state. | `app/governor/`, routing thresholds, policy files |
| promote | Convert one or more captured signals into a bundle suitable for downstream routing. | `app/hq/capture/promote.py` |
| route | Assign a promoted bundle or governed artifact to a lane/spine destination. | `app/hq/capture/router.py`, `services/clipboard_intake_spine/route_clipboard_task.py` |
| transform | Produce a new structured artifact from a bundle or prior artifact. | `services/concept_formalization_spine/`, `app/agents/social_offload/social_offload.py` |
| compile | Assemble transformed artifacts into a durable package or output set. | `signal_agent/media/video_loop_builder.py` |
| stage | Place a compiled or transformed artifact into a lane-specific ready state with manifests, indexes, or publish support materials. | `artifacts/videos/*`, `data/intake/_staging`, package indexes and manifests |
| emit | Deliver a staged artifact to its intended output surface. Path 2 treats emission as lane-specific and partially implemented today. | `data/social_offload/outputs/`, video package outputs, downstream channel assets |
| audit | Reconstruct, verify, and report what happened using ledgers, manifests, and run evidence. | `signal_agent/content/lineage_status.py`, `app/audit/runtime_audit.py` |

## Canonical Lifecycle and State Machine

The canonical Path 2 working flow is:

`captured -> normalized -> classified -> constrained -> promoted -> routed -> transformed -> compiled -> staged -> emitted -> audited`

Control and exception states are:

`held`, `rejected`, `failed`, `aborted`

Important clarifications:

- Not every lane currently exercises every state. The committed transition-gate foundation defines state admission and direct proof for configured transitions; capture, media, and content packaging integrations remain lane-specific dependent work. Emission remains lane-specific and only partially standardized.
- Artifact registration is a required record action, not a separate lifecycle verb. A durable artifact may be registered when a transform, compile, or stage step creates a stable output.
- A bundle is an intermediate governed unit. It does not become an artifact until a durable output with identity, provenance, and path is registered.

See [STATE_MACHINE.md](STATE_MACHINE.md) and `config/state_machine.yaml` for the canonical graph.

## Terminal vs Recoverable States

| State type | States | Meaning |
| --- | --- | --- |
| Terminal | `audited`, `rejected`, `aborted` | The run or object has reached an end condition that should not silently continue in-place. Further work must start a new run or new artifact version. |
| Recoverable | `held`, `failed` | The object is blocked but can resume after a policy release, remediation, or operator action. Resume must be recorded. |
| Working | `captured`, `normalized`, `classified`, `constrained`, `promoted`, `routed`, `transformed`, `compiled`, `staged`, `emitted` | The object remains active in the lane lifecycle. |

## Policy Categories

Path 2 recognizes these policy categories:

- Intake integrity policy: governs raw signal acceptance, normalization rules, and prohibited early mutation.
- Promotion determinism policy: governs bundle formation, repeatability, and promotion logging.
- Routing policy: governs lane assignment, fallback behavior, scoring transparency, and route logging.
- Artifact integrity policy: governs hashable durable outputs, registry discipline, and provenance completeness.
- Publication policy: governs readiness, packaging completeness, and emission eligibility.
- Audit policy: governs lineage reconstructability, ledger completeness, and evidence retention.
- Override and abort policy: governs explicit exceptions, operator overrides, and controlled termination.

## Lane Model

A lane is the Path 2 unit of governed operations. Each lane defines:

- what inputs or artifact classes it accepts
- which policies govern it
- which transforms are allowed inside it
- which emission surfaces it can write to
- what happens when governance or execution fails

A spine is narrower than a lane. Existing directories under `constraints/spines/` are concrete routing destinations. A lane may map to one spine queue, one service surface, or multiple downstream transforms.

Initial active lane registry is defined in `config/lanes.yaml` and is grounded in current repo surfaces:

- `volatile_capture`
- `content_publishing`
- `ai_stability_diagnostic`
- `concept_formalization`
- `video_packaging`
- `misc_review`
- `wtpu_content`

Configured but not yet lane-authoritative surfaces such as `social_field_theory` and `logistics_ops` remain reserved until they have active directories, transforms, and governance behavior.

## Artifact Model

Path 2 treats an artifact as a durable, governed output, not just any file written by the repo. The artifact model is defined in [ARTIFACT_MODEL.md](ARTIFACT_MODEL.md).

In brief:

- Signals are volatile inbound inputs.
- Records are persisted evidence and metadata.
- Bundles are governed intermediate units.
- Artifacts are durable outputs with identity, provenance, and policy relevance.

## Audit Model

Path 2 auditability is ledger-first, not dashboard-first. The minimum audit story is the ability to reconstruct what happened from durable evidence.

The broader audit model expects evidence from repo-native ledgers and manifests such as:

- `data/intake/intake.jsonl`
- `data/capture/capture_log.jsonl`
- `data/capture/promotion_log.jsonl`
- `data/capture/routing_log.jsonl`
- `data/artifact_registry.jsonl`
- `artifacts/videos/video_package_registry.jsonl`
- governor state and event logs in `app/governor/`
- lane-specific manifests and indexes under `artifacts/videos/`
- lineage reconstruction in `signal_agent/content/lineage_status.py`

A valid audit trail should allow an operator to answer:

- what signal or artifact entered the system
- which run or transform touched it
- which policy or gate allowed or blocked progress
- which lane it entered
- which durable artifacts were created
- whether the output was staged, emitted, held, rejected, failed, aborted, or audited

## System Invariants

These invariants define Path 2 discipline:

- Raw capture must not write to `data/artifact_registry.jsonl`.
- Only governed artifact creation paths may register durable outputs in `data/artifact_registry.jsonl` or a lane-specific package registry.
- Every state transition must be inferable from at least one durable record or manifest.
- Routing must be explicit. If confidence is too low, the object goes to `misc_review` or is held; it is not silently dropped.
- Bundles are routable intermediates, not automatically artifacts.
- Durable artifact mutation without a new version or new hash is forbidden.
- Any governor override path must be explicit, time-bounded, and logged.
- Terminal states must not be resumed silently in-place.
- Provenance must only gain information. Downstream transforms may extend provenance, not erase it.
- A lane may specialize behavior, but it may not bypass the canonical governance model.

## Explicit Non-Goals for This Phase

This phase does not attempt to do the following:

- publish Signal Agent as a public SDK or framework
- rename the repo around generic framework terminology
- replace existing modules, ledgers, or CLI entrypoints with a new execution engine
- build a universal workflow runtime for every domain in the repo
- claim that all lanes already implement every canonical state in code
- unify every existing record format into a single schema in one pass

## Path 1 Extraction Later

Path 1 public framework extraction should happen after Path 2 ontology, state transitions, lane boundaries, and artifact discipline stabilize under real operations. The extractable pieces are expected to be:

- the canonical state machine
- policy and gate contracts
- lane registry schema
- artifact metadata envelope
- audit and lineage primitives

The operational repo remains the proving ground. Path 1 should extract reusable contracts from Path 2, not replace Path 2 with premature framework packaging.
