# v0.2 Final Verification Addendum

Target branch:

```text
release/v0.2-local-authoring-surface
```

## Purpose

This addendum updates the final v0.2 verification result after the operator source-control repair commit:

```text
745745f Restore operator runtime source-control closure
```

## Updated Test Total

Release-ready verification figure:

```text
158 passing tests
```

This replaces the earlier 156-test release-ready figure because the repair added:

```text
tests/test_operator_source_control_completeness.py
```

with 2 passing tests.

## Verification Commands

| Verification surface | Command | Result |
| --- | --- | --- |
| Focused operator repair | `python -m pytest tests/test_operator_canonical_ledger_adapter.py tests/test_operator_source_control_completeness.py -q` | 8 passed |
| Router CLI tests | `python -m pytest tests/test_governed_authoring_command_router_cli.py -q` | 15 passed |
| Router foundation | `python -m pytest tests/test_governed_authoring_path_policy.py tests/test_governed_authoring_workspace.py tests/test_governed_authoring_command_router.py -q` | 39 passed |
| Existing local authoring proof paths | `python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_demo_bundle.py -q` | 31 passed |
| Bridge/backend | `python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q` | 29 passed |
| Existing integrations | `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q` | 23 passed |
| Formal governance | `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q` | 19 passed |

The raw command total includes the operator adapter tests twice because the focused repair command and the existing integration command both include that surface.

The unique release verification surface is:

```text
158 passing tests
```

## JSONL Baseline

Clean release branch tracked JSONL baseline:

```text
6 0b01cec041f2e54b4dcc1467f89019bbcd5ab5eb0a5a4e6d34ff02e426c9da0d
```

This is the baseline the tagged release should rely on.

Dirty-main operational baseline:

```text
52 JSONL files
```

The dirty-main baseline includes 46 ignored operational JSONLs and is not equivalent to the clean release branch baseline.

## Release Evidence Rule

The v0.2 tagged release should rely only on the clean-branch tracked JSONL baseline.

Do not present the 6-file release branch baseline as the same evidence as the dirty-main 52-file operational snapshot.

## Safe Claim

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces, fail-closed path validation, and a source-control-complete operator dependency closure.
```

Required qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.
