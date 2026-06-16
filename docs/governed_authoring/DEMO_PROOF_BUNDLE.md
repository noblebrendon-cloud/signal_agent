# Governed Authoring Demo Proof Bundle

This document records the local demo proof-bundle command added in Phase 15.

The command lives in `signal_agent/governed_authoring/demo_bundle.py`. It runs representative static export fixtures through the same offline Governed Authoring verification path used by the Phase 13 CLI, writes static-import-compatible result packets into a caller-provided output directory, and writes a local `proof_summary.md`.

## Command

```bash
python -m signal_agent.governed_authoring.demo_bundle \
  --out .tmp/governed_authoring_demo_bundle
```

Optional canonical ledger output:

```bash
python -m signal_agent.governed_authoring.demo_bundle \
  --out .tmp/governed_authoring_demo_bundle \
  --canonical-ledger
```

When `--canonical-ledger` is present, the command writes `canonical_governed_authoring.jsonl` inside the chosen output directory only.

## Covered Fixtures

| Fixture | Expected result |
| --- | --- |
| `static_export_valid_provisional.json` | `provisional` |
| `static_export_valid_approved.json` | `approved` |
| `static_export_missing_evidence.json` | `rejected` |
| `static_export_blocking_tension.json` | `deferred` |
| `static_export_generator_self_approval.json` | `rejected` |

## Output Files

The command writes:

- One `*.result.json` static-import-compatible packet per fixture.
- `proof_summary.md`.
- `canonical_governed_authoring.jsonl` only when `--canonical-ledger` is explicitly requested.

The proof summary lists:

- Fixture name.
- Expected result.
- Actual result.
- Pass/fail.
- Output packet path.
- Canonical ledger entry present yes/no.

## What Is Preserved

The demo bundle preserves:

- Evidence refs.
- Unresolved tensions.
- Review status.
- Output status.

## Boundary

The demo bundle is local proof infrastructure only.

It does not add:

- Server code.
- Browser-backend submission.
- Network behavior.
- Production authoring artifact writes.
- Default production canonical ledger writes.
- Static UI backend wiring.
- Repo-wide governance.

The command rejects output directories under the repo production `data/` tree.
