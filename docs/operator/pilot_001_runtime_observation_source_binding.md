# Pilot 001 Runtime Observation Source Binding

## 1. Purpose

Pilot 001 proved that a clean code worktree is not the same thing as the live runtime state source. The self-observation package was present on `main`, but the clean Pilot worktree did not contain the untracked operational JSONL ledgers under `data/state/` and `data/operator/runs/`, so the report command correctly exited without writing a misleading clean report.

This document designs a planning-only source-binding extension for self-observation:

```text
clean code root
+ explicit approved read-only observation source root
-> deterministic self-observation report under the code root
```

The purpose is to let an operator analyze real runtime activity from a clean code checkout without copying runtime ledgers, mutating canonical runtime state, or letting analytics output become authority.

## 2. Root Distinctions

`code root` is the clean repository checkout that provides the analytics code, tests, docs, and report output boundary. In the proposed Pilot 001 model this is the value of `--repo-root`.

`observation source root` is the approved live runtime workspace or exported read-only mount that contains operational ledgers. It is the value of the proposed `--observation-root`.

`report output root` is the analytics output area under the code root. For production CLI use, report files should resolve under:

```text
<repo-root>/data/analytics/
```

`canonical runtime state` is the runtime ledger area under the observation source root, especially:

```text
<observation-root>/data/state/
<observation-root>/data/operator/runs/
```

The observation source root is read-only input. It is never an output root.

## 3. Proposed CLI Contract

The future CLI should support explicit source binding:

```powershell
python -m signal_agent.analytics.self_observation `
  --repo-root <clean-code-root> `
  --observation-root <live-runtime-root> `
  --json-output data/analytics/self_observation_report.json `
  --markdown-output data/analytics/self_observation_report.md
```

If `--observation-root` is omitted, the existing single-root behavior remains valid:

```text
observation-root := repo-root
```

This preserves current local and test usage where code and runtime sample ledgers live under the same temporary root.

## 4. Allowed Read Paths

When `--observation-root` is provided, self-observation may read only these relative paths from that root:

```text
data/state/transition_gate_events.jsonl
data/state/event_log.jsonl
data/state/artifact_registry.jsonl
data/state/provider_events.jsonl
data/operator/runs/operator_runs.jsonl
data/state/inference_cache_registry.jsonl
```

The implementation should keep the existing source names:

```text
transition_events
event_log
artifact_registry
provider_events
operator_runs
inference_cache_registry
```

No recursive scanning is included in the smallest slice. No arbitrary source paths are accepted.

## 5. Allowed Write Paths

Report outputs should be resolved relative to `--repo-root`, not `--observation-root`.

For production CLI use, allowed report outputs should resolve at or under:

```text
<repo-root>/data/analytics/
```

The future implementation should reject output paths under:

```text
<repo-root>/data/state/
<repo-root>/config/
<repo-root>/governance/
<repo-root>/constraints/
<repo-root>/formal_governance/
<repo-root>/signal_agent/
<repo-root>/app/
<observation-root>/data/state/
<observation-root>/data/operator/runs/
```

The report writer should not write into the observation source root.

## 6. Source-Binding Provenance

The report schema should remain backward compatible with `self_observation_report.v1`. Additive provenance fields may be introduced without removing existing fields.

Minimum provenance should include:

```text
observation_source:
  mode: single_root | explicit_observation_root
  observation_root: normalized string path
  observation_source_identifier: deterministic identifier
  read_only: true
  allowed_relative_paths:
    - data/state/transition_gate_events.jsonl
    - data/state/event_log.jsonl
    - data/state/artifact_registry.jsonl
    - data/state/provider_events.jsonl
    - data/operator/runs/operator_runs.jsonl
    - data/state/inference_cache_registry.jsonl
```

Each `source_files` entry should continue to preserve:

```text
relative_source_path
resolved_source_path
exists
sha256
total_line_count
parsed_line_count
malformed_line_count
malformed_lines
rows_in_scope
```

The existing report already records source file hashes, parsed counts, malformed counts, and schema version. The source-binding slice should add explicit relative paths and an explicit read-only statement.

## 7. Path-Guard Rules

Path handling should be deterministic and restrictive:

- Resolve `--repo-root` and `--observation-root` before validation.
- Reject `--observation-root` if it resolves inside the report output directory.
- Reject report outputs that resolve under the observation source root.
- Reject report outputs that resolve under `data/state`, `config`, `governance`, `constraints`, `formal_governance`, `signal_agent`, or `app`.
- Reject `..` traversal after path resolution if the final path escapes the allowed output root.
- Reject arbitrary source file paths. Only the fixed source list is readable.
- If symlinks are present, validate the final resolved path. A symlink must not let a source path escape the allowed observation source subtrees or let an output path escape `<repo-root>/data/analytics/`.

Existing `report_builder.py` permits absolute non-repo output paths. The source-binding implementation should decide whether to keep that in legacy single-root programmatic use while making the production CLI stricter for bound observation mode. The Pilot 001 operational CLI should prefer the stricter rule.

## 8. Determinism Requirements

The same source files and same CLI arguments must produce byte-stable JSON and Markdown output.

Required deterministic behavior:

- No wall-clock timestamp by default.
- Normalize root and source paths consistently before serializing.
- Sort JSON keys as the existing writer does.
- Preserve malformed-line hashes instead of line contents.
- Preserve source file hashes.
- Preserve parsed and malformed line counts.
- Preserve the order of source names deterministically.
- Use relative source paths for stable report comparison where absolute roots differ, while keeping resolved paths available when needed for operator audit.

## 9. Failure Behavior

Missing optional source files should remain warnings.

Missing or empty primary inputs should keep the current safe behavior:

```text
primary_inputs_missing_or_empty
```

and the CLI should not write a report.

Malformed JSONL should remain nonfatal:

- skip malformed rows
- count them
- include line number and line hash

Unreadable source paths should become report warnings when possible, or a nonzero CLI exit if the reader cannot safely determine source metadata.

Reject and exit nonzero before writing if:

- `--observation-root` is missing when explicitly required by the pilot command wrapper
- `--observation-root` resolves to a non-directory
- `--observation-root` equals the output root
- an output path resolves under observation-root `data/state`
- an output path resolves under canonical code or policy directories
- path traversal or symlink resolution escapes an allowed root

## 10. Backward Compatibility

Existing single-root behavior remains valid:

```powershell
python -m signal_agent.analytics.self_observation --repo-root .
```

In this mode, source files are still read from:

```text
<repo-root>/data/state/
<repo-root>/data/operator/runs/
```

Existing report consumers should remain compatible because:

- `schema_version` remains `self_observation_report.v1`
- existing top-level fields remain present
- `source_files`, `metrics`, `subsystem_candidates`, `recommendations`, and `warnings` remain present
- new source-binding fields are additive

## 11. Smallest Safe Implementation Slice

The smallest safe slice is:

1. Add an optional `observation_root` argument to `build_self_observation_report`.
2. Add a `--observation-root` CLI flag.
3. Read fixed source paths from `observation_root` instead of `repo_root` when provided.
4. Keep report outputs resolved under `repo_root`.
5. Add source-binding provenance to the report.
6. Add path guards that reject output paths under the observation root and canonical state paths.
7. Add tests with separate temporary code and observation roots.

This slice should not create review artifacts, decision events, intake candidates, governed proposals, schedulers, dashboards, or any state mutation.

## 12. Likely Files Touched

Likely implementation files:

```text
signal_agent/analytics/self_observation.py
signal_agent/analytics/report_builder.py
tests/test_self_observation.py
tests/test_self_observation_cli.py
```

Possible package export update if the public function signature is exposed:

```text
signal_agent/analytics/__init__.py
```

No transition gate, policy, workflow, review-loop, resolver, or proposal-intake code should be required for this slice.

## 13. Required Tests

Required tests:

- isolated temporary code root plus separate temporary observation root
- report reads from observation root and writes under code root `data/analytics`
- observation source files are unchanged before and after the run
- no files are written under observation root
- canonical output path under code root `data/state` is rejected
- output path under observation root `data/state` is rejected
- path traversal outside `<repo-root>/data/analytics` is rejected in bound CLI mode
- symlink escape is rejected when symlink handling is supported by the test environment
- same source files and same arguments yield deterministic JSON and Markdown
- malformed JSONL is still counted and represented by line number plus line hash
- missing optional sources remain warnings
- missing or empty primary inputs still exits nonzero without writing
- legacy single-root mode still works
- existing report consumers still see the original top-level fields

## 14. Stop Conditions

Stop implementation if any future change requires:

- copying runtime ledgers into the clean code worktree
- writing under the observation root
- writing under `data/state`
- changing transition gate behavior
- changing policy behavior
- changing workflow behavior
- creating review artifacts or decision events
- creating intake candidates or governed proposals
- adding dashboards, queues, schedulers, integrations, or autonomous actions
- accepting arbitrary source paths
- weakening deterministic report output

## 15. Governance Connection

The observation-source binding remains analytics-only. It gives the observer a read-only source of operational evidence, but it does not convert analytics output into authority.

Any later human review still follows the existing chain:

```text
self-observation report
-> subsystem candidate
-> review artifact
-> human decision event
-> read-only resolved status
-> noncanonical intake candidate
-> separate governed proposal process
```

The source-binding layer only improves how the first report is produced. It does not authorize changes to runtime state, policy, workflows, transition gates, or implementation behavior.
