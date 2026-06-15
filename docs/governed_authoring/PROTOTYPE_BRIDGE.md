# Governed Authoring Prototype Bridge

This document describes the minimal bridge added in Phase 7 by commit `51e32a1`.

The bridge lives in `signal_agent/governed_authoring/prototype_bridge.py`. It is a conversion layer only. It does not rewrite the static prototype UI, add a server, write production authoring artifacts, or enable production ledger writes by default.

## Purpose

The static prototype in `products/governed_authoring_studio/prototype_v1a/` remains a local workflow demonstration. Phase 7 adds a backend-compatible data bridge so prototype/localStorage-style packets can be converted into the backend Governed Authoring proof path and backend output manifests can be converted back into prototype-readable result packets.

The bridge supports this flow:

```text
prototype/localStorage-style packet
-> backend source_packet
-> GovernedAuthoringRuntime
-> backend output_manifest
-> prototype-readable result packet
```

## What The Bridge Converts

The bridge converts:

- Prototype/localStorage-style packets into backend `source_packet` dictionaries.
- Backend `output_manifest` objects or dictionaries into prototype-readable result packets.
- Full backend run results into bridge result packets with both backend and prototype-facing views.

Primary functions:

- `prototype_to_source_packet(packet)`
- `bridge_prototype_packet(packet)`
- `output_manifest_to_prototype_result(output_manifest)`
- `backend_result_to_prototype_result(result)`
- `run_prototype_bridge(packet, canonical_ledger_path=None, strict=False)`

## What Survives Conversion

The Phase 7 tests prove preservation of:

- Evidence references.
- Unresolved tensions.
- Review status and review authority fields.
- Provisional, rejected, deferred, and approved output status.
- Generator/model/self-approval flags.
- Backend decision reason and output manifest identifiers.

## What Is Now Proven

The repository now proves that:

- A prototype-style packet can be converted into a backend-compatible source packet.
- A backend output manifest can be converted into a prototype-readable result packet.
- Publication-ready prototype packets without evidence can be flagged by the bridge and rejected by the backend.
- Generator/model self-approval can be flagged by the bridge and rejected by the backend.
- The backend proof path can run from a prototype-compatible packet without a server or UI rewrite.

Proof files:

- `signal_agent/governed_authoring/prototype_bridge.py`
- `tests/test_governed_authoring_prototype_bridge.py`
- `signal_agent/governed_authoring/runtime.py`
- `tests/test_governed_authoring_backend.py`

## What Is Not Proven

Do not claim:

- The static prototype UI is wired to the backend.
- The static prototype is a production app.
- A server or hosted app surface exists.
- Production authoring artifacts are written.
- Production canonical authoring ledger writes are enabled by default.
- All authoring outputs are governed.
- Repo-wide promotion governance is complete.

## Current Boundary

Safe wording:

"A minimal bridge now aligns static prototype packet shapes with the backend Governed Authoring proof path. The static prototype remains a non-production UI surface."

Unsafe wording:

"The app is wired."

"The full UI is backend-governed."

"Governed Authoring is production-ready."
