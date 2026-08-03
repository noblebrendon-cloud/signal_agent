from __future__ import annotations

import hashlib
import json
from pathlib import Path

from signal_agent.corpus_import.hashing import canonical_json, sha256_file
from signal_agent.corpus_import.linkedin.key_verifier import ensure_key_verifier, load_key_context
from signal_agent.corpus_import.receipts import verify_receipt_hash
from signal_agent.relationship_signals.pipeline import run_linkedin_relationship_slice


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _packet_hash(packet: dict) -> str:
    material = dict(packet)
    material.pop("packet_hash")
    return "sha256:" + hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def test_fixed_linkedin_fixture_produces_governed_vertical_slice(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source = repository_root / "tests" / "fixtures" / "linkedin_connections" / "Connections.csv"
    content_library = repository_root / "docs" / "operator" / "content_library"
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    key_dir = tmp_path / "outside-repository-keys"
    key_dir.mkdir()
    key_file = key_dir / "acceptance.relationship-hmac.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    run_one = tmp_path / "run-one"
    run_two = tmp_path / "run-two"
    run_three = tmp_path / "run-three"
    preinitialized_repo = tmp_path / "preinitialized-repo"
    preinitialized_repo.mkdir()
    preinitialized_context = load_key_context(
        key_file,
        "acceptance-test-key-v1",
        repo_root=preinitialized_repo,
    )
    ensure_key_verifier(
        preinitialized_context,
        repo_root=preinitialized_repo,
        clock=lambda: "2000-01-01T00:00:00Z",
    )

    source_before = source.read_bytes()
    source_stat_before = source.stat()
    library_before = _tree_snapshot(content_library)

    first = run_linkedin_relationship_slice(
        source=source,
        run_root=run_one,
        hmac_key_file=key_file,
        hmac_key_id="acceptance-test-key-v1",
        repo_root=fake_repo,
        content_library_root=content_library,
        clock=lambda: FIXED_CLOCK,
    )
    second = run_linkedin_relationship_slice(
        source=source,
        run_root=run_two,
        hmac_key_file=key_file,
        hmac_key_id="acceptance-test-key-v1",
        repo_root=fake_repo,
        content_library_root=content_library,
        clock=lambda: FIXED_CLOCK,
    )
    third = run_linkedin_relationship_slice(
        source=source,
        run_root=run_three,
        hmac_key_file=key_file,
        hmac_key_id="acceptance-test-key-v1",
        repo_root=preinitialized_repo,
        content_library_root=content_library,
        clock=lambda: FIXED_CLOCK,
    )

    assert first.success is True
    assert second.success is True
    assert third.success is True
    assert source.read_bytes() == source_before
    source_stat_after = source.stat()
    assert source_stat_after.st_size == source_stat_before.st_size
    assert source_stat_after.st_mtime_ns == source_stat_before.st_mtime_ns
    assert _tree_snapshot(content_library) == library_before

    expected_paths = {
        "00_original/Connections.csv",
        "00_original/Connections.csv.sha256.txt",
        "01_normalized/relationship_records.jsonl",
        "02_analysis/unresolved_matches.json",
        "02_analysis/topic_cluster.json",
        "02_analysis/related_work.json",
        "04_packets/signal_packet.json",
        "04_packets/campaign_context_packet.json",
        "05_receipts/source_receipt.json",
        "05_receipts/run_manifest.json",
    }
    assert set(_tree_snapshot(run_one)) == expected_paths
    assert _tree_snapshot(run_one) == _tree_snapshot(run_two)
    assert _tree_snapshot(run_one) == _tree_snapshot(run_three)
    assert (run_one / "00_original" / "Connections.csv").read_bytes() == source_before
    for relative_path in sorted(expected_paths):
        if not relative_path.endswith(".json"):
            continue
        payload = (run_one / relative_path).read_bytes()
        parsed = json.loads(payload.decode("utf-8"))
        assert payload == (canonical_json(parsed) + "\n").encode("utf-8")
        assert not payload.endswith(b"\n\n")

    source_receipt = _read_json(run_one / "05_receipts" / "source_receipt.json")
    assert verify_receipt_hash(source_receipt) is True
    assert source_receipt["source"]["sha256"] == f"sha256:{sha256_file(source)}"
    assert source_receipt["source"]["byte_for_byte_equal"] is True
    assert source_receipt["source"]["observed_mtime_ns"] == source_stat_before.st_mtime_ns
    assert source_receipt["operation"] == "preserve_linkedin_connections_source"
    assert "artifacts" not in source_receipt
    assert "taxonomy" not in source_receipt
    assert "hmac" not in canonical_json(source_receipt).lower()

    records = _read_jsonl(run_one / "01_normalized" / "relationship_records.jsonl")
    normalized_bytes = (run_one / "01_normalized" / "relationship_records.jsonl").read_bytes()
    assert normalized_bytes == b"".join(
        (canonical_json(record) + "\n").encode("utf-8") for record in records
    )
    assert len(records) == 7
    assert len({record["relationship_record_id"] for record in records}) == 7
    assert [record["source_provenance"]["record_number"] for record in records] == list(range(1, 8))
    assert all(record["source_provenance"]["evidence_ref"] for record in records)
    assert all("canonical_person_id" not in record for record in records)
    assert records[0]["identifiers"][0]["kind"] == "email_hmac"
    email_token = records[0]["identifiers"][0]["value"]
    assert email_token.startswith("hmac-sha256:")
    assert records[4]["identifiers"][0]["value"] == email_token
    assert records[0]["identifiers"][1]["canonical_value"] == "https://linkedin.com/in/avery-stone"

    normalized_text = (run_one / "01_normalized" / "relationship_records.jsonl").read_text("utf-8")
    assert "shared@example.test" not in normalized_text
    assert "?trk=fixture" not in normalized_text
    for relative_path, artifact_bytes in _tree_snapshot(run_one).items():
        if relative_path == "00_original/Connections.csv":
            continue
        assert b"@example.test" not in artifact_bytes

    matches = _read_json(run_one / "02_analysis" / "unresolved_matches.json")
    assert matches["automatic_merge_performed"] is False
    assert matches["state"] == "review_required"
    assert matches["source_parse_summary"]["blank_row_count"] == 1
    assert {group["match_basis"] for group in matches["candidate_groups"]} == {
        "email_hmac_exact",
        "linkedin_profile_url_exact",
        "repeated_source_row",
    }
    assert all(group["state"] == "review_required" for group in matches["candidate_groups"])

    cluster = _read_json(run_one / "02_analysis" / "topic_cluster.json")
    assert cluster["analysis_status"] == "classified"
    assert cluster["inferred_cluster"]["confidence_state"] == "high"
    assert {item["rule_group"] for item in cluster["deterministic_matches"]} == {
        "ai_governance",
        "knowledge_systems",
        "content_infrastructure",
        "local_first_software",
    }
    assert cluster["ambiguous_matches"]
    assert cluster["unclassified_record_ids"]

    related = _read_json(run_one / "02_analysis" / "related_work.json")
    assert related["search_scope"] == "content_library_teaching_atoms_only"
    assert related["scope_complete"] is False
    assert related["results"]
    assert all(result["evidence_refs"] and result["confidence_state"] for result in related["results"])

    signal_packet = _read_json(run_one / "04_packets" / "signal_packet.json")
    campaign_packet = _read_json(run_one / "04_packets" / "campaign_context_packet.json")
    assert signal_packet["packet_hash"] == _packet_hash(signal_packet)
    assert campaign_packet["packet_hash"] == _packet_hash(campaign_packet)
    assert signal_packet["status"] == "pending_human_approval"
    assert campaign_packet["status"] == "pending_human_approval"
    assert campaign_packet["authorization"]["authorized"] is False
    assert signal_packet["related_work"]["search_scope"] == "content_library_teaching_atoms_only"
    assert signal_packet["related_work"]["scope_complete"] is False
    assert all(value is False for value in signal_packet["safety_flags"].values())
    assert all(value is False for value in campaign_packet["safety_flags"].values())

    packet_text = canonical_json(signal_packet) + canonical_json(campaign_packet)
    assert "@example.test" not in packet_text
    assert "linkedin.com/in/" not in packet_text
    assert email_token not in packet_text

    manifest = _read_json(run_one / "05_receipts" / "run_manifest.json")
    manifest_material = dict(manifest)
    manifest_material.pop("manifest_hash")
    assert manifest["manifest_hash"] == (
        "sha256:" + hashlib.sha256(canonical_json(manifest_material).encode("utf-8")).hexdigest()
    )
    assert manifest["source"]["source_receipt_file_sha256"] == (
        f"sha256:{sha256_file(run_one / '05_receipts/source_receipt.json')}"
    )
    assert all(item["path"] != "05_receipts/run_manifest.json" for item in manifest["artifacts"])
    assert manifest["canonicalization"]["artifact_hash_boundary"] == (
        "exact_persisted_bytes_including_final_newline"
    )
    assert manifest["canonicalization"]["packet_hash_boundary"] == (
        "canonical_packet_content_excluding_only_packet_hash_without_final_newline"
    )
    for item in manifest["artifacts"]:
        assert item["sha256"] == f"sha256:{sha256_file(run_one / Path(item['path']))}"

    state_files = {
        path.relative_to(fake_repo).as_posix()
        for path in fake_repo.rglob("*")
        if path.is_file()
    }
    assert state_files == {
        "data/state/relationship_identity_keys/acceptance-test-key-v1.json"
    }

    public_schemas = repository_root / "schemas" / "relationship_signals"
    schema_versions = {
        json.loads(path.read_text(encoding="utf-8"))["properties"]["schema_version"]["const"]
        for path in public_schemas.glob("*.schema.json")
    }
    assert schema_versions == {
        "signal_agent.relationship_record.v1",
        "signal_agent.relationship_signal_packet.v1",
        "signal_agent.campaign_context_packet.v1",
    }
