# v0.2 Command Router Verification Report

Version target:

```text
v0.2-local-authoring-surface
```

## Verification Context

Phase 26 implemented the local command-router runtime foundation.

Phase 27 documented the Phase 26 boundary and test results.

Current safe claim:

```text
v0.2 has a local command-router foundation with fail-closed path classification for covered explicit local output paths.
```

## Verification Summary

All Phase 28 verification commands passed.

Total unique requested surface:

```text
141 passing tests
```

Production JSONL fingerprint before verification:

```text
52 cc209a4d06275a3174635f32e631e0ec6f728f9bf2aae4596dec93e75e21ba34
```

Production JSONL fingerprint after verification:

```text
52 cc209a4d06275a3174635f32e631e0ec6f728f9bf2aae4596dec93e75e21ba34
```

Result:

```text
Production JSONL fingerprint unchanged.
```

## Test Results

| Test command | Result |
| --- | --- |
| `python -m pytest tests/test_governed_authoring_path_policy.py -q` | 11 passed |
| `python -m pytest tests/test_governed_authoring_workspace.py -q` | 11 passed |
| `python -m pytest tests/test_governed_authoring_command_router.py -q` | 17 passed |
| `python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_demo_bundle.py -q` | 31 passed |
| `python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q` | 29 passed |
| `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q` | 23 passed |
| `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q` | 19 passed |

## Mutation Boundary

Phase 28 verification did not change source/runtime files.

It did not modify:

- Production ledgers.
- Repo `data/`.
- Static prototype UI files.
- Server or network behavior.
- Browser-backend submission behavior.
- Production authoring artifact paths.
- Default production canonical ledger behavior.

The workspace still contains unrelated dirty/quarantined files, including `data/`, but Phase 28 did not touch them.

## Verified Phase 26 Behavior

The verification re-confirmed:

- Fail-closed path classification.
- Workspace validation.
- Explicit output validation.
- Optional explicit ledger path validation.
- Overwrite denial by default.
- Router support for covered commands:
  - `verify-static-export`
  - `run-demo-bundle`
  - `inspect-result-packet`
  - `validate-output-directory`
  - `summarize-proof-output`
- No default ledger write.
- No production JSONL fingerprint change.
- No server/network behavior.
- No static prototype UI changes.

## Remaining Gaps

Phase 28 verification does not prove:

- Existing CLI exposure of the command-router foundation.
- Local server behavior.
- Browser-backend submission.
- Backend-wired UI.
- Production authoring writes.
- Production identity or authentication.
- Repo-wide governance.
- Complete IBVM proof.
