from __future__ import annotations

import json
from pathlib import Path

from signal_agent.operational_ingestion.canonical import sha256_bytes
from signal_agent.relationship_signals.simulated_operational_pipeline import (
    relationship_semantic_projection,
)

from .simulated_test_support import normalized_records, run_case, tree


def test_finite_source_preserves_exact_bounded_bytes_and_receipt_binding(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path)
    ingestion = result.execution.ingestion
    bounded_bytes = ingestion.bounded_material.path.read_bytes()
    preserved = tmp_path / "governed/00_original/simulated_operational_bounded_source.json"
    receipt_path = tmp_path / "governed/05_receipts/simulated_operational_source_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert preserved.read_bytes() == bounded_bytes
    assert receipt["source_sha256"] == sha256_bytes(bounded_bytes)
    assert receipt["preserved_source"] == {
        "path": "00_original/simulated_operational_bounded_source.json",
        "source_sha256": sha256_bytes(bounded_bytes),
        "byte_size": len(bounded_bytes),
    }
    assert receipt["acquisition_provenance"]["capture_set_hash"] == ingestion.boundary.payload["capture_set_hash"]
    assert receipt["acquisition_provenance"]["observation_set_hash"] == ingestion.boundary.payload["observation_set_hash"]


def test_relationship_slice_completes_unchanged_downstream_stages(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path)
    required = {
        "00_original/simulated_operational_bounded_source.json",
        "01_normalized/relationship_records.jsonl",
        "02_analysis/topic_cluster.json",
        "02_analysis/related_work.json",
        "02_analysis/unresolved_matches.json",
        "04_packets/signal_packet.json",
        "04_packets/campaign_context_packet.json",
        "05_receipts/run_manifest.json",
        "05_receipts/operational_completed_manifest.json",
        "05_receipts/simulated_operational_source_receipt.json",
    }
    assert required <= set(tree(tmp_path / "governed"))
    operational_manifest = json.loads(
        (tmp_path / "governed/05_receipts/operational_completed_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert operational_manifest["completion_state"] == "completed"
    assert operational_manifest["safety_flags"] == {
        "network_authorized": False,
        "source_records_mutated": False,
        "upstream_write_authorized": False,
    }
    assert result.execution.ingestion.completed_run.run_id == operational_manifest["run_id"]


def test_change_lineage_and_tombstone_remain_immutable_normalized_effects(
    tmp_path: Path, repository_root: Path
) -> None:
    run_case(repository_root, tmp_path)
    records = normalized_records(tmp_path / "governed")
    by_kind = {}
    for record in records:
        by_kind.setdefault(record["relationship"]["observation_state"], []).append(record)
    assert len(by_kind["active"]) == 4
    assert len(by_kind["tombstone"]) == 1
    changed = [
        record
        for record in records
        if record["relationship"]["supersedes_observation_id"] is not None
    ]
    assert len(changed) == 2
    for record in changed:
        assert record["relationship"]["predecessor_content_hash"].startswith("sha256:")
        assert record["relationship"]["ordering_state"] == "provider_version_ordered"
    tombstone = by_kind["tombstone"][0]
    assert "explicit_source_tombstone" in tombstone["data_quality_issues"]
    assert tombstone["relationship"]["deletion_evidence_class"] == "explicit_simulator_tombstone"


def test_duplicate_transport_and_observation_never_duplicate_normalized_effects(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path)
    records = normalized_records(tmp_path / "governed")
    assert len(records) == 5
    assert len({item["relationship_record_id"] for item in records}) == 5
    provenance = result.execution.ingestion.boundary.payload["observation_capture_provenance"]
    assert sorted(len(value) for value in provenance.values()) == [1, 1, 1, 1, 2]


def test_transport_metadata_is_absent_from_semantic_projection(
    tmp_path: Path, repository_root: Path
) -> None:
    run_case(repository_root, tmp_path)
    projection = relationship_semantic_projection(tmp_path / "governed")
    serialized = json.dumps(projection, sort_keys=True)
    for forbidden in (
        "capture_set_hash",
        "page_ordinal",
        "attempt_ordinal",
        "retry",
        "cursor",
        "provider_request_id",
        "captured_at",
    ):
        assert forbidden not in serialized


def test_source_and_operational_outputs_are_read_only_and_non_authorizing(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path)
    before = result.execution.ingestion.bounded_material.path.read_bytes()
    records = normalized_records(tmp_path / "governed")
    assert result.execution.ingestion.bounded_material.path.read_bytes() == before
    assert all(item["privacy"]["public_export_allowed"] is False for item in records)
    all_bytes = b"".join(tree(tmp_path).values()).lower()
    assert b'"network_authorized":true' not in all_bytes
    assert b'"upstream_write_authorized":true' not in all_bytes
    assert b'"automatic_merge_performed":true' not in all_bytes
