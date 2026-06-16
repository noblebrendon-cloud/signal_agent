# Release Candidate Boundary

This file defines the release-candidate boundary after the final Phase 18 verification pass.

## Current Release-Candidate Claim

Use:

```text
The repository contains a verified local proof pack for formal governance and covered Governed Authoring paths.
```

Expanded:

```text
The proof pack covers isolated formal governance, selected runtime integrations, claim evidence enforcement, HQ promotion separation for the covered path, configured canonical ledger entries, Governed Authoring backend decisions, prototype packet bridging, static export/import, offline verification, local CLI verification, and a repeatable local demo proof bundle.
```

## What Passed

The final verification pass ran the documented test groups for:

- Formal governance proof pack.
- Claim evidence enforcement.
- HQ promotion separation.
- Canonical ledger adapter.
- Operator canonical ledger adapter.
- Governed Authoring backend.
- Prototype bridge.
- Static export/import.
- Offline harness.
- Offline CLI.
- Demo proof bundle.

Documented result:

```text
102 passed
```

The local demo proof bundle also ran successfully with `--canonical-ledger` into a temp output directory.

## Ledger Boundary

Production JSONL fingerprint before and after verification:

```text
52 ba7d8cb8e7f12c7f5185069ba351d643d280e0b296b531139561cb69ad89c2d6
```

Interpretation:

```text
Production JSONL ledgers were not modified by this verification pass.
```

## Output Boundary

Allowed release-candidate outputs:

- Temp proof-bundle result JSON files.
- Temp `proof_summary.md`.
- Temp optional `canonical_governed_authoring.jsonl`.
- Documentation under `docs/proof_pack/`.

Not allowed as release-candidate outputs:

- Repo `data/` writes.
- Production authoring artifacts.
- Default production canonical ledger entries.
- Server files.
- Browser-backend wiring.

## Safe Claims

Safe:

- "A verified local proof pack exists for covered formal governance and Governed Authoring paths."
- "The local proof pack tests passed."
- "The local demo proof bundle produced repeatable proof outputs for covered fixtures."
- "Production JSONL fingerprints were unchanged during final verification."
- "The proof pack is local and non-production."

Unsafe:

- "Governed Authoring is production-ready."
- "The static UI is backend-wired."
- "The prototype submits to the backend."
- "Production authoring writes are governed."
- "Default production canonical authoring ledgers are enabled."
- "Repo-wide governance is complete."
- "Complete IBVM proof exists across every path."

## Remaining Release Blockers

Before any production release claim, the following remain unresolved:

- Production app/server surface design.
- Browser-backend submission path.
- Production authoring artifact store.
- Production canonical authoring ledger policy.
- Human identity and authority source.
- Repo-wide mutation inventory.
- Gating for all state-mutating paths.
- Full IBVM proof across all governed transitions.

## Commit Boundary

The Phase 18 report is documentation-only. It should be staged by exact path only if committed:

```bash
git add docs/proof_pack/FINAL_VERIFICATION_REPORT.md
git add docs/proof_pack/RELEASE_CANDIDATE_BOUNDARY.md
```
