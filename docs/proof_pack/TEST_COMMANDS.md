# Test Commands

This file lists the verified local test command groups for the formal governance and Governed Authoring proof chain.

## Formal Governance Proof Pack

```bash
python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q
```

## Claim Evidence Enforcement

```bash
python -m pytest tests/test_claim_evidence_enforcement.py -q
```

## HQ Promotion Separation

```bash
python -m pytest tests/test_hq_promotion_separation.py -q
```

## Canonical Ledger Adapter

```bash
python -m pytest tests/test_canonical_ledger_adapter.py -q
```

## Operator Canonical Ledger Adapter

```bash
python -m pytest tests/test_operator_canonical_ledger_adapter.py -q
```

## Governed Authoring Backend

```bash
python -m pytest tests/test_governed_authoring_backend.py -q
```

## Prototype Bridge

```bash
python -m pytest tests/test_governed_authoring_prototype_bridge.py -q
```

## Static Export And Import

```bash
python -m pytest tests/test_governed_authoring_static_export_import.py -q
```

## Offline Harness

```bash
python -m pytest tests/test_governed_authoring_offline_harness.py -q
```

## Offline CLI

```bash
python -m pytest tests/test_governed_authoring_offline_cli.py -q
```

## Demo Proof Bundle

```bash
python -m pytest tests/test_governed_authoring_demo_bundle.py -q
```

## Combined Regression Bands

Governed Authoring local proof loop:

```bash
python -m pytest tests/test_governed_authoring_demo_bundle.py tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py -q
```

Governed Authoring backend and bridge:

```bash
python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q
```

Selected governance integrations:

```bash
python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q
```

Formal governance proof pack:

```bash
python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q
```

## Test Boundary

These commands prove selected covered paths. They do not prove every repository state mutation, every promotion path, or a production-governed UI.
