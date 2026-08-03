from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from signal_agent.corpus_import.hashing import canonical_json
from signal_agent.relationship_signals.pipeline import run_linkedin_relationship_slice


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)
PLACEHOLDER = "${RESOLVED_FIXTURE_SOURCE_PATH}"
SOURCE_RECEIPT_PATH = "05_receipts/source_receipt.json"
SIGNAL_PACKET_PATH = "04_packets/signal_packet.json"
CAMPAIGN_PACKET_PATH = "04_packets/campaign_context_packet.json"
MANIFEST_PATH = "05_receipts/run_manifest.json"


def _canonical_bytes(payload: object) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sealed_hash(payload: dict, field: str) -> str:
    material = deepcopy(payload)
    material.pop(field)
    return "sha256:" + hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _materialize_expected_tree(witness: dict, resolved_source_path: str) -> dict[str, bytes]:
    serialized_witness = json.dumps(witness, ensure_ascii=False, sort_keys=True)
    assert serialized_witness.count(PLACEHOLDER) == 1
    entries = {item["path"]: item for item in witness["artifacts"]}
    expected = {
        path: (
            item["content_template"].encode("utf-8")
            if item["content_encoding"] == "utf-8-template"
            else base64.b64decode(item["content_template"], validate=True)
        )
        for path, item in entries.items()
    }

    receipt_template = entries[SOURCE_RECEIPT_PATH]["content_template"]
    assert receipt_template.count(PLACEHOLDER) == 1
    receipt = json.loads(receipt_template)
    assert receipt["source"]["observed_path"] == PLACEHOLDER
    receipt["source"]["observed_path"] = resolved_source_path
    receipt["receipt_hash"] = _sealed_hash(receipt, "receipt_hash")
    expected[SOURCE_RECEIPT_PATH] = _canonical_bytes(receipt)

    signal = json.loads(expected[SIGNAL_PACKET_PATH].decode("utf-8"))
    signal["source"]["source_receipt_hash"] = receipt["receipt_hash"]
    signal["packet_hash"] = _sealed_hash(signal, "packet_hash")
    expected[SIGNAL_PACKET_PATH] = _canonical_bytes(signal)

    campaign = json.loads(expected[CAMPAIGN_PACKET_PATH].decode("utf-8"))
    campaign["source_signal_packet"]["packet_hash"] = signal["packet_hash"]
    campaign["source_signal_packet"]["file_sha256"] = _sha256(
        expected[SIGNAL_PACKET_PATH]
    )
    campaign["packet_hash"] = _sealed_hash(campaign, "packet_hash")
    expected[CAMPAIGN_PACKET_PATH] = _canonical_bytes(campaign)

    manifest = json.loads(expected[MANIFEST_PATH].decode("utf-8"))
    manifest["source"]["source_receipt_hash"] = receipt["receipt_hash"]
    manifest["source"]["source_receipt_file_sha256"] = _sha256(
        expected[SOURCE_RECEIPT_PATH]
    )
    dependent_artifact_hashes = {
        SIGNAL_PACKET_PATH: _sha256(expected[SIGNAL_PACKET_PATH]),
        CAMPAIGN_PACKET_PATH: _sha256(expected[CAMPAIGN_PACKET_PATH]),
    }
    for artifact in manifest["artifacts"]:
        if artifact["path"] in dependent_artifact_hashes:
            artifact["sha256"] = dependent_artifact_hashes[artifact["path"]]
    manifest["manifest_hash"] = _sealed_hash(manifest, "manifest_hash")
    expected[MANIFEST_PATH] = _canonical_bytes(manifest)
    return expected


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_linkedin_output_tree_matches_materialized_pre_refactor_witness(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fixture_root = repository_root / "tests/fixtures/linkedin_connections"
    source = (fixture_root / "Connections.csv").resolve(strict=True)
    witness = json.loads(
        (fixture_root / "compatibility_witness_v1.json").read_text(encoding="utf-8")
    )

    reference_expected = _materialize_expected_tree(
        witness,
        witness["reference_capture"]["observed_source_path"],
    )
    entries = {item["path"]: item for item in witness["artifacts"]}
    for path, payload in reference_expected.items():
        assert len(payload) == entries[path]["reference_size_bytes"]
        assert _sha256(payload) == entries[path]["reference_sha256"]

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "acceptance.relationship-hmac.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    run_root = tmp_path / "run"
    result = run_linkedin_relationship_slice(
        source=source,
        run_root=run_root,
        hmac_key_file=key_file,
        hmac_key_id=witness["reference_capture"]["hmac_key_id"],
        repo_root=fake_repo,
        content_library_root=repository_root / "docs/operator/content_library",
        clock=lambda: FIXED_CLOCK,
    )

    actual = _tree(run_root)
    expected = _materialize_expected_tree(witness, str(source))
    assert set(actual) == set(expected) == set(entries)
    assert actual == expected
    assert not (run_root / ".staging").exists()

    for path, payload in actual.items():
        assert len(payload) == len(expected[path])
        assert _sha256(payload) == _sha256(expected[path])
        schema_version = entries[path].get("schema_version")
        if schema_version:
            if entries[path]["media_type"] == "application/x-ndjson":
                parsed = json.loads(payload.decode("utf-8").splitlines()[0])
            else:
                parsed = json.loads(payload.decode("utf-8"))
            assert parsed["schema_version"] == schema_version

    receipt = json.loads(actual[SOURCE_RECEIPT_PATH].decode("utf-8"))
    records = [
        json.loads(line)
        for line in actual["01_normalized/relationship_records.jsonl"]
        .decode("utf-8")
        .splitlines()
    ]
    signal = json.loads(actual[SIGNAL_PACKET_PATH].decode("utf-8"))
    campaign = json.loads(actual[CAMPAIGN_PACKET_PATH].decode("utf-8"))
    manifest = json.loads(actual[MANIFEST_PATH].decode("utf-8"))
    identity = witness["stable_identity"]
    assert receipt["source"]["observed_path"] == str(source)
    assert [record["relationship_record_id"] for record in records] == identity[
        "relationship_record_ids"
    ]
    assert result.run_id == manifest["run_id"] == identity["run_id"]
    assert signal["packet_id"] == identity["signal_packet_id"]
    assert campaign["packet_id"] == identity["campaign_packet_id"]
    if str(source) == witness["reference_capture"]["observed_source_path"]:
        assert signal["packet_hash"] == identity["signal_packet_hash"]
        assert campaign["packet_hash"] == identity["campaign_packet_hash"]
        assert manifest["manifest_hash"] == identity["manifest_hash"]
