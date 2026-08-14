from __future__ import annotations

import json

from signal_agent.operational_ingestion.canonical import (
    sha256_bytes,
    sha256_canonical,
    verify_seal,
)
from signal_agent.relationship_signals.gmail_history_pipeline import (
    gmail_relationship_semantic_projection,
)

from .gmail_test_support import (
    FIXED_TIME,
    REPOSITORY_ROOT,
    SECOND_TIME,
    load_projection,
    projection_path,
    run_case,
)


def test_m4c1_gmail_history_offline_compatibility_witness_is_exact(tmp_path):
    witness = json.loads(
        (
            REPOSITORY_ROOT
            / "tests/fixtures/operational_ingestion/gmail_history_compatibility_witness_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert verify_seal(witness, "witness_hash")
    bootstrap_root = tmp_path / "bootstrap-governed"
    bootstrap = run_case(
        tmp_path,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=bootstrap_root,
    )
    incremental_root = tmp_path / "incremental-governed"
    incremental = run_case(
        tmp_path,
        script_name="gmail_incremental_partition_a.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_root),
        governed_run_root=incremental_root,
    )
    artifacts = []
    for root_name in ("store", "bootstrap-governed", "incremental-governed"):
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
    assert artifacts == witness["artifacts"]
    expected = witness["expected"]
    bootstrap_execution = bootstrap.result.execution
    incremental_execution = incremental.result.execution
    bootstrap_projection = load_projection(bootstrap_root)
    incremental_projection = load_projection(incremental_root)
    bootstrap_receipt = json.loads(
        (bootstrap_root / "05_receipts/gmail_history_source_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    incremental_receipt = json.loads(
        (incremental_root / "05_receipts/gmail_history_source_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert expected["bootstrap"] == {
        "capture_set_hash": bootstrap_execution.boundary.payload["capture_set_hash"],
        "observation_set_hash": bootstrap_execution.boundary.payload[
            "observation_set_hash"
        ],
        "bounded_material_id": bootstrap_execution.bounded_material.payload[
            "bounded_material_id"
        ],
        "projection_set_hash": bootstrap_projection[
            "target_label_projection_set_hash"
        ],
        "source_receipt_id": bootstrap_receipt["receipt_id"],
        "candidate_id": bootstrap_execution.checkpoint_candidate.payload[
            "candidate_id"
        ],
        "authority_id": bootstrap_execution.completion_authority.payload[
            "authority_id"
        ],
        "checkpoint_id": bootstrap_execution.checkpoint_commit.payload[
            "checkpoint_id"
        ],
        "governed_run_id": bootstrap_execution.completed_run.run_id,
        "relationship_effect_count": len(bootstrap_projection["transitions"]),
    }
    assert expected["incremental"] == {
        "capture_set_hash": incremental_execution.boundary.payload["capture_set_hash"],
        "observation_set_hash": incremental_execution.boundary.payload[
            "observation_set_hash"
        ],
        "bounded_material_id": incremental_execution.bounded_material.payload[
            "bounded_material_id"
        ],
        "projection_set_hash": incremental_projection[
            "target_label_projection_set_hash"
        ],
        "source_receipt_id": incremental_receipt["receipt_id"],
        "candidate_id": incremental_execution.checkpoint_candidate.payload[
            "candidate_id"
        ],
        "authority_id": incremental_execution.completion_authority.payload[
            "authority_id"
        ],
        "checkpoint_id": incremental_execution.checkpoint_commit.payload[
            "checkpoint_id"
        ],
        "governed_run_id": incremental_execution.completed_run.run_id,
        "relationship_effect_count": len(incremental_projection["transitions"]),
        "unresolved_relevance_count": len(
            incremental_projection["unresolved_relevance"]
        ),
        "semantic_projection_hash": sha256_canonical(
            gmail_relationship_semantic_projection(incremental_root)
        ),
    }
    assert expected["safety"] == {
        "authentication_authorized": False,
        "automatic_merge_performed": False,
        "gmail_write_authorized": False,
        "live_mailbox_access_authorized": False,
        "network_authorized": False,
        "oauth_authorized": False,
        "source_records_mutated": False,
    }
    assert witness["fixed_clocks"] == [FIXED_TIME, SECOND_TIME]
