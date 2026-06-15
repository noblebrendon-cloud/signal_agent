# Next Integration Plan

This plan starts from the proof status after commit `c2a993c`.

## Recommended Next Target

Recommended Phase 7:

```text
Minimal static prototype bridge to the Governed Authoring backend proof path.
```

Goal:

- Let the existing static prototype call or invoke the backend proof path for one controlled source-packet-to-output route.
- Do not rewrite the UI.
- Do not add a broad app/server surface.
- Do not create production authoring artifact writes yet.

Why this is the strongest next target:

- Governed Authoring now has backend proof, but the prototype UI is still disconnected.
- A minimal bridge closes the next most visible proof gap without broadening scope.
- It can preserve the existing UI as a workflow shell while proving one backend-backed path.

## Minimal Bridge Scope

The bridge should cover one path:

```text
prototype source packet
-> backend GovernedAuthoringRuntime
-> output manifest
-> optional temp/local canonical ledger path
-> UI displays backend decision and manifest status
```

Required constraints:

- Keep existing static UI structure.
- Add only the minimal call boundary needed for one path.
- Use temp or explicitly configured ledger paths during tests.
- Do not write production JSONL ledgers in tests.
- Do not add broad authentication, routing, publishing, or server features.

Recommended tests:

- UI bridge can submit a valid source packet to backend.
- UI bridge displays `provisional`, `rejected`, `deferred`, and `approved` output statuses from backend fixtures or mocked backend responses.
- UI bridge does not mutate production ledgers.
- Existing Phase 1-5 tests still pass.

## Alternative Next Target

If inspection shows the prototype bridge would require too much app/server surface, use this safer alternative:

```text
Governed shell canonical ledger integration.
```

Reason:

- Governed shell already has strong policy and hash-chain evidence.
- It remains subsystem-specific and not yet linked to canonical governed-transition entries.
- Adding an adapter could strengthen the proof chain without UI risk.

## Still Deferred

Do not tackle these until the next bounded path is proven:

- Full production Governed Authoring app.
- Broad server/API surface.
- Repo-wide mutation gate.
- Historical ledger migration.
- Universal same-input/same-decision proof.
- Full IBVM proof across every path.

## Phase 7 Acceptance Criteria

For the recommended prototype bridge, accept only if:

- Existing prototype UI is minimally bridged, not rewritten.
- Backend response comes from `signal_agent/governed_authoring`.
- Tests prove the bridge does not bypass backend decisions.
- Production JSONL ledgers remain unchanged during tests.
- Documentation still says "covered path", not "production app".
