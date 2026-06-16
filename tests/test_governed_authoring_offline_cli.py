from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from signal_agent.formal_governance.ledger import read_ledger_entries


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governed_authoring"
CLI = ROOT / "signal_agent" / "governed_authoring" / "cli.py"


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = ROOT / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _run_cli(
    fixture_name: str,
    output_path: Path,
    *,
    canonical_ledger_path: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [
        sys.executable,
        "-m",
        "signal_agent.governed_authoring.cli",
        "verify-static-export",
        "--input",
        str(FIXTURES / fixture_name),
        "--output",
        str(output_path),
    ]
    if canonical_ledger_path is not None:
        command.extend(["--canonical-ledger", str(canonical_ledger_path)])

    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    return completed, payload


def _assert_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().startswith("{")


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_review_status"),
    [
        ("static_export_valid_provisional.json", "provisional", "Provisional backend draft"),
        ("static_export_valid_approved.json", "approved", "Approved by backend review"),
        ("static_export_missing_evidence.json", "rejected", "Rejected by backend review"),
        ("static_export_blocking_tension.json", "deferred", "Deferred by backend review"),
        ("static_export_generator_self_approval.json", "rejected", "Rejected by backend review"),
    ],
)
def test_cli_writes_static_import_compatible_result_for_fixture_outcomes(
    tmp_path: Path,
    fixture_name: str,
    expected_status: str,
    expected_review_status: str,
) -> None:
    output_path = tmp_path / "results" / f"{fixture_name}.result.json"

    completed, payload = _run_cli(fixture_name, output_path)

    _assert_success(completed)
    assert payload["schema_version"] == "governed_authoring.prototype_result.v1"
    assert payload["output_status"] == expected_status
    assert payload["review_status"] == expected_review_status
    assert payload == json.loads(completed.stdout)


def test_cli_preserves_evidence_refs_review_status_and_nonblocking_tension(tmp_path: Path) -> None:
    completed, payload = _run_cli("static_export_valid_approved.json", tmp_path / "approved.json")

    _assert_success(completed)
    assert payload["output_status"] == "approved"
    assert payload["review_status"] == "Approved by backend review"
    assert payload["evidence_refs"] == ["evidence:prototype.source.offline.001"]
    assert payload["unresolved_tensions"][0]["tension_id"] == "prototype.tension.offline.nonblocking"
    assert payload["unresolved_tensions"][0]["blocking"] is False


def test_cli_preserves_blocking_unresolved_tension_and_deferred_status(tmp_path: Path) -> None:
    completed, payload = _run_cli("static_export_blocking_tension.json", tmp_path / "deferred.json")

    _assert_success(completed)
    assert payload["output_status"] == "deferred"
    assert payload["review_status"] == "Deferred by backend review"
    assert payload["evidence_refs"] == ["evidence:prototype.source.offline.002"]
    assert payload["unresolved_tensions"][0]["tension_id"] == "prototype.tension.offline.lineage"
    assert payload["unresolved_tensions"][0]["blocking"] is True


def test_cli_rejects_generator_self_approval_without_losing_evidence_refs(tmp_path: Path) -> None:
    completed, payload = _run_cli("static_export_generator_self_approval.json", tmp_path / "rejected.json")

    _assert_success(completed)
    assert payload["output_status"] == "rejected"
    assert payload["review_status"] == "Rejected by backend review"
    assert payload["evidence_refs"] == ["evidence:prototype.source.offline.003"]


def test_cli_optional_canonical_ledger_writes_only_to_temp_path(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    output_path = tmp_path / "result.json"
    canonical_ledger_path = tmp_path / "canonical" / "governed_authoring.jsonl"

    completed, payload = _run_cli(
        "static_export_valid_approved.json",
        output_path,
        canonical_ledger_path=canonical_ledger_path,
    )

    _assert_success(completed)
    entries = read_ledger_entries(canonical_ledger_path)
    assert len(entries) == 1
    assert entries[0]["decision"] == "APPROVE_OUTPUT"
    assert payload["canonical_ledger_entry_id"] == entries[0]["ledger_entry_id"]
    assert _production_jsonl_snapshot() == before


def test_cli_missing_input_returns_nonzero_and_writes_no_result(tmp_path: Path) -> None:
    missing_input = tmp_path / "missing.json"
    output_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "signal_agent.governed_authoring.cli",
            "verify-static-export",
            "--input",
            str(missing_input),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "static export input does not exist" in completed.stderr
    assert not output_path.exists()


def test_cli_does_not_modify_production_jsonl_ledgers(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()

    for fixture_name in [
        "static_export_valid_provisional.json",
        "static_export_valid_approved.json",
        "static_export_missing_evidence.json",
        "static_export_blocking_tension.json",
        "static_export_generator_self_approval.json",
    ]:
        completed, payload = _run_cli(fixture_name, tmp_path / f"{fixture_name}.json")
        _assert_success(completed)
        assert payload["schema_version"] == "governed_authoring.prototype_result.v1"

    assert _production_jsonl_snapshot() == before


def test_cli_introduces_no_network_or_server_surface() -> None:
    cli_text = CLI.read_text(encoding="utf-8")
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
        assert token not in cli_text
