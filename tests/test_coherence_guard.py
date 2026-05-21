import json
import os
from pathlib import Path
from unittest.mock import patch

from app.hq.capture.router import route_bundle
from shared.coherence import check_artifact_coherence, check_path_coherence
from shared.events import _default_event_log_path
from shared.inspect import coherence_status
from shared.state_registry import record_state


def test_coherence_guard_success(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    artifact_path = tmp_path / "test_doc.md"
    artifact_path.write_text("dummy")

    record_state("test_doc.md", "promoted", str(artifact_path), registry_path=registry_path)

    res = check_artifact_coherence("test_doc.md", expected_state="promoted", registry_path=registry_path)
    assert res["coherent"] is True
    assert res["reason"] == "coherent"

    res_path = check_path_coherence(artifact_path, expected_state="promoted", registry_path=registry_path)
    assert res_path["coherent"] is True


def test_coherence_guard_missing_registry(tmp_path):
    registry_path = tmp_path / "registry.jsonl" # missing

    res = check_artifact_coherence("test_doc.md", expected_state="promoted", registry_path=registry_path)
    assert res["coherent"] is False
    assert res["reason"] == "missing_registry_entry"


def test_coherence_guard_missing_filesystem(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    artifact_path = tmp_path / "test_doc.md" # not created

    record_state("test_doc.md", "promoted", str(artifact_path), registry_path=registry_path)

    res = check_artifact_coherence("test_doc.md", expected_state="promoted", registry_path=registry_path)
    assert res["coherent"] is False
    assert res["reason"] == "missing_filesystem_artifact"


def test_coherence_guard_state_mismatch(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    artifact_path = tmp_path / "test_doc.md"
    artifact_path.write_text("dummy")

    record_state("test_doc.md", "captured", str(artifact_path), registry_path=registry_path)

    res = check_artifact_coherence("test_doc.md", expected_state="promoted", registry_path=registry_path)
    assert res["coherent"] is False
    assert res["reason"] == "state_mismatch"


def test_coherence_guard_hash_success(tmp_path):
    import hashlib
    registry_path = tmp_path / "registry.jsonl"
    artifact_path = tmp_path / "test_hash.md"
    content = b"hashed content"
    artifact_path.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()

    record_state("test_hash.md", "promoted", str(artifact_path), registry_path=registry_path)

    res = check_artifact_coherence(
        "test_hash.md",
        expected_state="promoted",
        expected_hash=expected_hash,
        registry_path=registry_path
    )
    assert res["coherent"] is True
    assert res["reason"] == "coherent"


def test_coherence_guard_hash_mismatch(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    artifact_path = tmp_path / "test_hash.md"
    artifact_path.write_bytes(b"modified content")

    record_state("test_hash.md", "promoted", str(artifact_path), registry_path=registry_path)

    res = check_artifact_coherence(
        "test_hash.md",
        expected_state="promoted",
        expected_hash="invalidhashxxx",
        registry_path=registry_path
    )
    assert res["coherent"] is False
    assert res["reason"] == "content_mismatch"


@patch("app.hq.capture.router._resolve_contract")
def test_router_enforces_coherence_failure(mock_resolve, tmp_path, monkeypatch):
    mock_resolve.return_value = {
        "contract_source": "registry",
        "confidence": 1.0,
        "routable": True,
    }

    registry_path = tmp_path / "registry.jsonl"
    # missing file in reality for coherence failure
    # but the router inputs the 'bundle_path' that is given to it.
    # to fail coherence via 'missing_registry_entry', we just do not write to registry!

    # We must patch get_state globally or inside router so that it uses our registry path.
    # Actually, we can patch `check_artifact_coherence` default via env var or mock.
    # Router does not pass registry_path to check_artifact_coherence, which uses default.
    # We will override the default base dir.
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))

    bundle_path = tmp_path / "bundle.md"
    bundle_path.write_text("hello keywords")

    spines_dir = tmp_path / "spines"
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir()
    config_path = tmp_path / "spine_router.yaml"
    config_path.write_text("- name: default\n  keywords: [hello]\n")

    # Routing
    res = route_bundle(
        bundle_path=bundle_path,
        dry_run=False,
        config_path=config_path,
        capture_dir=capture_dir,
        spines_dir=spines_dir,
    )

    assert res["status"] == "fail"
    assert "coherence check failed" in res["error"]
    assert "coherence" in res
    assert res["coherence"]["reason"] == "missing_registry_entry"
    assert res["coherence"]["coherent"] is False

    # Check that it did NOT copy
    assert not (spines_dir / "default" / "incoming" / "bundle.md").exists()

    # Verify CoherenceCheckFailed event emitted
    event_log = tmp_path / "data" / "state" / "event_log.jsonl"
    assert event_log.exists()
    events = [json.loads(line) for line in event_log.read_text().splitlines()]
    coherence_events = [e for e in events if e["event_type"] == "CoherenceCheckFailed"]
    assert len(coherence_events) == 1
    assert coherence_events[0]["payload"]["reason"] == "missing_registry_entry"

    routing_log = capture_dir / "routing_log.jsonl"
    logged_routes = [json.loads(x) for x in routing_log.read_text().splitlines()]
    assert logged_routes[-1]["status"] == "fail"


def test_inspect_coherence_status(tmp_path):
    registry_path = tmp_path / "registry.jsonl"
    res = coherence_status("test_doc.md", "promoted", registry_path)
    assert res["coherent"] is False
    assert res["reason"] == "missing_registry_entry"
