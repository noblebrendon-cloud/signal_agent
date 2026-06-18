# v0.2 Command Router Test Results

Version target:

```text
v0.2-local-authoring-surface
```

## Test Summary

Phase 26 test results:

| Test surface | Result |
| --- | ---: |
| Path policy tests | 11 passed |
| Workspace tests | 11 passed |
| Command router tests | 17 passed |
| Offline CLI, harness, and demo bundle | 31 passed |
| Static export/import, prototype bridge, and backend | 29 passed |
| Claim, canonical ledger, HQ promotion, and operator integrations | 23 passed |
| Formal governance proof pack | 19 passed |

Total unique requested surface:

```text
141 passing tests
```

## Commands Represented

The Phase 26 verification covered:

```bash
python -m pytest tests/test_governed_authoring_path_policy.py -q
python -m pytest tests/test_governed_authoring_workspace.py -q
python -m pytest tests/test_governed_authoring_command_router.py -q
python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_demo_bundle.py -q
python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q
python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q
python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q
```

## Tested Behavior

The new Phase 26 tests prove:

- Allowed temp workspace is accepted.
- Allowed explicit workspace outside repo `data/` is accepted.
- Result path under workspace `results/` is accepted.
- Summary path under workspace `summaries/` is accepted.
- Validation path under workspace `validation/` is accepted.
- Metadata path under workspace `metadata/` is accepted.
- Draft path under workspace `drafts/` is accepted.
- Explicit ledger path under workspace `ledgers/` is accepted.
- Repo `data/` workspace is rejected.
- Repo `data/` result path is rejected.
- Production ledger path is rejected.
- Implicit ledger path is rejected when ledger output is requested.
- Parent traversal outside workspace is rejected.
- Ambiguous and unknown paths fail closed.
- Overwrite attempts are rejected by default.
- `verify-static-export` routes a fixture to a static-import-compatible result inside a temp workspace.
- `run-demo-bundle` routes outputs into a temp workspace only.
- Optional ledger writes only to an explicit workspace `ledgers/` path.
- No default ledger write occurs.
- Production JSONL fingerprint remains unchanged.
- No server/network behavior is introduced.
- No production authoring artifact writes are introduced.

## Mutation Boundary

Production JSONL fingerprint before and after matched:

```text
52 cc209a4d06275a3174635f32e631e0ec6f728f9bf2aae4596dec93e75e21ba34
```

No static prototype UI files changed.

No server, network, browser submission, production authoring write, or default production ledger behavior was added.

## Remaining Test Gaps

Still not proven:

- CLI exposure of the command-router foundation.
- Local server behavior.
- Browser-backend submission.
- Production authoring artifact writes.
- Production identity or authentication.
- Repo-wide governance.
- Complete IBVM proof.
