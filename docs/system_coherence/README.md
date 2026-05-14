# System Coherence Documentation Layer

**Status**: Stage 1 — documentation only, evidence-mapped, no runtime changes
**Generated**: 2026-05-13
**Authority**: This layer is descriptive. It does not modify runtime behavior, governance invariants, or transition gate logic.

---

## Purpose

This directory provides a structural map of the Signal Agent system as it exists today, organized for operator understanding, external communication, and convergence planning.

Every claim in these documents is one of:

| Classification | Meaning |
|---|---|
| **Implemented** | Live code, ledgers, tests, or configs exist in the repo and are exercised |
| **Emerging** | Code or plans exist but are untracked, partially wired, or under active development |
| **Future-facing** | Described in governance specs or planning docs but no runtime enforcement exists |

---

## Documents

| Document | Scope |
|---|---|
| [SIGNAL_AGENT_SYSTEM_MAP.md](SIGNAL_AGENT_SYSTEM_MAP.md) | Full module map — every canonical, legacy, and experimental surface with evidence links |
| [SPINE_ARCHITECTURE.md](SPINE_ARCHITECTURE.md) | Content spine taxonomy, platform groupings, and spine observability foundations |
| [GOVERNED_CONTINUITY_ENGINE.md](GOVERNED_CONTINUITY_ENGINE.md) | How the system maintains operational continuity — transition gate, lifecycle, witness node |
| [HQ_OBSERVABILITY_LAYER.md](HQ_OBSERVABILITY_LAYER.md) | Capture → curation → routing → publication pipeline and observability surfaces |

---

## Relationship to Existing Docs

This layer does not replace:
- `GOVERNANCE_KERNEL.md` — normative spec for runtime invariants
- `ARCHITECTURE.md` — canonical package root declaration
- `docs/operator/OPERATOR_INDEX.md` — primary operator reference
- `docs/publications/deterministic_governance/` — public proof bundle

It synthesizes and cross-references them into a navigable coherence layer.

---

## Rules

1. Do not invent claims. Every implementation reference must trace to a real file.
2. Mark uncertain boundaries explicitly.
3. Update these docs when implementation changes — they are living documents.
4. Do not treat this layer as governance authority. `GOVERNANCE_KERNEL.md` and `config/state_machine.yaml` remain normative.
