# v0.2 Clean Branch Baseline Audit

Target branch:

```text
release/v0.2-local-authoring-surface at 322455d
```

## Question

Why did dirty main verification report 52 production JSONL files while the clean release branch reported 6?

## Finding

The two counts refer to different checkout states.

Dirty main worktree:

```text
all=52 tracked=6 untracked_unignored=0 ignored=46
```

Clean release branch:

```text
tracked JSONL files only: 6
```

The 46 additional JSONL files in dirty main are ignored operational/local state files. They are present on disk in the dirty main worktree but are not part of the clean release branch checkout.

## Tracked JSONL Files

The tracked JSONL files are:

```text
data/artifact_registry.jsonl
data/capture/promotion_log.jsonl
data/intake/intake.jsonl
data/state/letters_of_light_letters.jsonl
data/state/letters_of_light_transitions.jsonl
data/state/module_artifacts.jsonl
```

These are the 6 JSONL files present in the clean release branch.

## Ignored Operational JSONL Files In Dirty Main

Ignored JSONL examples from dirty main include:

```text
data/capture/routing_log.jsonl
data/claims/claims_ledger.jsonl
data/claims/distribution_log.jsonl
data/graph/cooccurrence_index.jsonl
data/graph/entity_index.jsonl
data/graph/relationship_index.jsonl
data/operator/runs/operator_runs.jsonl
data/outputs/publish_log.jsonl
data/social_offload/logs/social_offload_runs.jsonl
data/state/activation_events.jsonl
data/state/events.jsonl
data/state/transition_gate_events.jsonl
data/state/transitions.jsonl
```

These files should remain quarantined from release commit planning.

## Fingerprints Observed

Dirty main all-JSONL fingerprint:

```text
52 ba7d8cb8e7f12c7f5185069ba351d643d280e0b296b531139561cb69ad89c2d6
```

Clean release branch all-JSONL fingerprint:

```text
6 0b01cec041f2e54b4dcc1467f89019bbcd5ab5eb0a5a4e6d34ff02e426c9da0d
```

The clean release branch fingerprint stayed unchanged before and after the release-branch verification and CLI exercise.

## Interpretation

The clean release branch verification can claim:

```text
The clean release branch's tracked production JSONL baseline was unchanged before and after verification.
```

It should not claim:

```text
The clean release branch reproduced the dirty main worktree's 52-file operational JSONL baseline.
```

## Recommended Baseline Language

Use both statements when needed:

- Clean release branch baseline: 6 tracked JSONL files, unchanged before and after verification.
- Operational dirty-main baseline: 52 on-disk JSONL files, including ignored local operational state, previously observed unchanged in main-worktree verification.

Do not add ignored operational JSONLs to the release branch.

Do not replace one baseline with the other without documenting checkout provenance.

## Release Evidence Recommendation

The v0.2 release verification should use a clean-branch before/after fingerprint as the release evidence.

If operational continuity evidence is needed, document it separately as a local operational baseline, not as committed release-branch evidence.
