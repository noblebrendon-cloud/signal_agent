from __future__ import annotations

import hashlib
import json
from pathlib import Path

from signal_agent.relationship_signals.interaction_event_pipeline import (
    run_interaction_event_relationship_slice,
)


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def _artifact_inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": len(path.read_bytes()),
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def test_interaction_event_output_tree_matches_fixed_ten_artifact_witness(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fixture_root = repository_root / "tests/fixtures/interaction_events"
    witness = json.loads(
        (fixture_root / "compatibility_witness_v1.json").read_text(encoding="utf-8")
    )
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(TEST_ONLY_KEY)
    run_root = tmp_path / "run"
    result = run_interaction_event_relationship_slice(
        source=fixture_root / "events.jsonl",
        run_root=run_root,
        hmac_key_file=key_file,
        hmac_key_id=witness["reference_capture"]["hmac_key_id"],
        repo_root=fake_repo,
        content_library_root=repository_root / "docs/operator/content_library",
        taxonomy_path=repository_root
        / "config/relationship_topics/governed_systems_v1.json",
        clock=lambda: FIXED_CLOCK,
    )

    actual = _artifact_inventory(run_root)
    assert len(actual) == 10
    assert actual == witness["artifacts"]
    records = [
        json.loads(line)
        for line in (
            run_root / "01_normalized/relationship_records.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    signal = json.loads((run_root / "04_packets/signal_packet.json").read_text())
    campaign = json.loads(
        (run_root / "04_packets/campaign_context_packet.json").read_text()
    )
    manifest = json.loads((run_root / "05_receipts/run_manifest.json").read_text())
    stable = witness["stable_identity"]
    assert [record["relationship_record_id"] for record in records] == stable[
        "relationship_record_ids"
    ]
    assert result.run_id == manifest["run_id"] == stable["run_id"]
    assert signal["packet_id"] == stable["signal_packet_id"]
    assert campaign["packet_id"] == stable["campaign_packet_id"]
    assert signal["packet_hash"] == stable["signal_packet_hash"]
    assert campaign["packet_hash"] == stable["campaign_packet_hash"]
    assert manifest["manifest_hash"] == stable["manifest_hash"]
