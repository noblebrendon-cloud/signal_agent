from __future__ import annotations

import json
import ast
import inspect
from copy import deepcopy
from pathlib import Path

import pytest

from signal_agent.corpus_import.linkedin.key_verifier import (
    LinkedInKeyError,
    ensure_key_verifier,
    load_key_context,
)
from signal_agent.corpus_import.linkedin.importer import build_linkedin_import_plan
from signal_agent.relationship_signals.pipeline import run_linkedin_relationship_slice
from signal_agent.relationship_signals import packets


FIXED_CLOCK = "2026-08-02T12:00:00Z"
KEY_ONE = b"a" * 32
KEY_TWO = b"b" * 32


def _key_context(tmp_path: Path, fake_repo: Path, key_id: str, material: bytes):
    key_dir = tmp_path / f"keys-{key_id}-{material[:1].hex()}"
    key_dir.mkdir()
    key_path = key_dir / "identity.relationship-hmac.key"
    key_path.write_bytes(material)
    return load_key_context(key_path, key_id, repo_root=fake_repo)


def test_key_verifier_fails_closed_and_key_ids_are_separate_namespaces(tmp_path: Path) -> None:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    first = _key_context(tmp_path, fake_repo, "key-one", KEY_ONE)
    second_id = _key_context(tmp_path, fake_repo, "key-two", KEY_TWO)
    same_id_wrong_material = _key_context(tmp_path, fake_repo, "key-one", KEY_TWO)

    first_path = ensure_key_verifier(first, repo_root=fake_repo, clock=lambda: FIXED_CLOCK)
    second_path = ensure_key_verifier(second_id, repo_root=fake_repo, clock=lambda: FIXED_CLOCK)
    first_bytes = first_path.read_bytes()

    assert first_path != second_path
    with pytest.raises(LinkedInKeyError, match="linkedin_key_id_material_mismatch"):
        ensure_key_verifier(same_id_wrong_material, repo_root=fake_repo)
    assert first_path.read_bytes() == first_bytes

    record = json.loads(first_path.read_text(encoding="utf-8"))
    record.pop("verifier_tag")
    first_path.write_text(json.dumps(record), encoding="utf-8")
    corrupt_bytes = first_path.read_bytes()
    with pytest.raises(LinkedInKeyError, match="linkedin_key_verifier_metadata_missing"):
        ensure_key_verifier(first, repo_root=fake_repo)
    assert first_path.read_bytes() == corrupt_bytes

    second_record = json.loads(second_path.read_text(encoding="utf-8"))
    second_record["verifier_tag"] = "hmac-sha256:" + ("0" * 64)
    second_path.write_text(json.dumps(second_record), encoding="utf-8")
    corrupt_bytes = second_path.read_bytes()
    with pytest.raises(LinkedInKeyError, match="linkedin_key_verifier_corrupt"):
        ensure_key_verifier(second_id, repo_root=fake_repo)
    assert second_path.read_bytes() == corrupt_bytes


def test_relationship_hmac_key_must_be_external_regular_and_at_least_32_bytes(
    tmp_path: Path,
) -> None:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    inside = fake_repo / "inside.relationship-hmac.key"
    inside.write_bytes(KEY_ONE)
    with pytest.raises(LinkedInKeyError, match="must_be_outside_repository"):
        load_key_context(inside, "key-one", repo_root=fake_repo)

    outside = tmp_path / "short.relationship-hmac.key"
    outside.write_bytes(b"too-short")
    with pytest.raises(LinkedInKeyError, match="material_too_short"):
        load_key_context(outside, "key-one", repo_root=fake_repo)


def test_insufficient_cluster_is_successful_and_packets_remain_unauthorized(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    source = tmp_path / "Connections.csv"
    source.write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Morgan,One,https://linkedin.com/in/morgan-one,morgan@example.test,AI Governance Lab,Advisor,01 Jan 2026\n"
        "Taylor,Two,https://linkedin.com/in/taylor-two,taylor@example.test,Content Studio,Strategist,02 Jan 2026\n",
        encoding="utf-8",
        newline="",
    )
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    key_file = key_dir / "test.relationship-hmac.key"
    key_file.write_bytes(KEY_ONE)
    result = run_linkedin_relationship_slice(
        source=source,
        run_root=tmp_path / "run",
        hmac_key_file=key_file,
        hmac_key_id="insufficient-key",
        repo_root=fake_repo,
        content_library_root=repository_root / "docs" / "operator" / "content_library",
        clock=lambda: FIXED_CLOCK,
    )

    assert result.success is True
    assert result.cluster_confidence_state == "insufficient"
    cluster = json.loads((result.run_root / "02_analysis/topic_cluster.json").read_text("utf-8"))
    signal = json.loads((result.run_root / "04_packets/signal_packet.json").read_text("utf-8"))
    campaign = json.loads(
        (result.run_root / "04_packets/campaign_context_packet.json").read_text("utf-8")
    )
    assert cluster["analysis_status"] == "insufficient"
    assert cluster["inferred_cluster"]["supporting_record_count"] == 1
    assert signal["status"] == "pending_human_approval"
    assert campaign["context_readiness"] == "insufficient_evidence"
    assert campaign["authorization"] == {
        "authorized": False,
        "authorization_scope": "none",
        "approval_id": None,
        "human_approval_required": True,
    }
    assert all(value is False for value in signal["safety_flags"].values())
    assert all(value is False for value in campaign["safety_flags"].values())

    altered_signal_hash = deepcopy(signal)
    altered_signal_hash["packet_hash"] = "sha256:" + ("0" * 64)
    resealed_campaign = packets.build_campaign_context_packet(
        created_at=FIXED_CLOCK,
        signal_packet=altered_signal_hash,
        signal_packet_path="04_packets/signal_packet.json",
        signal_packet_file_sha256="0" * 64,
    )
    assert resealed_campaign["packet_id"] == campaign["packet_id"]
    assert resealed_campaign["packet_hash"] != campaign["packet_hash"]


def test_packet_builders_have_no_raw_linkedin_import_dependency() -> None:
    source = inspect.getsource(packets)
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "csv" not in imported_modules
    assert not any(name and name.startswith("signal_agent.corpus_import.linkedin") for name in imported_modules)


def test_incomplete_invalid_row_is_preserved_as_a_distinct_record(tmp_path: Path) -> None:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    context = _key_context(tmp_path, fake_repo, "invalid-row-key", KEY_ONE)
    source = tmp_path / "invalid-connections.csv"
    source.write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        ",,not-a-linkedin-url,not-an-email,,,not-a-date\n",
        encoding="utf-8",
        newline="",
    )

    plan = build_linkedin_import_plan(
        source,
        key_context=context,
        clock=lambda: FIXED_CLOCK,
    )

    assert len(plan.records) == 1
    record = plan.records[0]
    assert record["identifiers"] == []
    assert set(record["data_quality_issues"]) == {
        "company_missing",
        "connected_on_unparsed",
        "invalid_email",
        "invalid_linkedin_profile_url",
        "name_missing",
        "position_missing",
    }
    assert record["source_provenance"]["record_number"] == 1
    assert record["deterministic_classification"]["field_presence"]["url"] is True
