from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from signal_agent.formal_governance.ledger import read_ledger_entries
from signal_agent.governed_authoring.demo_bundle import (
    CANONICAL_LEDGER_FILENAME,
    DEMO_FIXTURES,
    PROOF_SUMMARY_FILENAME,
    ROOT,
    run_demo_bundle,
)


DEMO_BUNDLE = ROOT / "signal_agent" / "governed_authoring" / "demo_bundle.py"


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = ROOT / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _result_path(out_dir: Path, fixture_name: str) -> Path:
    return out_dir / f"{Path(fixture_name).stem}.result.json"


def _run_demo_cli(out_dir: Path, *, canonical_ledger: bool = False) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [
        sys.executable,
        "-m",
        "signal_agent.governed_authoring.demo_bundle",
        "--out",
        str(out_dir),
    ]
    if canonical_ledger:
        command.append("--canonical-ledger")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    return completed, payload


def test_demo_bundle_writes_result_packets_and_proof_summary(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle"

    summary = run_demo_bundle(out_dir)

    assert summary["passed"] is True
    assert Path(summary["proof_summary_path"]) == out_dir.resolve() / PROOF_SUMMARY_FILENAME
    assert (out_dir / PROOF_SUMMARY_FILENAME).exists()
    assert len(summary["results"]) == len(DEMO_FIXTURES)
    for fixture in DEMO_FIXTURES:
        path = _result_path(out_dir, fixture.filename)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "governed_authoring.prototype_result.v1"
        assert payload["output_status"] == fixture.expected_status
        assert payload["review_status"] == fixture.expected_review_status


def test_demo_bundle_summary_records_expected_actual_and_packet_paths(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle"

    summary = run_demo_bundle(out_dir)

    for entry in summary["results"]:
        assert entry["pass"] is True
        assert entry["expected_result"] == entry["actual_result"]
        assert Path(entry["output_packet_path"]).is_file()

    proof_summary = (out_dir / PROOF_SUMMARY_FILENAME).read_text(encoding="utf-8")
    for fixture in DEMO_FIXTURES:
        assert fixture.filename in proof_summary
        assert fixture.expected_status in proof_summary


def test_demo_bundle_preserves_evidence_refs_tensions_review_and_output_status(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle"

    summary = run_demo_bundle(out_dir)

    approved = next(entry for entry in summary["results"] if entry["fixture_name"] == "static_export_valid_approved.json")
    deferred = next(entry for entry in summary["results"] if entry["fixture_name"] == "static_export_blocking_tension.json")

    assert approved["evidence_refs"] == ["evidence:prototype.source.offline.001"]
    assert approved["review_status"] == "Approved by backend review"
    assert approved["output_status"] == "approved"
    assert approved["unresolved_tensions"][0]["blocking"] is False
    assert deferred["evidence_refs"] == ["evidence:prototype.source.offline.002"]
    assert deferred["review_status"] == "Deferred by backend review"
    assert deferred["output_status"] == "deferred"
    assert deferred["unresolved_tensions"][0]["blocking"] is True


def test_demo_bundle_optional_canonical_ledger_is_inside_output_directory(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle"

    summary = run_demo_bundle(out_dir, canonical_ledger=True)

    canonical_ledger_path = out_dir.resolve() / CANONICAL_LEDGER_FILENAME
    assert summary["canonical_ledger_enabled"] is True
    assert Path(summary["canonical_ledger_path"]) == canonical_ledger_path
    assert canonical_ledger_path.exists()
    assert canonical_ledger_path.resolve().is_relative_to(out_dir.resolve())
    entries = read_ledger_entries(canonical_ledger_path)
    assert len(entries) == len(DEMO_FIXTURES)
    assert all(entry["canonical_ledger_entry_present"] for entry in summary["results"])


def test_demo_bundle_cli_writes_temp_outputs_and_reports_summary(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle_cli"

    completed, payload = _run_demo_cli(out_dir, canonical_ledger=True)

    assert completed.returncode == 0, completed.stderr
    assert payload["schema_version"] == "governed_authoring.demo_proof_bundle.v1"
    assert payload["passed"] is True
    assert (out_dir / PROOF_SUMMARY_FILENAME).exists()
    assert (out_dir / CANONICAL_LEDGER_FILENAME).exists()
    for fixture in DEMO_FIXTURES:
        assert _result_path(out_dir, fixture.filename).exists()


def test_demo_bundle_does_not_modify_production_jsonl_ledgers(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()

    run_demo_bundle(tmp_path / "demo_bundle")
    run_demo_bundle(tmp_path / "demo_bundle_with_ledger", canonical_ledger=True)

    assert _production_jsonl_snapshot() == before


def test_demo_bundle_rejects_output_under_production_data(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    out_dir = ROOT / "data" / f"governed_authoring_demo_bundle_test_{tmp_path.name}"

    completed, _payload = _run_demo_cli(out_dir)

    assert completed.returncode != 0
    assert "must not be under production data/" in completed.stderr
    assert not out_dir.exists()
    assert _production_jsonl_snapshot() == before


def test_demo_bundle_rejects_existing_output_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "demo_bundle"
    out_dir.mkdir()
    existing = out_dir / "proof_summary.md"
    existing.write_text("existing\n", encoding="utf-8")

    completed, _payload = _run_demo_cli(out_dir)

    assert completed.returncode != 0
    assert "output files already exist" in completed.stderr
    assert existing.read_text(encoding="utf-8") == "existing\n"


def test_demo_bundle_introduces_no_network_or_server_surface() -> None:
    text = DEMO_BUNDLE.read_text(encoding="utf-8")
    forbidden_tokens = [
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "http.server",
        "socket",
        "requests",
        "urllib",
        "FastAPI",
        "Flask",
        "listen(",
    ]

    for token in forbidden_tokens:
        assert token not in text


def test_demo_bundle_introduces_no_production_authoring_artifact_path() -> None:
    text = DEMO_BUNDLE.read_text(encoding="utf-8")
    forbidden_fragments = [
        "data/governed_authoring",
        "data/authoring",
        "data/outputs/governed_authoring",
        "data/outputs/authoring",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in text.replace("\\", "/")
