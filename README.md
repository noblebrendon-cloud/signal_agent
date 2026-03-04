# signal_agent — Canonical Execution Map

## Canonical roots
- Canonical Python package root: `signal_agent/`
- Canonical Leviathan subsystem: `signal_agent/leviathan/`

Non-canonical directories must not be treated as production entrypoints unless explicitly marked.

## Canonical entrypoints
- Stability Snapshot CLI:
  - `python -m signal_agent.leviathan.diagnostic.stability_snapshot.cli`
- Deterministic clock runtime:
  - `python -m signal_agent.core.clock.clock`

## Tests
- Stdlib runner:
  - `python -m unittest discover`

## Policy invariants
- `signal_agent/leviathan/diagnostic/stability_snapshot/invariant_v1.json`

## Runtime output directories (do not commit)
- `logs/`
- `repro_out/`
- `.tmp/`
- `.tmp_offload_out/`
