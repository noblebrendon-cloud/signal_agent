"""
OIL -- End-to-End Analysis Runner (v0.4.1)

v0.4.1 DIM improvements:
  - write_artifact now returns (Path, run_id)
  - run_id passed to append_entry and find_similar for stable self-exclusion
  - one memory entry per CLI invocation (load_index dedupes by run_id)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent
_DEFAULT_ARTIFACTS_DIR = _OIL_ROOT / "artifacts"
_DEFAULT_GRAPH = _OIL_ROOT / "graph" / "sample_graph.json"
_DEFAULT_MEMORY_INDEX = _OIL_ROOT / "memory" / "index.jsonl"


def _load_telemetry(source: str) -> list[dict]:
    if source == "mock":
        from oil.intake.mock_telemetry import MOCK_EVENTS
        return MOCK_EVENTS
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Telemetry file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    raise ValueError("Telemetry JSON must be a list of event dicts")


def _compute_outcome_summary(matches: list[dict], outcomes: dict[str, list[dict]]) -> dict:
    """Join similar incidents to their outcomes and compute aggregate rates.

    v0.7: counts only the final outcome per run_id (via select_final_outcome),
    so each prior incident contributes exactly one outcome to the summary.
    """
    from oil.memory.outcomes import select_final_outcome
    total_with_outcomes = 0
    counts: dict[str, int] = {"resolved": 0, "mitigated": 0, "false_positive": 0, "ignored": 0}

    for m in matches:
        rid = m.get("run_id", "")
        if rid and rid in outcomes:
            final = select_final_outcome(outcomes[rid])
            if final:
                total_with_outcomes += 1
                kind = final.get("outcome_kind", "")
                if kind in counts:
                    counts[kind] += 1

    total = total_with_outcomes
    resolved_rate = counts["resolved"] / total if total > 0 else 0.0
    return {
        "total_with_outcomes": total,
        "resolved_rate":       round(resolved_rate, 4),
        "counts":              counts,
    }


def _build_similar_incidents_block(
    matches: list[dict],
    outcomes: dict[str, list[dict]] | None = None,
) -> dict:
    if not matches:
        return {
            "occurrence_count": 0,
            "most_common_origin": "",
            "most_common_action_category": "",
            "recent_examples": [],
            "outcome_summary": None,
        }
    from collections import Counter
    origin_counts = Counter(m.get("origin_service", "") for m in matches)
    most_common = origin_counts.most_common(1)[0][0] if origin_counts else ""
    # v0.5: action category summary
    action_counts = Counter(
        m.get("action_category", "") for m in matches if m.get("action_category", "")
    )
    most_common_action = action_counts.most_common(1)[0][0] if action_counts else ""
    recent = sorted(matches, key=lambda m: m.get("created_utc", ""), reverse=True)[:5]
    # v0.6: outcome summary (None if no outcomes loaded)
    outcome_summary = _compute_outcome_summary(matches, outcomes) if outcomes else None
    return {
        "occurrence_count": len(matches),
        "most_common_origin": most_common,
        "most_common_action_category": most_common_action,
        "recent_examples": recent,
        "outcome_summary": outcome_summary,
    }


def run(
    telemetry_source: str,
    graph_path: Path,
    reference_service: str,
    artifacts_dir: Path,
    memory_index: Path | None = None,
) -> dict:
    """Execute the full OIL pipeline and return the incident report."""
    from oil.cases.writer import write_case
    from oil.correlation.ranker import rank_hypotheses, select_reference
    from oil.explanation.generator import format_human_block, generate_explanation
    from oil.explanation.reporter import compute_inputs_digest, write_artifact
    from oil.graph.loader import load_graph
    from oil.impact.mapper import load_impact_map
    from oil.intake.normalizer import normalize_events
    from oil.memory.actions import extract_action
    from oil.memory.fingerprint import generate_fingerprint
    from oil.memory.outcomes import load_outcomes
    from oil.memory.store import append_entry, find_similar, load_index

    index_path = memory_index or _DEFAULT_MEMORY_INDEX

    # 1. Intake
    raw_events = _load_telemetry(telemetry_source)
    events = normalize_events(raw_events)

    # 2. Graph
    graph = load_graph(graph_path)

    # 3. Correlation
    if not events:
        raise ValueError("No events to analyse after normalization")

    reference_ts = select_reference(events, reference_service)
    hypotheses = rank_hypotheses(
        events=events,
        graph=graph,
        reference_ts=reference_ts,
        reference_service=reference_service,
    )

    # 4. Impact
    impact_map = load_impact_map()

    # 5. Inputs digest
    graph_dicts = {k: {"upstream": v.upstream, "downstream": v.downstream} for k, v in graph.items()}
    inputs_digest = compute_inputs_digest(raw_events, graph_dicts, impact_map)

    # 6. Explanation
    report = generate_explanation(
        hypotheses=hypotheses,
        events=events,
        impact_map=impact_map,
        reference_service=reference_service,
    )

    # 7. Artifact write (v0.4.1: returns (path, run_id))
    artifact_path, run_id = write_artifact(report, artifacts_dir, inputs_digest=inputs_digest)
    report["_artifact_path"] = str(artifact_path)
    report["_run_id"] = run_id

    # 8. DIM: fingerprint + memory index (one entry per invocation)
    top = hypotheses[0] if hypotheses else None
    fingerprint_id = generate_fingerprint(report, hypotheses)

    # v0.5: deterministic action extraction
    action = extract_action(report, top.origin_service if top else "")

    append_entry(
        fingerprint_id=fingerprint_id,
        artifact_path=str(artifact_path),
        origin_service=top.origin_service if top else "",
        change_kind=top.origin_change_kind if top else "",
        metric_kind=report.get("primary_metric_kind", ""),
        hop_distance_class=report.get("hop_distance_class", "unknown"),
        impact_domain=report.get("impact_domain", ""),
        confidence=report.get("confidence_score", 0.0),
        index_path=index_path,
        run_id=run_id,
        action_category=action["action_category"],
        action_target_service=action["action_target_service"],
        fallback_action_category=action["fallback_action_category"],
    )

    # 9. Similarity lookup and outcome join (self-excluded by run_id)
    index = load_index(index_path)
    matches = find_similar(
        fingerprint_id=fingerprint_id,
        index=index,
        top_n=5,
        current_run_id=run_id,
    )

    # v0.6: load outcomes for recall summary
    outcomes_path = index_path.parent / "outcomes.jsonl"
    outcomes = load_outcomes(outcomes_path)

    # 10. Attach similar_incidents and render
    report["similar_incidents"] = _build_similar_incidents_block(matches, outcomes)

    print(format_human_block(report))
    if top and top.change_biased:
        print("[change_biased] +0.10 bonus applied -- change event detected for top origin.")
    print(f"\nArtifact written: {artifact_path}")
    print(f"Memory index:     {index_path}  (fingerprint: {fingerprint_id}, run_id: {run_id})")

    # v0.7: write case bundle
    _human_block = format_human_block(report)   # already printed above
    # find this run's memory_line from the index (last entry with matching run_id)
    this_memory_line: dict = {}
    for entry in reversed(load_index(index_path)):
        if entry.get("run_id") == run_id:
            this_memory_line = entry
            break
    outcomes_for_run = outcomes.get(run_id, [])
    case_dir = write_case(
        run_id=run_id,
        artifact_path=artifact_path,
        memory_line=this_memory_line,
        outcomes_for_run=outcomes_for_run,
        human_block=_human_block,
    )
    print(f"Case bundle:      {case_dir}")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oil.run_analysis",
        description="OIL -- Operational Intelligence Layer analysis runner",
    )
    parser.add_argument("--telemetry", default="mock")
    parser.add_argument("--graph", default=str(_DEFAULT_GRAPH))
    parser.add_argument("--reference-service", default="checkout")
    parser.add_argument("--artifacts-dir", default=str(_DEFAULT_ARTIFACTS_DIR))
    args = parser.parse_args(argv)
    try:
        run(
            telemetry_source=args.telemetry,
            graph_path=Path(args.graph),
            reference_service=args.reference_service,
            artifacts_dir=Path(args.artifacts_dir),
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
