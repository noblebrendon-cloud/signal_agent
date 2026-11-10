# Campaign implementation verification

Recorded 2026-11-10 UTC. Implementation was prepared against connected repository `main` at `fb2918bcf4559bdec37b8367ec458dff2528db11`.

## Scope and result

**216 targeted tests passed in 2.31 seconds** on Python 3.12.14/Linux. This comprises 149 new campaign tests and 67 existing governed-authoring, formal-governance, and transition-gate regressions. The command used `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` so unrelated globally installed pytest plugins did not affect the declared test environment.

The exact test list is in the [campaign guide](README.md) and `.github/workflows/campaign-verification.yml`. Local preparation used a hash-verified snapshot of relevant upstream code, fixtures, and schemas. This is not a claim that the complete repository suite, another Windows checkout, or the deployed Control Room was tested.

| Layer | Observed result |
| --- | --- |
| Unit | Deterministic decisions, strict contracts, evidence quality, correction lineage, and boundaries passed. |
| Integration | The real governed-authoring runtime produced provisional results; all packet schemas and source/task references passed. |
| End-to-end | Actual CLI subprocess and loopback HTTP requests completed a controlled campaign cycle. |
| Filesystem | Eight export files matched their checksums; exact source text survived; overwrite, traversal, symlink, and protected-path checks passed. |
| Performance | Representative 0/100/1,000-observation histories were measured locally, as detailed below. |
| CI | The workflow is configured to run targeted tests, controlled trial, and benchmark. The PR check is the authoritative record of remote execution. |
| Deployment | No deployment job, live campaign release, external-account connection, or canonical-state mutation was performed. |

## Controlled local trial

`python scripts/campaign_trial.py` passed. It exercised:

1. An illustrative planned campaign receiving `run_small_test`.
2. Its exact source and explicit qualified claim passing through `GovernedAuthoringRuntime`, returning `EMIT_PROVISIONAL_DRAFT` with no canonical ledger entry.
3. An API handoff and CLI export producing identical handoff IDs, preserving source text, and passing all eight file checksum checks.
4. A testing campaign with no observations receiving `observe_more`.
5. Synthetic reported observations remaining insufficient.
6. Comparable synthetic observations under a complete supplied plan supporting `repeat_theme`, without a causal-effect claim.
7. A paused campaign being denied a handoff with HTTP 409.

All audience observations in this trial were explicitly synthetic. Pending executor tasks were not presented as completed content or media, and no social destination was called. Temporary trial exports were removed after verification.

## Performance measurement

Command: `python scripts/benchmark_campaigns.py --iterations 30`. Each scenario had one warm-up followed by 30 timed calls. Python allocation peaks were measured on a separate call with `tracemalloc`.

| Observations | Input bytes | Evaluation median / p95 | Handoff median / p95 | Evaluation allocation peak | Handoff allocation peak |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1,604 | 0.112 / 0.150 ms | 0.364 / 0.445 ms | 19,817 bytes | 37,241 bytes |
| 100 | 48,497 | 1.811 / 2.817 ms | 3.365 / 3.664 ms | 202,506 bytes | 290,587 bytes |
| 1,000 | 470,598 | 16.847 / 20.874 ms | 29.660 / 34.623 ms | 2,058,824 bytes | 2,880,891 bytes |

These are single-process warm-call observations on Linux, not throughput, concurrent HTTP capacity, total process memory, provider latency, or a production SLA. The script records its environment and measurement time and can be rerun on the deployment target. No arbitrary universal latency threshold was introduced.

## Findings resolved during review

- Missing observations in an already active test no longer trigger another automatic production test.
- Excluded duplicate reports cannot inflate exposure totals, and one reference cannot masquerade as multiple independent variants.
- Later contradictions and unfavorable qualitative records remain visible regardless of input ordering.
- An injected repository root cannot remove the executing checkout's protected-path checks.
- Production requires explicit claims, preventing the older runtime's first-500-character fallback from dropping qualifications and creating unlinked claim IDs.
- Selected principles reach the executor as versioned working guidance, not merely IDs.
- Parent and correction links are preserved without claiming historical lookup or verification.

## Practical limits

The evaluator accepts attributed editorial and observation records. It does not authenticate a reviewer, retrieve platform metrics, or independently prove source truth. Source hashes detect changed bytes, not factual accuracy. Principle interpretations remain proposed adaptations of visible labels from the supplied recording.

The API is local and returns in-memory material. Source-to-Series production, remote Control Room integration, actual destination approval, publishing, and audience measurement require their respective executable integrations and receipts. Existing authority boundaries remain in place.
