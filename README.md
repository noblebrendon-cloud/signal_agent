# signal_agent — Canonical Execution Map

## Canonical roots
- Canonical Python package root: `signal_agent/`
- Canonical Laviathon namespace: `signal_agent.laviathon`
- Legacy compatibility namespace: `signal_agent.leviathan`

## Deployable app roots
- `apps/laviathon-web/` -> `laviathon.com`
- `apps/laviathon-labs/` -> `labs.laviathon.com`
- `apps/laviathon-docs/` -> `docs.laviathon.com`
- `apps/laviathon-api/` -> `api.laviathon.com`

Non-canonical directories must not be treated as production entrypoints unless explicitly marked.

## Canonical entrypoints
- Stability Snapshot CLI:
  - `python -m signal_agent.laviathon.diagnostic.stability_snapshot.cli`
- Deterministic clock runtime:
  - `python -m signal_agent.core.clock.clock`

## Tests
- Stdlib runner:
  - `python -m unittest discover`

## Policy invariants
- `signal_agent/leviathan/diagnostic/stability_snapshot/invariant_v1.json`

## Deterministic Governance Bundle

See `docs/publications/deterministic_governance/` for a repo-grounded publication bundle that maps the live transition gate, operator write contracts, ledgers, routing and release surfaces, and proof boundaries onto a deterministic governance / control illusion model.

Key entry points:

- `docs/publications/deterministic_governance/README.md`
- `docs/publications/deterministic_governance/deterministic_governance.md`
- `docs/publications/deterministic_governance/implementation_evidence.md`
- `docs/publications/deterministic_governance/release/release_notes_v1.md`

## Drift Audit CLI

Offline, deterministic log-drift auditor.

Install (once):
```powershell
pip install -e .
```

Demo run:
```powershell
drift-audit analyze --input examples\drift_audit\demo_input --out .tmp\demo_out --format both
```

Docs: `docs/drift_audit/QUICKSTART.md`
Module README (legacy physical path): `signal_agent/leviathan/diagnostic/drift_audit/README.md`

- Canonical entrypoint: `python -m signal_agent.laviathon.cli.drift_audit_cli`
- Console script (after install): `drift-audit`
- Tests: `python -m pytest tests/drift_audit/ -v`

## Runtime output directories (do not commit)
- `logs/`
- `repro_out/`
- `.tmp/`
- `.tmp_offload_out/`
