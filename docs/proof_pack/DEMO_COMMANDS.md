# Demo Commands

This file records local demo commands for the Governed Authoring proof surfaces.

All commands must use temp or explicit output paths. They must not write into repo `data/`.

## Offline CLI Verification

Verify one static prototype export packet and write one static-import-compatible result packet:

```bash
python -m signal_agent.governed_authoring.cli verify-static-export \
  --input tests/fixtures/governed_authoring/static_export_valid_approved.json \
  --output <temp-output-dir>/static_export_valid_approved.result.json
```

With optional explicit canonical ledger output:

```bash
python -m signal_agent.governed_authoring.cli verify-static-export \
  --input tests/fixtures/governed_authoring/static_export_valid_approved.json \
  --output <temp-output-dir>/static_export_valid_approved.result.json \
  --canonical-ledger <temp-output-dir>/canonical_governed_authoring.jsonl
```

## Demo Proof Bundle

Run representative fixtures and write local proof outputs:

```bash
python -m signal_agent.governed_authoring.demo_bundle --out <temp-output-dir>
```

Run representative fixtures with optional canonical ledger output inside the chosen directory:

```bash
python -m signal_agent.governed_authoring.demo_bundle --out <temp-output-dir> --canonical-ledger
```

## Demo Bundle Outputs

The demo bundle writes:

- One `*.result.json` static-import-compatible packet per representative fixture.
- `proof_summary.md`.
- `canonical_governed_authoring.jsonl` only when `--canonical-ledger` is requested.

## Required Path Boundary

Safe:

- `%TEMP%/governed_authoring_demo_bundle`
- `.tmp/governed_authoring_demo_bundle`
- Any explicit non-production output directory outside repo `data/`.

Unsafe:

- `data/`
- `data/outputs/`
- Any production ledger or authoring artifact path.

The demo bundle rejects output directories under repo `data/`.
