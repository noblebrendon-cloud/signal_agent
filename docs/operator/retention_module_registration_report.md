# Retention Module Registration Report

## Summary

The retention subsystem was registered in the repo’s live module registry at `data/state/module_artifacts.jsonl` and surfaced in `docs/operator/module_artifact_index.md`.

It was registered as **one module**:

- `retention`

## Why One Module

One record is the smallest shape that matches the repo’s current module-artifact conventions. The retention package is a cohesive governed capability with one primary authority boundary:

- append-only retention ledgers,
- reconciliation,
- local dispatch gating,
- deterministic queue projection,
- local sender preview validation,
- and explicit operator authorization.

Splitting it now into `retention_identity`, `retention_reconciliation`, `retention_dispatch_gate`, `retention_send_queue`, `retention_sender_contract`, and `retention_authorization` would over-fragment a subsystem that still behaves as one internal governed spine and does not yet admit a real external sender boundary.

## Where Retention Was Registered

- Live registry:
  - `data/state/module_artifacts.jsonl`
- Operator index:
  - `docs/operator/module_artifact_index.md`

## Public Interfaces Declared

The registered `public_interface` matches the package-level governed surface:

- `build_contact_seed_event`
- `build_contact_snapshot`
- `authorize_send_preview`
- `evaluate_dispatch_ready`
- `evaluate_transition`
- `load_latest_contact_snapshot`
- `plan_dispatch`
- `project_send_queue`
- `preview_send_queue`
- `reconcile_state`

## State Files Read And Written

Retention ledgers:

- Read:
  - `data/state/events.jsonl`
  - `data/state/transitions.jsonl`
  - `data/state/contacts.jsonl`
  - `data/state/content_dispatch.jsonl`
- Written:
  - `data/state/events.jsonl`
  - `data/state/transitions.jsonl`
  - `data/state/contacts.jsonl`
  - `data/state/content_dispatch.jsonl`

Projection artifacts:

- `data/state/send_queue_preview.json`

Preview artifacts:

- `data/state/send_preview.json`

Authorization artifacts:

- `data/state/send_authorization.json`

## External Actions Still Blocked

The registration explicitly declares:

- `external_actions_allowed: false`
- `network_allowed: false`
- `irreversible_action_allowed: false`

That keeps the boundary clear:

- retention ledgers are internal governed state,
- queue/preview/authorization files are local artifacts,
- and external sending remains blocked.

## Verification Commands

```powershell
python -m pytest tests/test_retention_cli.py -q
python -m pytest tests/test_retention_reconcile.py -q
python -m pytest tests/test_retention_dispatch_gate.py -q
python -m pytest tests/test_retention_send_queue.py -q
python -m pytest tests/test_retention_sender_contract.py -q
python -m pytest tests/test_retention_authorization.py -q
python tools/verify_system.py
```

Virtualenv equivalents used for verification here:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_cli.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_reconcile.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_dispatch_gate.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_send_queue.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_sender_contract.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_authorization.py -q
E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py
```

## Verification Results

- `tests/test_retention_cli.py`: `18 passed`
- `tests/test_retention_reconcile.py`: `6 passed`
- `tests/test_retention_dispatch_gate.py`: `11 passed`
- `tests/test_retention_send_queue.py`: `8 passed`
- `tests/test_retention_sender_contract.py`: `10 passed`
- `tests/test_retention_authorization.py`: `12 passed`
- `tools/verify_system.py`: `passed` with `E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py` after verifier stabilization updates that did not change retention runtime behavior
