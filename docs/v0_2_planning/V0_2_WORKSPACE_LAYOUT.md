# v0.2 Workspace Layout

Version target:

```text
v0.2-local-authoring-surface
```

## Proposed Layout

Future command-router outputs should use this caller-selected local workspace layout:

```text
<workspace>/
  inputs/
  results/
  summaries/
  ledgers/
  validation/
  drafts/
  metadata/
```

The layout is a contract, not an implementation.

## inputs/

Stores input packet copies or references.

Examples:

- `static_export_valid_approved.json`
- `source_packet.json`
- `fixture_reference.json`

Rules:

- Inputs must be explicit.
- Generated output cannot be used as its own approval authority.

## results/

Stores static-import-compatible result packets.

Examples:

- `static_export_valid_approved.result.json`
- `authoring_result.json`

Rules:

- Result packets stay local.
- Result packets are not production artifacts.

## summaries/

Stores proof and workflow summaries.

Examples:

- `proof_summary.md`
- `workflow_summary.md`
- `workflow_summary.json`

Rules:

- Summaries describe local proof/workflow output only.
- Summaries do not promote artifacts.

## ledgers/

Stores optional local canonical ledger JSONL.

Examples:

- `canonical_governed_authoring.jsonl`

Rules:

- Ledger writes are disabled by default.
- Ledger writes require explicit configuration.
- Ledger files must stay outside repo `data/`.

## validation/

Stores validation and error reports.

Examples:

- `validation_report.json`
- `validation_report.md`
- `router_error.json`

Rules:

- Validation reports may describe failures.
- Validation reports must not hide governance rejections.

## drafts/

Stores local draft outputs.

Examples:

- `draft.md`
- `draft.json`

Rules:

- Drafts are local and provisional.
- Drafts are not approved publications.
- Drafts are not production authoring artifacts.

## metadata/

Stores run metadata and fingerprints.

Examples:

- `run_metadata.json`
- `command_metadata.json`
- `fingerprints.json`

Rules:

- Metadata may record command name, paths, and statuses.
- Metadata does not create canonical state transitions.

## Forbidden Layouts

Forbidden workspace roots:

- `data/`
- `data/outputs/`
- `data/operator/`
- `data/claims/`
- Production ledger paths.
- Production authoring artifact paths.

Forbidden behavior:

- Parent traversal outside approved workspace.
- Implicit output directories.
- Overwrites without explicit policy.
- Hidden background state.
