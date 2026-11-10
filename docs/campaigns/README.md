# Campaign principles and traversal

Signal Agent can now evaluate a campaign's supplied state and evidence, propose a next action, and prepare a scoped Source-to-Series handoff through the existing governed authoring runtime. It preserves the campaign purpose and source qualifications while allowing bounded creative variation.

This implementation is a Python module and local API. It does not connect a remote Control Room, synchronize another checkout, operate a scheduler, or publish content. Its lineage and verification labels describe supplied records, not independently retrieved audience data.

## Operating model

1. Supply a `campaign_context.v1` with purpose, phase, sources, claims, editorial assessment, selected principles, and requested outputs.
2. Evaluate at an explicit timestamp. Receive a deterministic `campaign_decision.v1` with an action, reasons, evidence exclusions, limitations, and a working hypothesis.
3. For an eligible bounded production action, prepare a `campaign_handoff.v1`. The adapter runs the existing `GovernedAuthoringRuntime` in provisional mode and produces a pending `source_to_series.task_packet.v1`.
4. Execute only the requested Source-to-Series drafts, preserving the source and decision references. This requires a separate executor invocation; preparing the packet does not generate prose or media.
5. Review actual outputs and use existing destination-specific release authority. Record real release receipts and observations separately, then evaluate the updated context.

Evaluation does not mutate campaign phase, approve an artifact, create a lane, or write a canonical ledger. An explicit operator request records a proposed action; it is not execution authority. Arbitrary constraints supplied as prose accompany the packet for review and are not silently treated as executable policy.

## The eleven principles

The catalog retains the eleven labels visible in the supplied recording. Its working rules are operational adaptations, not a verified transcript of the speaker's definitions or universal scientific laws. The catalog includes source provenance and this qualification.

Select the principles relevant to a particular piece or campaign. An empty selection is valid. The selected working rules, questions, candidate actions, evidence prompts, and limits are copied into the production packet so an executor receives their meaning rather than only their names.

| Principle ID | Operational use | Boundary |
| --- | --- | --- |
| `mirror` | Start from an experience the reader may recognize. | Do not invent knowledge of private audience traits. |
| `future_self` | Describe a credible direction of growth or understanding. | An intended effect is not a demonstrated transformation. |
| `messaging` | Keep one supported central claim clear. | Preserve qualifications when simplifying. |
| `enemy` | Identify the documented obstacle, practice, or claim being challenged. | Do not manufacture hostility to increase engagement. |
| `before` | Establish the starting situation and necessary context. | Do not fabricate histories or testimonials. |
| `consistency` | Preserve purpose while varying expression at a feasible cadence. | Repetition does not require identical output. |
| `polarity` | State a defensible position with reasons. | Disagreement alone does not establish usefulness. |
| `transformation` | State the useful difference the piece aims to make. | Keep intended and observed effects separate. |
| `levels` | Adjust explanation depth for different entry points. | Do not infer readiness or worth through unsupported profiling. |
| `gap` | Open an honest question and provide the promised answer. | Preserve the context necessary to understand the answer. |
| `repeated_offender` | Revisit durable ideas with fresh examples or presentation. | Do not repeat corrected claims or equate repetition with spam. |

These are editorial prompts. They do not make a true claim false because it performed poorly, or make an unsupported claim true because it attracted attention.

## Decisions and production eligibility

| Situation | Proposed action | Provisional handoff |
| --- | --- | --- |
| Planned campaign, no audience observations | `run_small_test` as an explicit hypothesis | Eligible when sources, claims, editorial assessment, and outputs are ready |
| Testing/reviewing campaign, no observations | `observe_more` | No |
| Relevant attributed misunderstanding | `clarify_message` | Bounded editorial response, with evidence limitations |
| Relevant attributed request for depth | `deepen_explanation` | Bounded editorial response, with evidence limitations |
| Comparable repeated usefulness meets the supplied plan | `repeat_theme` | Bounded repeat, without a causal-success claim |
| Explicit request to vary a hook, format, destination presentation, or explanation | Requested bounded action | Labeled creative hypothesis, subject to source/editorial readiness |
| Insufficient evidence for requested repeat/expansion | `run_small_test` | Only a bounded experiment |
| Adequate evidence plus an explicit expansion request | `expand_campaign` | No; scope, capacity, and authority need a separate governed decision |
| Explicit meaning-based lane-review request | `propose_lane_routing` | No; the existing protocol assesses fit and durable evidence |
| Mission misalignment or source-fidelity violation | `pause` | No |
| Already paused/archived | `pause` / `archive` | No; evaluation cannot resume the campaign |

The action catalog also includes `revise_hook`, `vary_format`, `adapt_platform`, and `archive`. All 12 actions are available as attributed `operator_request` values. There is no automatic campaign expansion or lane admission.

Before any handoff, every scoped source must have readable text, at least one explicit claim must be supplied, the editorial assessment must be aligned/preserved, and at least one output must be requested. Requiring explicit claims prevents the older authoring runtime's truncated fallback claim from silently dropping a later source qualification.

`review.by` and `review.reason` attribute an editorial assessment. An editor or model may supply that assessment. It is separate from human release approval. Unknown assessments block production preparation; no additional publication-approval ceremony is created for evaluation itself.

## Evidence semantics

An observation records its ID, variant ID, kind, summary, source reference, timestamp, platform, format, verification label, attributed verifier, exposures, and optional numerator/denominator metric. A label of `verified` is an attributed input. This evaluator does not authenticate the verifier, retrieve a platform report, or independently establish the report's truth.

For repeated evidence, supply all seven evaluation-plan fields: start/end window, platform, format, minimum observations, minimum exposures, and minimum distinct variants. The evaluator does not invent universal performance thresholds. Repetition additionally requires useful observations across at least two distinct declared variants. Distinct IDs and references do not establish statistical independence or unique audience reach.

- Only eligible past observations in the supplied comparable context count toward the plan. Incomplete windows cannot establish the repeat condition.
- The same exact `source_ref` counts once globally, even under a different variant ID. Use real report fragments or measurement locators for genuinely separate observations.
- Repeated snapshots of one variant contribute the maximum accepted exposure total, not a sum. Totals across variants are exposure instances; they can overlap in people.
- A later past, same-context contradiction invalidates earlier use of its reference even when the correction occurred after the original measurement window. Future-dated corrections do not change an earlier fixed-time evaluation.
- Duplicate records cannot add numerical weight, but relevant confusion, requests for depth, or conflict remain visible. Input ordering cannot hide an unfavorable qualitative observation.
- Raw performance counts, comment volume, or attention alone cannot prove usefulness, causal lift, truth, mission alignment, or a winning formula.
- The decision retains the reference and reason for every excluded observation. Weak or contradictory results are not erased to improve the outcome.

## Source, claim, and correction lineage

Source text is preserved byte-for-byte after UTF-8 encoding; leading spaces and newlines are meaningful. A supplied SHA-256 must match that exact text. A URI or content hash alone remains representable for planning but does not count as a retrieved production source.

Claim statuses (`confirmed`, `qualified`, `unverified`) remain attributed records. Unverified claims retain blocking unresolved tensions in authoring metadata. Output remains provisional even when a caller labels a claim confirmed.

The current lineage connects campaign digest → decision → source packet → pending task. Optional `lineage` also records a parent campaign digest, parent decision ID, predecessor variant IDs, corrected claim IDs, and change note. Correction entries require a parent reference and explanation. These are declared links; the evaluator does not retrieve historical records to confirm that a parent exists.

Changing source text, claims, evidence, selected principles, parent references, or other normalized context changes the campaign digest. Decisions also include the catalog digest and evaluation time. Derivative identities change with their decision. Keep previous exports, supply the new parent/correction links, and export into a new workspace. Source-to-Series must revise affected derivatives and retain their prior versions; this evaluator does not remotely retract published material.

## CLI

Run from the repository root with Python 3.12. The runtime uses the standard library. All CLI results, help, and errors are JSON. Errors go to stderr with a nonzero exit code.

Read the catalog:

```bash
python -m signal_agent.campaigns catalog
```

Evaluate the supplied illustrative source:

```bash
python -m signal_agent.campaigns evaluate --campaign examples/campaigns/exploratory_campaign.json --at 2026-11-10T00:00:00Z
```

Prepare a new local workspace:

```bash
python -m signal_agent.campaigns handoff --campaign examples/campaigns/exploratory_campaign.json --at 2026-11-10T00:00:00Z --workspace .tmp/campaigns/garden-example-01
```

Use a new destination for each export. Existing directories, path traversal, symlinked paths, and production/source locations are rejected. An optional additional repository root extends protection and cannot remove protection of the executing checkout. A failed/interrupted export may leave an incomplete new workspace; a successful receipt lists every file and its SHA-256.

Exports contain normalized context, exact source packet, the real authoring result, decision, task packet, full handoff, readable summary, and checksum manifest. The `ledgers` directory remains empty. `build_handoff` returns the same material in memory; `write_handoff` performs the guarded export.

## Local HTTP API

Start the API:

```bash
python -m signal_agent.campaigns serve --host 127.0.0.1 --port 8767
```

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | Local provisional service health |
| GET | `/api/campaigns/principles` | Versioned catalog |
| POST | `/api/campaigns/evaluate` | `campaign_decision.v1` |
| POST | `/api/campaigns/handoff` | In-memory `campaign_handoff.v1` |

Both POST routes require exactly `campaign` and `evaluated_at` in the JSON envelope. Success returns the object directly. Errors use `{"error":{"code":"...","message":"..."}}`; a 409 not-ready response includes the evaluated decision. Validation failures return 400, oversized transport bodies 413, and unknown routes 404.

The stdlib server binds to IPv4 loopback only, validates Host against its actual port, checks browser Origin/Fetch-Site, and grants no CORS access. It is a local development interface; do not expose it through a public proxy. HTTP handoff cannot choose a filesystem path. A remote Control Room needs a separately designed authenticated adapter before it can use this API.

Transport permits at most 2 MiB of UTF-8 JSON and a five-second socket I/O timeout. The core applies a stricter 1 MiB canonical-context limit, depth 12, 1,000 observations, 32 sources, 200 claims, and 32 outputs. Duplicate JSON keys, unknown fields, non-finite values, invalid counts, and naive timestamps are rejected.

## Source-to-Series execution

Provide either the complete handoff or its task packet plus the matching exact source packet to Source-to-Series. The task packet contains the selected principle guidance, working hypothesis, evidence limits, claim references, source hashes, declared correction lineage, and pending tasks.

| Task kind | Scoped deliverable |
| --- | --- |
| `short_post` | One written short post |
| `essay` | One essay draft |
| `video_script` | One video script, with any requested production directions |
| `visual_brief` | One visual brief; not a generated image receipt |
| `narration_script` | One narration script; not recorded audio |

An explicit task packet overrides ordinary series default asset counts. Finished images, audio, or video require a separately requested scope. Keep actual produced drafts and media separate from task preparation. No task packet supplies publication authority.

## Verification

Install the declared test dependencies:

```bash
python -m pip install -r requirements-campaigns-dev.txt
```

Run the focused change and governance regressions:

```bash
python -m pytest -q tests/test_campaign_decisions.py tests/test_campaign_handoff.py tests/test_campaign_transport.py tests/test_governed_authoring_backend.py tests/test_governed_authoring_workspace.py tests/test_governed_authoring_path_policy.py tests/test_formal_governance_models.py tests/test_formal_governance_decision.py tests/test_formal_governance_ledger.py tests/test_hq_transition_gate.py
```

Run the controlled local trial:

```bash
python scripts/campaign_trial.py
```

The trial uses a real CLI subprocess and loopback HTTP requests, verifies export hashes and exact source text, follows initial proposal → pending handoff → observation wait → bounded repeat → paused rejection, and removes its temporary exports. Its audience observations are explicitly synthetic. It does not claim social publication, media generation, or audience success.

Measure representative histories:

```bash
python scripts/benchmark_campaigns.py --iterations 30
```

The benchmark reports warm-call median, p95, maximum, Python allocation peaks, input size, and response size for 0, 100, and 1,000 synthetic observations. These are local measurements, not concurrent server capacity or a production SLA. CI runs the same targeted regressions, controlled trial, and bounded benchmark with read-only repository permissions and pinned action commits. It contains no deployment job.

Schemas are under `schemas/campaigns/` and reuse existing governed-authoring schemas via relative references. Resolve them locally as one schema tree. Structural schema validity does not establish factual truth or relational hash integrity; the executable validators and consumers perform those additional checks.
