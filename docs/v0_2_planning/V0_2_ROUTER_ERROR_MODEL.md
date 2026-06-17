# v0.2 Router Error Model

Version target:

```text
v0.2-local-authoring-surface
```

## Purpose

This document defines structured errors for a future local command router. It is a design artifact only and does not implement runtime behavior.

## Error Shape

Future router errors should include:

- `code`
- `category`
- `message`
- `path`
- `command`
- `recoverable`
- `safe_to_retry`

## Error Categories

| Code | Category | Meaning |
| --- | --- | --- |
| `MISSING_INPUT` | input | Required input file or argument is missing. |
| `INVALID_JSON` | input | Input file is not valid JSON. |
| `UNSUPPORTED_PACKET_SHAPE` | input | Packet shape is not supported by the command. |
| `FORBIDDEN_OUTPUT_PATH` | path | Output path is under repo `data/` or another forbidden path. |
| `AMBIGUOUS_PATH` | path | Path classification is ambiguous and must fail closed. |
| `ATTEMPTED_PRODUCTION_WRITE` | path | Command attempted to write to production-like location. |
| `LEDGER_PATH_REQUIRED` | ledger | Ledger output was requested without explicit safe path. |
| `LEDGER_PATH_FORBIDDEN` | ledger | Ledger path is under repo `data/` or production path. |
| `SELF_CERTIFICATION_ATTEMPT` | governance | Generated/model output attempted to certify itself. |
| `BLOCKING_UNRESOLVED_TENSION` | governance | Blocking unresolved tension prevents approval. |
| `MISSING_EVIDENCE` | governance | Approval-ready output lacks required evidence. |
| `DEMO_EXPECTATION_MISMATCH` | verification | Demo fixture output differs from expected result. |

## Required Error Behavior

Errors must:

- Fail before writing when path safety is uncertain.
- Preserve existing files.
- Avoid ledger writes on failed validation.
- Return nonzero result codes.
- Avoid hiding governance failures.

## Specific Errors

### Missing Input

Trigger:

- Required file path does not exist.
- Required command argument is absent.

Expected result code:

- `2`

### Invalid JSON

Trigger:

- File exists but cannot be parsed as JSON.

Expected result code:

- `2`

### Unsupported Packet Shape

Trigger:

- JSON is valid but not a supported static export, source packet, or result packet.

Expected result code:

- `2` or `6`

### Forbidden Output Path

Trigger:

- Output path is inside repo `data/`.
- Output path is a production ledger or artifact path.

Expected result code:

- `3`

### Attempted Production Write

Trigger:

- Any command attempts to write to a production-like location.

Expected result code:

- `3`

### Ledger Path Missing

Trigger:

- Ledger write is requested but no explicit ledger path is supplied.

Expected result code:

- `3`

### Self-Certification Attempt

Trigger:

- Generated/model output attempts to provide its own approval authority.

Expected result code:

- `4`

### Blocking Unresolved Tension

Trigger:

- A blocking unresolved tension exists for approval-ready output.

Expected result code:

- `4`

### Missing Evidence

Trigger:

- Approval-ready output has missing evidence refs.

Expected result code:

- `4`

## Non-Goals

This model does not define production incident handling, hosted service errors, authentication errors, or repo-wide governance failures.
