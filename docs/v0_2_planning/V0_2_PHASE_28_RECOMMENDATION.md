# v0.2 Phase 28 Recommendation

Version target:

```text
v0.2-local-authoring-surface
```

## Recommendation

Phase 28 should be:

```text
Command-router verification report and CLI integration decision.
```

Do not jump directly to local server work.

## Purpose

Phase 28 should decide whether to expose the command-router foundation through the existing CLI or keep it as an internal runtime foundation for one more verification phase.

The decision should preserve the Phase 26 boundary:

- Local.
- Non-production.
- Covered paths only.
- Explicit output paths only.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Inputs To Review

Phase 28 should review:

- `signal_agent/governed_authoring/path_policy.py`
- `signal_agent/governed_authoring/workspace.py`
- `signal_agent/governed_authoring/command_router.py`
- `tests/test_governed_authoring_path_policy.py`
- `tests/test_governed_authoring_workspace.py`
- `tests/test_governed_authoring_command_router.py`
- Existing offline CLI behavior.
- Existing offline harness behavior.
- Existing demo bundle behavior.

## CLI Integration Decision Options

| Option | Proof value | Boundary risk | Recommendation |
| --- | --- | --- | --- |
| Keep router internal for one more verification phase | Lowest risk; gives more time to inspect command contracts. | Low. | Acceptable if more audit is desired. |
| Expose router through existing CLI as local-only subcommands | Improves usability while preserving local explicit-path boundary. | Medium if CLI flags are strict. | Candidate next implementation after Phase 28 decision. |
| Add a separate router CLI module | Clear separation from existing CLI. | Medium because another entrypoint must be documented and tested. | Consider only if existing CLI integration would blur boundaries. |
| Add local server | Not needed for the next step. | High. | Defer. |
| Add browser submission | Not needed for the next step. | High. | Defer. |

## Required Verification Before CLI Exposure

Before exposing the router through CLI, require:

- Re-run Phase 26 router tests.
- Confirm no production JSONL fingerprint changes.
- Confirm no repo `data/` writes.
- Confirm no static prototype UI changes.
- Confirm no server/network behavior.
- Confirm no default ledger write.
- Confirm explicit ledger path behavior.
- Confirm overwrite denial by default.
- Confirm clear CLI error codes and messages.

## Phase 28 Output

Phase 28 should produce a documentation-only decision report unless explicitly approved otherwise.

Recommended files:

- `docs/v0_2_planning/V0_2_COMMAND_ROUTER_VERIFICATION_REPORT.md`
- `docs/v0_2_planning/V0_2_CLI_INTEGRATION_DECISION.md`
- `docs/v0_2_planning/V0_2_PHASE_29_RECOMMENDATION.md`

## Forbidden Phase 28 Scope

Phase 28 should not add:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Browser-backend submission.
- Static prototype UI wiring.
- Production authoring writes.
- Default production canonical ledger writes.
- Repo-wide governance claims.

## Safe Phase 28 Goal

Use:

```text
Decide whether the local command-router foundation should remain internal or be exposed through explicit local CLI commands.
```

Do not use:

```text
Make v0.2 a local server or backend-wired UI.
```
