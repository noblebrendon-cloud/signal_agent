from __future__ import annotations

import json
from pathlib import Path

from signal_agent.operational_ingestion.canonical import (
    sha256_bytes,
    sha256_canonical,
    verify_seal,
)
from signal_agent.relationship_signals.simulated_operational_pipeline import (
    relationship_semantic_projection,
)

from .simulated_test_support import FIXED_TIME, run_case


def test_m4b_operational_compatibility_witness_is_exact(
    tmp_path: Path, repository_root: Path
) -> None:
    witness = json.loads(
        (
            repository_root
            / "tests/fixtures/operational_ingestion/compatibility_witness_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert verify_seal(witness, "witness_hash")
    result = run_case(repository_root, tmp_path)
    ingestion = result.execution.ingestion
    artifacts = []
    for root_name in ("store", "governed"):
        for path in sorted((tmp_path / root_name).rglob("*")):
            if path.is_file():
                raw = path.read_bytes()
                artifacts.append(
                    {
                        "path": path.relative_to(tmp_path).as_posix(),
                        "sha256": sha256_bytes(raw),
                        "byte_size": len(raw),
                    }
                )
    expected = {
        "attempt_outcomes": [item.outcome for item in result.execution.attempts],
        "page_count": len(result.execution.pages),
        "retry_count": result.execution.retry_count,
        "requested_delay_ms": result.execution.requested_delay_ms,
        "capture_set_hash": ingestion.boundary.payload["capture_set_hash"],
        "observation_set_hash": ingestion.boundary.payload["observation_set_hash"],
        "boundary_id": ingestion.boundary.payload["boundary_id"],
        "bounded_material_id": ingestion.bounded_material.payload["bounded_material_id"],
        "observation_index_id": ingestion.observation_index.payload["observation_index_id"],
        "candidate_id": ingestion.checkpoint_candidate.payload["candidate_id"],
        "authority_id": ingestion.completion_authority.payload["authority_id"],
        "checkpoint_id": ingestion.checkpoint_commit.payload["checkpoint_id"],
        "governed_run_id": ingestion.completed_run.run_id,
        "counts": dict(ingestion.boundary.payload["counts"]),
        "semantic_projection_hash": sha256_canonical(
            relationship_semantic_projection(tmp_path / "governed")
        ),
        "source_records_mutated": False,
        "automatic_merge_performed": False,
        "network_authorized": False,
    }
    assert witness["fixed_clock"] == FIXED_TIME
    assert artifacts == witness["artifacts"]
    assert expected == witness["expected"]
