# v0.2 Operator Source-Control Repair Plan

Target branch:

```text
release/v0.2-local-authoring-surface
```

## Repair Purpose

Repair the source-control completeness blocker that prevented a clean checkout from collecting:

```text
tests/test_operator_canonical_ledger_adapter.py
```

The blocker was missing committed runtime source for:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`

Focused verification then exposed the committed `signal_agent/operator/runtime.py` import closure:

- `signal_agent/operator/capture_routing_status.py`
- `signal_agent/operator/routing_queue_backlog.py`
- `signal_agent/operator/routing_lineage_drilldown.py`
- `signal_agent/content/lineage_status.py`

After imports were repaired, the committed operator adapter test exposed the registry configuration dependency:

- `config/operator/intents.yaml`
- `config/operator/tools.yaml`
- `config/operator/workflows.yaml`

## Source Origin

The source files were copied from the dirty main worktree:

```text
E:\signal_agent\signal_agent\operator
```

and:

```text
E:\signal_agent\signal_agent\content
```

and:

```text
E:\signal_agent\config\operator
```

The destination is the clean release worktree:

```text
C:\Users\mrcol\AppData\Local\Temp\signal_agent_release_v0_2_20260619150000526\signal_agent\operator
```

## Exact-Copy Hash Verification

| File | Dirty-main SHA-256 | Initial release-worktree SHA-256 after exact copy | Match |
| --- | --- | --- | --- |
| `signal_agent/operator/intent.py` | `35898e8c7955af36ff845cfdaa8cd2dbf17a6faefa16dd1c186af77b7147c663` | `35898e8c7955af36ff845cfdaa8cd2dbf17a6faefa16dd1c186af77b7147c663` | yes |
| `signal_agent/operator/planner.py` | `a80e45c5103bf10471379b9a1f4c8a807b729818e9db290b454c0f65ffc3dac9` | `a80e45c5103bf10471379b9a1f4c8a807b729818e9db290b454c0f65ffc3dac9` | yes |
| `signal_agent/operator/registry.py` | `5e66be71ed8c703e361b6aa42a9c9b5d01e905ee42f3b570a1e660388ba3adce` | `5e66be71ed8c703e361b6aa42a9c9b5d01e905ee42f3b570a1e660388ba3adce` | yes |
| `signal_agent/operator/capture_routing_status.py` | `791ab425c0108f564fcfc9313d73228a3e65dce91db7a0adc988990aa2b3b012` | `791ab425c0108f564fcfc9313d73228a3e65dce91db7a0adc988990aa2b3b012` | yes |
| `signal_agent/operator/routing_queue_backlog.py` | `d6d4ea9f0a3383acb80d540422ee49945d61d69b8fda97fe1b9f4f6a0b45cf32` | `d6d4ea9f0a3383acb80d540422ee49945d61d69b8fda97fe1b9f4f6a0b45cf32` | yes |
| `signal_agent/operator/routing_lineage_drilldown.py` | `33787e548eac62a298992721b10035e998dc8b6a5faf774f6f888ec84b53826a` | `33787e548eac62a298992721b10035e998dc8b6a5faf774f6f888ec84b53826a` | yes |
| `signal_agent/content/lineage_status.py` | `e9464d81dc006858d849e1c732c6ab8889c5f5676e64a8f9ee76383f28c12a6f` | `e9464d81dc006858d849e1c732c6ab8889c5f5676e64a8f9ee76383f28c12a6f` | yes |
| `config/operator/intents.yaml` | `468d5f8a452714f01482aa4451b10b02dbd30fd0a832a2ebd6536c34eab274d6` | `468d5f8a452714f01482aa4451b10b02dbd30fd0a832a2ebd6536c34eab274d6` | yes |
| `config/operator/tools.yaml` | `5bca3e8f119614524f4c403856ad839e6c39687f30c11e845e6afba43fe19815` | `5bca3e8f119614524f4c403856ad839e6c39687f30c11e845e6afba43fe19815` | yes |
| `config/operator/workflows.yaml` | `9be424e875b8d2d02ca165bee54261c616b93ea12f7eed5b9f6c2c3870b1746a` | `9be424e875b8d2d02ca165bee54261c616b93ea12f7eed5b9f6c2c3870b1746a` | yes |

## Commit-Readiness Normalization

The exact copied files matched their dirty-main source hashes. A subsequent all-files whitespace check found pre-existing whitespace in two exact-copied files:

- `signal_agent/operator/registry.py`
- `config/operator/tools.yaml`

The release worktree copy was normalized for commit readiness only:

- Removed two whitespace-only blank lines in `registry.py`.
- Removed one final blank line at EOF in `tools.yaml`.

Final normalized hashes:

| File | Final release-worktree SHA-256 |
| --- | --- |
| `signal_agent/operator/registry.py` | `dd9b9b34219d8977f81b5606a43aeac695f53999b78f38d6d9cb4707dcd46de5` |
| `config/operator/tools.yaml` | `fad4e29df1ac5cf4c73c100342b532331c851bfa66aee85ed675911cb5cdb475` |

This normalization does not change runtime behavior.

## Import Closure

Direct local imports:

- `intent.py` imports `.registry`.
- `planner.py` imports `.intent` and `.registry`.
- `registry.py` has no local operator imports.
- `runtime.py` imports `.capture_routing_status`, `.routing_queue_backlog`, and `.routing_lineage_drilldown` at module load.
- `capture_routing_status.py` has no local operator imports.
- `routing_queue_backlog.py` imports `.capture_routing_status` and `.registry`.
- `routing_lineage_drilldown.py` imports `.capture_routing_status`, `.registry`, `.routing_queue_backlog`, and `signal_agent.content.lineage_status`.
- `lineage_status.py` has no local project imports.
- `OperatorRegistry.load()` requires `config/operator/intents.yaml`, `config/operator/tools.yaml`, and `config/operator/workflows.yaml`.

External imports:

- `dataclasses`
- `pathlib`
- `typing`
- `re`
- `yaml`
- `datetime`
- `json`
- `app.hq.governance`

No additional untracked operator or content files are required for the import closure of the repaired modules.

## Files Added In Repair Scope

Runtime source:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`
- `signal_agent/operator/capture_routing_status.py`
- `signal_agent/operator/routing_queue_backlog.py`
- `signal_agent/operator/routing_lineage_drilldown.py`
- `signal_agent/content/lineage_status.py`

Registry configuration:

- `config/operator/intents.yaml`
- `config/operator/tools.yaml`
- `config/operator/workflows.yaml`

Focused regression test:

- `tests/test_operator_source_control_completeness.py`

Documentation:

- `docs/v0_2_planning/V0_2_OPERATOR_SOURCE_CONTROL_REPAIR_PLAN.md`

## Files Intentionally Not Copied

The repair does not copy unrelated untracked operator files, including:

- `signal_agent/operator/invariant_checker.py`
- `signal_agent/operator/response.py`

Those files may need separate audits for other workstreams, but they are not required to collect and run the committed operator canonical ledger adapter test.

The repair does not copy unrelated config, data, generated files, or release-site files.

## Boundary

This repair does not:

- Touch `data/`.
- Modify production ledgers.
- Add server behavior.
- Add network behavior.
- Add browser-backend submission.
- Modify static prototype UI files.
- Add production writes.
- Enable default production ledger writes.

## Verification Requirement

Before this repair is committed, verify:

- `python -m pytest tests/test_operator_canonical_ledger_adapter.py -q`
- `python -m pytest tests/test_operator_source_control_completeness.py -q`
- The complete clean-release verification suite.
- The clean branch's 6 tracked JSONL fingerprint remains unchanged before and after verification.
