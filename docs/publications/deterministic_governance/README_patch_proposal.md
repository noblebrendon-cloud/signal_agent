# README Patch Proposal

No top-level README modification was required to assemble this bundle. If a minimal exposure patch is desired, the following insertion is the narrowest repo-accurate option.

## Proposed Insertion

Insert this block in `README.md` immediately after the `## Policy invariants` section and before `## Drift Audit CLI`:

```md
## Deterministic Governance Bundle

See `docs/publications/deterministic_governance/` for a repo-grounded publication bundle that maps the live transition gate, operator write contracts, ledgers, routing and release surfaces, and proof boundaries onto a deterministic governance / control illusion model.

Key entry points:

- `docs/publications/deterministic_governance/README.md`
- `docs/publications/deterministic_governance/deterministic_governance.md`
- `docs/publications/deterministic_governance/implementation_evidence.md`
- `docs/publications/deterministic_governance/release/release_notes_v1.md`
```

## Why This Was Left As A Proposal

- The user requested bounded writes.
- The existing README is not required for the bundle to function.
- A proposal preserves the narrowest possible repo diff while still preparing release exposure text.
