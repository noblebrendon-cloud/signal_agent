# Phase 9 Static Export/Import Update

Commit: `feff458 Add static Governed Authoring packet export and import`

Phase 9 adds a minimal static JSON export/import surface to the Governed Authoring prototype. The patch keeps the prototype local and non-production while allowing it to exchange packets compatible with the Phase 7 bridge contract.

## What Changed

Updated files:

- `products/governed_authoring_studio/prototype_v1a/README.md`
- `products/governed_authoring_studio/prototype_v1a/app.js`
- `products/governed_authoring_studio/prototype_v1a/index.html`

New files:

- `products/governed_authoring_studio/prototype_v1a/prototype_bridge_static.js`
- `tests/test_governed_authoring_static_export_import.py`

The static UI can now:

- Export backend-compatible governed authoring JSON packets.
- Import backend result/output manifest packets.
- Preserve evidence refs.
- Preserve unresolved tensions.
- Preserve review status.
- Preserve provisional, rejected, deferred, and approved output status.
- Flag publication-ready packets that lack evidence refs.
- Flag generator/model self-approval.

## What Phase 9 Proves

Phase 9 proves:

- Static export packet shape matches the documented bridge contract.
- Imported backend result packets can be parsed into prototype-readable fields.
- Evidence refs survive export/import.
- Unresolved tensions survive export/import.
- Review status survives export/import.
- Output status survives export/import.
- Missing evidence is flagged.
- Generator self-approval is flagged.
- No server/network/backend submission behavior was added.
- No production writes were added.
- Production JSONL ledgers remain unchanged during the static export/import tests.

## Verification

Phase 9 verification included:

- `python -m pytest tests/test_governed_authoring_static_export_import.py -q`
- `python -m pytest tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q`
- `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q`
- `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q`
- Static syntax checks for the changed JavaScript and Python files.
- Production JSONL fingerprint checks.

## Browser Verification Limitation

The in-app browser could not verify direct `file://` interaction because browser policy blocked direct local-file navigation.

Current tests prove packet shape and static behavior, but they do not prove full interactive browser behavior under `file://`.

## What Phase 9 Does Not Prove

Phase 9 does not prove:

- The static prototype is backend-wired.
- A server/app surface exists.
- Production authoring artifact writes exist.
- Production canonical authoring ledger writes are enabled by default.
- The UI is production-governed.
- All authoring outputs are governed.
- Repo-wide promotion governance is complete.

## Proof Status Change

Before Phase 9:

```text
The backend proof path and prototype bridge existed, but the static prototype UI could not exchange bridge-compatible packets.
```

After Phase 9:

```text
The static prototype can export and import bridge-compatible JSON packets.
```

Boundary remains:

```text
The static prototype does not submit to a backend.
The static prototype does not perform production writes.
The static prototype is not a production Governed Authoring app.
```
