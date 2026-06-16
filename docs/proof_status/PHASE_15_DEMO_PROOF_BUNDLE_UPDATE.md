# Phase 15 Demo Proof Bundle Update

Commit: `c1ab877 Add local Governed Authoring demo proof bundle`

Phase 15 adds a local demo proof-bundle command for the Governed Authoring offline verification path. It packages the representative static export fixture loop into repeatable local proof output.

## What Changed

New implementation file:

- `signal_agent/governed_authoring/demo_bundle.py`

New test file:

- `tests/test_governed_authoring_demo_bundle.py`

New documentation file:

- `docs/governed_authoring/DEMO_PROOF_BUNDLE.md`

## Demo Commands

Run the local demo proof bundle:

```bash
python -m signal_agent.governed_authoring.demo_bundle --out <output-dir>
```

Run with optional canonical ledger output:

```bash
python -m signal_agent.governed_authoring.demo_bundle --out <output-dir> --canonical-ledger
```

The canonical ledger file is written as `canonical_governed_authoring.jsonl` inside the chosen output directory only.

## Generated Output Files

The demo bundle writes:

- `proof_summary.md`.
- One static-import-compatible result JSON per representative fixture.
- Optional `canonical_governed_authoring.jsonl` inside the chosen output directory only.

The command rejects output directories under repo `data/`.

## Covered Fixture Outcomes

| Fixture | Expected result |
| --- | --- |
| `static_export_valid_provisional.json` | provisional |
| `static_export_valid_approved.json` | approved |
| `static_export_missing_evidence.json` | rejected |
| `static_export_blocking_tension.json` | deferred |
| `static_export_generator_self_approval.json` | rejected |

## What Survives

The demo bundle preserves:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Output status.

## What Is Now Proven

Phase 15 proves:

- The local demo proof bundle is repeatable for covered fixtures.
- Representative static export fixtures can be verified through the offline Governed Authoring proof path.
- Static-import-compatible result JSON packets are written into a chosen output directory.
- A proof summary can be generated locally.
- Optional canonical ledger output is constrained to the chosen output directory.
- Output under repo `data/` is refused.
- No server behavior is added.
- No browser-backend submission is added.
- No production writes are added.
- No default production ledger writes are enabled.

## Verification

Phase 15 verification included:

- `python -m pytest tests/test_governed_authoring_demo_bundle.py -q`
- `python -m pytest tests/test_governed_authoring_offline_cli.py tests/test_governed_authoring_offline_harness.py -q`
- `python -m pytest tests/test_governed_authoring_static_export_import.py tests/test_governed_authoring_prototype_bridge.py tests/test_governed_authoring_backend.py -q`
- `python -m pytest tests/test_claim_evidence_enforcement.py tests/test_canonical_ledger_adapter.py tests/test_hq_promotion_separation.py tests/test_operator_canonical_ledger_adapter.py -q`
- `python -m pytest tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_formal_governance_cli.py -q`
- Example demo command with `--canonical-ledger` into a temp output directory.
- Production JSONL fingerprint check before and after the example command.

## What Phase 15 Does Not Prove

Phase 15 does not prove:

- Static UI submits to backend.
- A server/app surface exists.
- Browser-backend submission exists.
- A production authoring artifact write path exists.
- Default production canonical authoring ledger writes are enabled.
- UI is production-governed.
- Repo-wide promotion governance is complete.

## Proof Status Change

Before Phase 15:

```text
The local CLI could verify one static export packet at a time, but there was no repeatable local proof-bundle command that produced fixture result packets and a proof summary.
```

After Phase 15:

```text
The local demo proof bundle is repeatable for covered fixtures and writes local proof outputs only to a chosen output directory.
```
