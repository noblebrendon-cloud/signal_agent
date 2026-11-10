"""Measure supplied synthetic histories; do not infer a production capacity SLA."""
from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signal_agent.campaigns import build_handoff, evaluate_campaign  # noqa: E402


EVALUATED_AT = "2026-11-10T00:00:00Z"


def synthetic_campaign(observations: int) -> dict:
    campaign = json.loads((ROOT / "examples/campaigns/exploratory_campaign.json").read_text(encoding="utf-8"))
    campaign["campaign_id"] = f"benchmark.synthetic.{observations}"
    if observations:
        campaign["phase"] = "reviewing"
        campaign["evaluation_plan"] = {
            "window_start": "2026-11-07T00:00:00Z", "window_end": "2026-11-09T00:00:00Z",
            "platform": "synthetic", "format": "short_post",
            "minimum_observations": 2, "minimum_exposures": 200,
            "minimum_independent_variants": 2,
        }
    campaign["observations"] = [{
        "observation_id": f"observation.synthetic.{i}",
        "variant_id": f"variant.synthetic.{i % 10}",
        "kind": "repeat_value", "summary": "Synthetic benchmark input; not an audience result.",
        "source_ref": f"example:synthetic/measurement/{i}",
        "observed_at": "2026-11-08T12:00:00Z", "platform": "synthetic", "format": "short_post",
        "verification": "verified", "verified_by": "synthetic-fixture",
        "exposures": 100, "metric": {"name": "example_count", "numerator": 5, "denominator": 100},
    } for i in range(observations)]
    return campaign


def measure(operation: Callable[[], dict], iterations: int) -> dict:
    operation()  # Warm caches outside the timed sample.
    timings = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        result = operation()
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ordered = sorted(timings)
    return {
        "iterations": iterations,
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        "max_ms": round(max(ordered), 3),
        "peak_traced_bytes_single_call": peak,
        "response_json_bytes": len(json.dumps(result, ensure_ascii=False).encode("utf-8")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    args = parser.parse_args()
    if not 2 <= args.iterations <= 500:
        parser.error("--iterations must be between 2 and 500")
    rows = []
    for count in (0, 100, 1000):
        campaign = synthetic_campaign(count)
        original = copy.deepcopy(campaign)
        rows.append({
            "observations": count,
            "input_json_bytes": len(json.dumps(campaign, ensure_ascii=False).encode("utf-8")),
            "evaluation": measure(lambda: evaluate_campaign(campaign, evaluated_at=EVALUATED_AT), args.iterations),
            "provisional_handoff": measure(lambda: build_handoff(campaign, evaluated_at=EVALUATED_AT), args.iterations),
        })
        if campaign != original:
            raise RuntimeError("Benchmark operation mutated its input.")
    print(json.dumps({
        "schema_version": "campaign_benchmark.v1", "mode": "synthetic_local_measurement",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "evaluation_time": EVALUATED_AT,
        "limits": "Single-process warm-call timings. Not concurrent HTTP capacity, network latency, or an SLA. Memory is Python allocations, not total RSS. No provider or audience calls.",
        "scenarios": rows,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
