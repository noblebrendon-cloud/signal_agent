# Release Notes v1

Date: 2026-04-20

## Summary

This release adds a publication-grade bundle under `docs/publications/deterministic_governance/` that maps a deterministic governance / control illusion model onto live repo surfaces rather than describing the model in isolation.

This release publishes a repo-grounded deterministic governance artifact that is intentionally bounded to repo-demonstrated behavior. The strongest repo-proven surfaces in this release are the governed operator write path and one named docs-route publication path from compiled to staged to emitted. Other routing, publication, release, and repo-wide invariant claims remain explicitly partial or theoretical where the repo does not yet prove them.

## What Is Included

- Formal model of the Determinism Invariant
- Control Illusion Detection Test
- Exact repo surface inventory
- Invariant-to-code/config/test mapping
- Implementation evidence table
- Failure mode analysis
- Mermaid diagram sources under `docs/publications/deterministic_governance/diagrams/`
- TeX formalizations
- Citation and Zenodo metadata
- Minimal README patch proposal

## What The Bundle Proves

- Governed operator write workflows are constrained by declared intent, declared read/write boundaries, transition gating, duplicate prevention, and boundary evidence in `signal_agent/operator/runtime.py`, `config/operator/tools.yaml`, and `config/operator/workflows.yaml`.
- Transition denial is fail-closed on governed paths proved through `app/hq/governance/transition_gate.py`, `config/state_machine.yaml`, `tests/test_operator_write_denial.py`, and `tests/security/test_transition_bypass.py`.
- Durable ledgers and registries exist on named repo surfaces including `shared/state_registry.py`, `app/intake/intake.py`, `app/hq/capture/promote.py`, `app/hq/capture/router.py`, and `services/release_orchestrator/runner.py`.

## What The Bundle Does Not Claim

- It does not claim every repo mutation path already satisfies the full invariant.
- It does not claim that publication, release, routing, and curation all use the same enforcement strength as the operator runtime.
- It does not change runtime governance behavior.

## Release Cautions

- `services/release_orchestrator/runner.py` and `app/hq/curation/curate.py` now use the shared IO contract on their named persistence surfaces, but they still do not prove operator-style declared-vs-observed boundary verification.
- `shared/contract.py` still exposes low-confidence `member_inference` as a signal, but `app/hq/capture/router.py` now fails closed when that is the only contract evidence, as exercised in `tests/test_phase2_improvements.py`.
- `config/state_machine.yaml` explicitly notes that some flows remain only partially implemented.

## Recommended Next Hardening Step

Unify non-operator mutators with the same declared-boundary and append-discipline patterns already present in `signal_agent/operator/runtime.py` and `app/utils/io_contract.py`.

## Public Exposure Patch

If the bundle is exposed from the repo root README, use the insertion prepared in `docs/publications/deterministic_governance/README_patch_proposal.md`.

## GitHub And Zenodo Release Checklist

- Confirm the bundle path is `docs/publications/deterministic_governance/` and all files intended for release are committed.
- If desired, apply the README insertion from `README_patch_proposal.md` after `## Policy invariants` in the top-level `README.md`.
- Review `release/CITATION.cff` for author, date, version, and repository URL accuracy.
- Review `release/zenodo_metadata.json` for creator name, access policy, related identifiers, and version.
- Create the Git tag for the release version you intend to publish.
- Push the commit and tag to GitHub.
- Draft the GitHub release using this file as the release note body.
- Ensure the GitHub release includes the repository path `docs/publications/deterministic_governance/` in the description or assets note.
- Archive the tagged release to Zenodo and verify the imported metadata matches `zenodo_metadata.json`.
- After Zenodo assigns a DOI, update any external citation surfaces if needed.
