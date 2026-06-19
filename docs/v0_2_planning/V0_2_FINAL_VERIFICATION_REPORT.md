# v0.2 Final Verification Report

Version target:

```text
v0.2-local-authoring-surface
```

## Verification Context

Phase 29 integrated the local command-router foundation into the Governed Authoring CLI.

Phase 30 documented the CLI integration status and boundary.

Current safe claim under verification:

```text
v0.2 exposes a local command-router foundation through the Governed Authoring CLI for covered explicit workspace paths.
```

## Verification Summary

All required Phase 31 verification commands passed.

Total documented test result:

```text
156 passed
```

Real CLI-router exercise result:

```text
5 CLI-router commands passed against an explicit temporary workspace outside the repo.
```

## Production JSONL Fingerprint

Fingerprint method:

```text
SHA-256 over concatenated bytes of sorted data/**/*.jsonl files.
```

Before verification:

```text
52 ba7d8cb8e7f12c7f5185069ba351d643d280e0b296b531139561cb69ad89c2d6
```

After verification:

```text
52 ba7d8cb8e7f12c7f5185069ba351d643d280e0b296b531139561cb69ad89c2d6
```

Result:

```text
Production JSONL fingerprint unchanged.
```

## Test Results

| Verification surface | Command | Result |
| --- | --- | --- |
| Router CLI tests | `python -m pytest tests/test_governed_authoring_command_router_cli.py -q` | 15 passed |
| Router foundation | `python -m pytest tests/test_governed_authoring_path_policy.py tests/test_governed_authoring_workspace.py tests/test_governed_authoring_command_router.py -q` | 39 passed |
| Existing local authoring proof paths | `python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py tests/test_governed_authoring_demo_bundle.py -q` | 31 passed |
| Bridge/backend | `python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q` | 29 passed |
| Existing integrations | `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q` | 23 passed |
| Formal governance | `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q` | 19 passed |

## CLI-Router Exercise

Temporary workspace:

```text
C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334
```

The workspace is outside the repo.

Commands run:

```bash
python -m signal_agent.governed_authoring.cli router validate-output-directory --workspace C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334
```

Result:

```text
result_code=0 status=validated classification=allowed_workspace_path
```

```bash
python -m signal_agent.governed_authoring.cli router verify-static-export --input E:\signal_agent\tests\fixtures\governed_authoring\static_export_valid_approved.json --workspace C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334 --output C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\results\phase31_valid_approved.result.json --canonical-ledger C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\ledgers\phase31_verify_static_export.canonical.jsonl --with-canonical-ledger
```

Result:

```text
result_code=0 status=completed output_status=approved review_status="Approved by backend review"
```

```bash
python -m signal_agent.governed_authoring.cli router run-demo-bundle --workspace C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334 --canonical-ledger C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\ledgers\phase31_demo_bundle.canonical.jsonl --with-canonical-ledger
```

Result:

```text
result_code=0 status=completed passed=true
```

```bash
python -m signal_agent.governed_authoring.cli router summarize-proof-output --workspace C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334 --summary C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\summaries\phase31_proof_output_summary.md
```

Result:

```text
result_code=0 status=summarized result_count=6
```

```bash
python -m signal_agent.governed_authoring.cli router inspect-result-packet --input C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\results\static_export_valid_approved.result.json --workspace C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334 --report C:\Users\mrcol\AppData\Local\Temp\governed_authoring_v0_2_phase31_20260619140715334\summaries\phase31_result_inspection.md
```

Result:

```text
result_code=0 status=inspected schema_version=governed_authoring.prototype_result.v1 output_status=approved
```

## Temporary Workspace Outputs

| File | Size |
| --- | ---: |
| `ledgers\phase31_demo_bundle.canonical.jsonl` | 26667 |
| `ledgers\phase31_verify_static_export.canonical.jsonl` | 5990 |
| `results\phase31_valid_approved.result.json` | 1062 |
| `results\static_export_blocking_tension.result.json` | 1081 |
| `results\static_export_generator_self_approval.result.json` | 891 |
| `results\static_export_missing_evidence.result.json` | 819 |
| `results\static_export_valid_approved.result.json` | 1062 |
| `results\static_export_valid_provisional.result.json` | 798 |
| `summaries\phase31_proof_output_summary.md` | 1184 |
| `summaries\phase31_result_inspection.md` | 151 |
| `summaries\proof_summary.md` | 1552 |

## Result Packet Compatibility

All produced result packets used:

```text
governed_authoring.prototype_result.v1
```

Observed packet outcomes:

| Result packet | Output status | Review status |
| --- | --- | --- |
| `phase31_valid_approved.result.json` | approved | Approved by backend review |
| `static_export_blocking_tension.result.json` | deferred | Deferred by backend review |
| `static_export_generator_self_approval.result.json` | rejected | Rejected by backend review |
| `static_export_missing_evidence.result.json` | rejected | Rejected by backend review |
| `static_export_valid_approved.result.json` | approved | Approved by backend review |
| `static_export_valid_provisional.result.json` | provisional | Provisional backend draft |

## Proof Summaries

Proof summaries/reports were produced inside the temporary workspace:

- `summaries\proof_summary.md`
- `summaries\phase31_proof_output_summary.md`
- `summaries\phase31_result_inspection.md`

## Ledger Boundary

Optional canonical ledger output was explicit-path only and confined to the temporary workspace:

| Ledger | Entries | Size |
| --- | ---: | ---: |
| `ledgers\phase31_verify_static_export.canonical.jsonl` | 1 | 5990 |
| `ledgers\phase31_demo_bundle.canonical.jsonl` | 5 | 26667 |

No default production canonical ledger write was enabled.

## Mutation Boundary

Phase 31 did not modify source/runtime files.

Source/runtime dirty-name fingerprint before and after the verification run matched:

```text
count=26 hash=579703029d8d778a2ca6a316bde38e428c20ef76db516a96daf5bc7b9828b49c
```

The workspace already contained unrelated dirty/quarantined files. Phase 31 treated those as out of scope.

Phase 31 did not add:

- Server code.
- HTTP endpoints.
- Websocket behavior.
- Network behavior.
- Browser-backend submission.
- Static prototype UI changes.
- Production authoring artifacts.
- Production writes.
- Default production canonical ledger writes.

## Release-Candidate Claim

The Phase 31 evidence supports this release-candidate claim:

```text
v0.2-local-authoring-surface provides a verified local CLI authoring surface over covered Governed Authoring proof paths, using explicit workspaces and fail-closed path validation.
```

Mandatory qualifiers:

- Local.
- Non-production.
- Covered paths only.
- Explicit workspace/output paths.
- No server.
- No browser-backend submission.
- No production writes.
- No default production ledger writes.

## Remaining Boundaries

Phase 31 does not prove:

- Production app readiness.
- Local server behavior.
- Backend-wired UI.
- Browser submission.
- Production authoring writes.
- Repo-wide governance.
- Complete IBVM proof.

## Recommended Phase 32

Phase 32 should prepare the v0.2 release note, tag preparation, tag, push, and GitHub prerelease only after this verification report is committed.
