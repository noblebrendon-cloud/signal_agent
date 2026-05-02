# Retention Pre-External V1 Checkpoint

**Generated**: 2026-05-01  
**Scope**: Verified checkpoint for the retention subsystem before any external sender admission  
**Checkpoint label**: `retention_pre_external_v1`  
**Retention ledgers mutated**: No

**Sources reviewed**:
- `data/state/module_artifacts.jsonl`
- `docs/operator/module_artifact_index.md`
- `docs/operator/retention_module_registration_report.md`
- `docs/operator/retention_stage_2_reconciliation.md`
- `docs/operator/retention_stage_3_dispatch_gate.md`
- `docs/operator/retention_stage_4_send_queue_projection.md`
- `docs/operator/retention_stage_5_local_sender_contract.md`
- `docs/operator/retention_stage_6_outbound_authorization.md`
- `docs/operator/retention_subsystem_guide.md`
- `app/retention/`

## checkpoint_summary

The retention subsystem is at a verified **pre-external** boundary.

This checkpoint means:
- retention is fully registered as an active governed module
- Stages 1-6 are implemented as local-only governance and preview surfaces
- no real sender adapter is admitted
- no outbound delivery is permitted
- local verification artifacts may be produced, but they do not authorize or execute external action

## what_was_stabilized

The stabilized surface at this checkpoint is:
- Stage 1 append-only contact intake, transitions, and governed ledger writes
- Stage 2 read-only reconciliation over the four retention ledgers
- Stage 3 read-only dispatch readiness gating
- Stage 4 deterministic send queue projection
- Stage 5 local-only sender preview validation through `local-noop`
- Stage 6 explicit local operator authorization over preview artifacts
- retention module registration as one governed internal capability
- repo-wide verification stability through the current `tools/verify_system.py` surface

## boundary_flags

These boundary flags remain explicitly preserved:

- `external_actions_allowed = false`
- `network_allowed = false`
- `irreversible_action_allowed = false`

These flags are part of the live `retention` module record and are the hard boundary that defines this checkpoint as pre-external.

## verified_stage_boundary

### Stage 1: Seed and ingest retention state

Owned surfaces:
- `add-contact`
- `ingest-substack-csv`
- append-only event, transition, contact, and optional dispatch-plan creation

Current boundary:
- canonical contact identity is hashed before it enters retained state
- dry-run emits deterministic previews only
- apply mode appends to governed ledgers only
- no external sender is involved

### Stage 2: Reconciliation

Owned surface:
- read-only integrity audit across the retention ledgers

Current boundary:
- catches missing ledger rows, hash-chain drift, raw identifier leakage, and dispatch/state inconsistency
- fails closed on inconsistencies
- does not repair or rewrite ledgers

### Stage 3: Dispatch readiness

Owned surface:
- read-only evaluation of whether planned dispatches are structurally eligible

Current boundary:
- classifies records as `eligible`, `blocked`, or `skipped`
- still performs no send, no status mutation, and no network action

### Stage 4: Send queue projection

Owned surface:
- deterministic projection of eligible dispatches into a queue preview artifact

Current boundary:
- only eligible records enter the queue
- blocked and skipped records are excluded
- output is a preview artifact, not a delivery act

### Stage 5: Local sender contract

Owned surface:
- local validation of the projected queue through the `local-noop` adapter

Current boundary:
- validates queue structure and provenance
- keeps `no_network: true`
- keeps `sent: false`
- does not mutate dispatch outcomes

### Stage 6: Outbound authorization

Owned surface:
- explicit operator approval or denial of a local sender preview artifact

Current boundary:
- records local authorization intent only
- keeps `external_action_allowed: false`
- keeps `sent: false`
- does not admit a real sender boundary

## artifact_classes

The retention subsystem has four distinct output classes and they should not be conflated.

### Ledgers

Authoritative retained state:
- `data/state/events.jsonl`
- `data/state/transitions.jsonl`
- `data/state/contacts.jsonl`
- `data/state/content_dispatch.jsonl`

Properties:
- append-only
- governed
- hash-chained
- reconciliation input

### Projection artifact

Deterministic queue preview:
- `data/state/send_queue_preview.json`

Properties:
- derived from clean reconciliation and dispatch-readiness results
- not a ledger
- not an authorization
- not a delivery result

### Preview artifact

Local sender preview:
- `data/state/send_preview.json`

Properties:
- validated only through `local-noop`
- `no_network: true`
- `sent: false`
- local-only delivery-contract proof

### Authorization artifact

Explicit operator decision record:
- `data/state/send_authorization.json`

Properties:
- records approve or deny over a local preview artifact
- preserves `external_action_allowed: false`
- does not unlock real sending

## checkpoint_verification_commands

```powershell
python -m pytest tests/test_retention_cli.py -q
python -m pytest tests/test_retention_reconcile.py -q
python -m pytest tests/test_retention_dispatch_gate.py -q
python -m pytest tests/test_retention_send_queue.py -q
python -m pytest tests/test_retention_sender_contract.py -q
python -m pytest tests/test_retention_authorization.py -q
python tools/verify_system.py
```

Virtualenv equivalents:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_cli.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_reconcile.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_dispatch_gate.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_send_queue.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_sender_contract.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_authorization.py -q
E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py
```

## checkpoint_verification_status

Validated at this checkpoint with:
- `tests/test_retention_cli.py`: `18 passed`
- `tests/test_retention_reconcile.py`: `6 passed`
- `tests/test_retention_dispatch_gate.py`: `11 passed`
- `tests/test_retention_send_queue.py`: `8 passed`
- `tests/test_retention_sender_contract.py`: `10 passed`
- `tests/test_retention_authorization.py`: `12 passed`
- `tools/verify_system.py`: `passed`

## why_this_is_the_correct_pre_external_boundary

This is the correct pre-external boundary because the subsystem can already:
- capture canonical contact events without leaking raw email into retained ledgers
- reconcile its own ledgers before any downstream dispatch evaluation
- prove queue eligibility locally without admitting a sender
- validate projected queue records through a local-only sender contract
- require explicit operator authorization while still forbidding delivery

That means the governance spine is in place, but the irreversible external boundary is still blocked.

## what_must_not_be_added_yet

Do not add any of the following until the next admitted stage defines their governance explicitly:
- direct Gmail, SMTP, Substack, Mailchimp, or ConvertKit sending
- any adapter that can set `external_action_allowed: true`
- delivery outcome ledgers without a governed schema
- retry or backoff logic that implies real delivery semantics
- sent-state mutation rules
- implicit approval paths that bypass explicit operator authorization
