# Reflective Corpus / Reflective Pressure Boundary

## Boundary Decision

`app/reflective_corpus` is the upstream corpus memory layer.

`app/reflective_pressure` is the downstream pressure articulation, review, and output-preparation layer.

The corpus layer preserves and reconciles local reflective memory. The pressure layer may later help operators review, classify, package, and prepare selected material for downstream workflows, but it must not become a dependency of the corpus layer.

## Ownership

`reflective_corpus` owns:

- raw fragments
- theme registry
- deterministic theme matching
- pressure detection as internal corpus signal
- essay candidate seeds
- corpus reconciliation/reporting

`reflective_pressure` owns:

- pressure review
- classification workflows
- prompt packs
- review batches
- output preparation
- human judgment workflows

## Dependency Direction

`reflective_pressure` may consume reviewed outputs from `reflective_corpus` in the future.

`reflective_corpus` must not depend on `reflective_pressure`.

This keeps corpus memory local, deterministic, and upstream. It also prevents output-preparation concerns from leaking back into the memory layer.

## Explicit Prohibitions

The boundary prohibits:

- automatic publishing
- external posting
- network calls
- AI drafting
- automated detect-to-publish loops
- unreviewed mutation into production content

## Not Yet Authorized

The following are not yet authorized:

- no cross-module integration yet
- no automatic persistence of detected candidates into downstream publication flows
- no public API
- no external action path

## Future Integration Path

Future integration, if authorized separately, should follow this path:

```text
corpus fragment
-> theme/pressure/candidate
-> human review
-> reflective_pressure packet
-> publication workflow only through separate outbound authorization
```

## Checkpoint

Reflective Corpus initial implementation committed at:

```text
3184e3a286947c1ab924e088bd1a1483c906ee91
```
