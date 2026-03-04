# Architecture Declaration — Option A

## Canonical package root
`signal_agent/` is the canonical Python package root.

## Canonical Leviathan
`signal_agent/leviathan/` is the canonical Leviathan implementation.

## Non-canonical top-level directories
The following are not canonical code roots:
- `leviathan/` (legacy or experimental)
- `laviathon/` (typographic/experimental; not canonical)
- `app/` (wrapper/tools; not canonical package root)

## Runtime controller
Canonical runtime controller:
- `signal_agent/core/clock/clock.py`

Legacy controllers may exist elsewhere but must not be considered canonical entrypoints.

## Migration rule
Any code outside `signal_agent/` must either:
1) be migrated into `signal_agent/`, or
2) be explicitly marked legacy/experimental and excluded from canonical entrypoints.
