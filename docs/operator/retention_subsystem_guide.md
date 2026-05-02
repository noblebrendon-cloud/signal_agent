# Retention Subsystem Guide

**Generated**: 2026-05-01  
**Scope**: Operator and developer guide for the Stage 1-6 retention subsystem  
**Retention ledgers mutated by this guide update**: No

## Purpose

The retention subsystem is the governed internal path for taking contact-related events, deciding whether they affect contact state, planning local dispatch intent, and projecting that intent into deterministic local artifacts.

It solves a narrow problem: the repo needs a safe retention spine before any automation is allowed to reach external delivery systems. That means identity handling, state transitions, queue preparation, preview validation, and operator authorization all have to exist as local governed steps first.

It is governed before it is automated because irreversible delivery should not happen until the system can prove:
- the ledgers are internally consistent
- dispatch intent is structurally valid
- queue records are deterministic and traceable
- preview validation is local-only
- operator approval exists as an explicit boundary

## Architecture

### Stage 1: Contact Intake And Append-Only Ledgers

`add-contact` creates a canonical `contact_seeded` event, appends it to `events.jsonl`, evaluates a transition, appends the transition decision to `transitions.jsonl`, and only appends a `contact_snapshot` to `contacts.jsonl` when the transition gate applies a state change. Optional dispatch planning can append a local plan to `content_dispatch.jsonl`.

### Stage 2: Reconciliation

`reconcile` reads the retention ledgers without mutating them and reports structural inconsistencies such as missing transitions, missing contact snapshots, invalid dispatch references, raw identifier leakage, and broken hash-chain relationships.

### Stage 3: Dispatch Readiness Gate

`dispatch-ready` requires reconciliation to pass first. It reads planned dispatch records and determines whether each one is eligible, blocked, or skipped based on contact state, consent, dispatch type, local safety conditions, and current plan status.

### Stage 4: Send Queue Projection

`project-send-queue` converts only eligible dispatch-ready records into deterministic `send_ready` queue records. Blocked and skipped dispatches stay out of the queue and are reported as exclusions.

### Stage 5: Local Sender Preview Contract

`send-preview` validates a Stage 4 queue projection against the local sender contract through the `local-noop` adapter. This produces accepted or rejected preview results without contacting any external service and without marking anything sent.

### Stage 6: Outbound Authorization

`authorize-send` applies an explicit operator decision to a Stage 5 preview result. This can approve or deny the preview artifact, but it still cannot enable real delivery.

## State And Artifacts

### Retention Ledgers

- `data/state/events.jsonl`
- `data/state/transitions.jsonl`
- `data/state/contacts.jsonl`
- `data/state/content_dispatch.jsonl`

These are the governed append-only retention ledgers.

### Projection Artifact

- `data/state/send_queue_preview.json`

This is the deterministic Stage 4 queue projection.

### Preview Artifact

- `data/state/send_preview.json`

This is the Stage 5 local sender preview output.

### Authorization Artifact

- `data/state/send_authorization.json`

This is the Stage 6 local operator authorization output.

## Safety Boundaries

- `send_ready` is not `sent`
- `accepted_preview` is not `sent`
- an authorized preview is not external permission
- `external_actions_allowed` remains `false`
- `network_allowed` remains `false`
- `irreversible_action_allowed` remains `false`

Even when a record is eligible, projected, accepted in preview, or approved by an operator, the system is still operating inside a governed local boundary with no external sending.

## How To Use It

Use the repo virtualenv interpreter for all retention commands:

```powershell
E:\signal_agent\.venv\Scripts\python.exe
```

### Add Contact Dry Run

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli add-contact --source substack --identifier-kind email --identifier-value test@example.com --consent-status opted_in --dry-run
```

### Add Contact Apply

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli add-contact --source substack --identifier-kind email --identifier-value test@example.com --consent-status opted_in --apply --plan-dispatch
```

### Reconcile

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli reconcile --state-root data/state
```

### Dispatch Ready

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli dispatch-ready --state-root data/state
```

### Project Send Queue Preview To Stdout

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli project-send-queue --state-root data/state
```

### Project Send Queue To File

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli project-send-queue --state-root data/state --out data/state/send_queue_preview.json
```

### Send Preview To Stdout

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli send-preview --queue data/state/send_queue_preview.json --adapter local-noop
```

### Send Preview To File

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli send-preview --queue data/state/send_queue_preview.json --adapter local-noop --out data/state/send_preview.json
```

### Authorize Send Approve

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli authorize-send --preview data/state/send_preview.json --operator-id local-operator --decision approve
```

### Authorize Send Deny

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli authorize-send --preview data/state/send_preview.json --operator-id local-operator --decision deny
```

### Optional Authorization Artifact File

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m app.retention.cli authorize-send --preview data/state/send_preview.json --operator-id local-operator --decision approve --out data/state/send_authorization.json
```

## Expected Outputs

### `add-contact --dry-run`

The command prints preview payloads for the event, transition, contact snapshot, and dispatch plan. Nothing is written. A dry run means the governed path can be evaluated without mutating state.

### `add-contact --apply`

The command appends the event and transition, appends a contact snapshot only if the transition decision applies, and optionally appends a dispatch plan if `--plan-dispatch` is present. An applied transition means the event changed the governed contact state.

### `reconcile`

`clean: true` means the current retention ledgers are internally consistent under the Stage 2 checks. `clean: false` means inconsistencies were found and downstream gates should not be trusted.

### `dispatch-ready`

`eligible` means a planned dispatch is structurally safe to become send-ready inside the local system. `blocked` means it failed a required condition. `skipped` means it is structurally terminal or intentionally not advanced.

### `project-send-queue`

`projected_count` is the number of eligible dispatch records converted into deterministic queue records. `excluded_count` covers blocked and skipped records that were intentionally kept out of the queue.

### `send-preview`

`accepted_preview` means the local-noop adapter contract accepted the queue record as a valid local preview input. It is still unsent and local-only. `rejected_preview` means the queue or one of its records failed contract validation.

### `authorize-send`

`authorized: true` means the operator explicitly approved the preview artifact. `authorized: false` means it was denied. In both cases, the records remain `sent: false` and `external_action_allowed: false`.

## Verification

Run the full retained verification surface with the repo virtualenv interpreter:

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_cli.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_reconcile.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_dispatch_gate.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_send_queue.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_sender_contract.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_authorization.py -q
E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py
```

## Troubleshooting

### Reconciliation Fails

If `reconcile` returns `clean: false`, stop there. The later gates are designed to fail closed when Stage 2 reports inconsistent ledger state.

### `dispatch-ready` Blocks A Record

This usually means the contact state is not eligible, consent does not allow dispatch, the dispatch type is not recognized, the plan status is terminal, or reconciliation failed upstream.

### `send-preview` Rejects A Queue Record

This usually means the queue projection is not clean, a queue record is missing required provenance, the queue status is not `send_ready`, or the record is missing a template or content reference.

### `authorize-send` Refuses Approval

Approval fails closed if the preview is not clean, the adapter is not `local-noop`, any preview result is rejected, `sent` is not `false`, `no_network` is not `true`, or the operator decision is invalid.

### Optional Extractor Dependencies Reported By The Verifier

`tools/verify_system.py` treats format-specific extractor dependencies as optional and reports them deterministically. If one of those packages is absent, the verifier should report the optional state instead of failing the retention boundary itself.

### Provider Identity Assertion Expectations

The verifier expects canonical fully-qualified provider identities in `provider:model` form. If a fallback assertion fails on an unqualified model string, the expectation is stale.

## Next Allowed Stage

The next admitted stage must **not** jump straight to Gmail, SMTP, Substack, Mailchimp, or any other direct sender integration.

Before a real sender can be admitted, the system still needs:
- a real sender admission policy
- a delivery outcome ledger
- an explicit `external_action_allowed` transition
- a retry and failure contract
- governed sent-state mutation rules
- explicit operator approval requirements tied to real delivery semantics

Until those exist, the retention subsystem remains a governed internal boundary only.
