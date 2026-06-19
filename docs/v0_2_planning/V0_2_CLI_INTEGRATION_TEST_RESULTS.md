# v0.2 CLI Integration Test Results

Version target:

```text
v0.2-local-authoring-surface
```

## Summary

Phase 29 verification covered the command-router CLI integration plus prior v0.2 and v0.1 proof surfaces.

Total:

```text
156 passing tests
```

Production JSONL fingerprint before and after verification:

```text
52 cc209a4d06275a3174635f32e631e0ec6f728f9bf2aae4596dec93e75e21ba34
```

Result:

```text
Production JSONL fingerprint unchanged.
```

## Test Commands

| Test command | Result |
| --- | --- |
| `python -m pytest tests/test_governed_authoring_command_router_cli.py -q` | 15 passed |
| `python -m pytest tests/test_governed_authoring_path_policy.py tests/test_governed_authoring_workspace.py tests/test_governed_authoring_command_router.py -q` | 39 passed |
| `python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_demo_bundle.py -q` | 31 passed |
| `python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q` | 29 passed |
| `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q` | 23 passed |
| `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q` | 19 passed |

## Covered CLI Behavior

The command-router CLI tests cover:

- Router command dispatch through `python -m signal_agent.governed_authoring.cli router`.
- Static export verification through explicit workspace paths.
- Demo bundle execution through explicit workspace paths.
- Result packet inspection.
- Output directory validation.
- Proof output summarization.
- JSON stdout for successful command results.
- Structured JSON stderr for failed command results.
- Fail-closed rejection of forbidden paths.
- No default ledger writes.

## Non-Mutation Evidence

Verification recorded:

- Production JSONL fingerprint unchanged.
- No server behavior added.
- No browser-backend submission added.
- No static prototype UI changes.
- No production authoring writes added.
- No default production canonical ledger writes added.

The workspace still contains unrelated dirty/quarantined files, including `data/`, but Phase 29 verification did not make them part of the CLI integration proof claim.
