from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from signal_agent.formal_governance.ledger import read_ledger_entries
from signal_agent.governed_authoring.demo_bundle import DEMO_FIXTURES


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governed_authoring"
PROTOTYPE = ROOT / "products" / "governed_authoring_studio" / "prototype_v1a"
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


def _prototype_snapshot() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PROTOTYPE.glob("*"))
        if path.is_file()
    }


def _run_router(args: list[str]) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, "-m", "signal_agent.governed_authoring.cli", "router", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_payload = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    stderr_payload = json.loads(completed.stderr) if completed.stderr.strip().startswith("{") else {}
    return completed, stdout_payload, stderr_payload


def _assert_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().startswith("{")


def test_cli_router_verify_static_export_writes_result_inside_temp_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    completed, payload, _error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
        ]
    )
    result_path = workspace / "results" / "static_export_valid_approved.result.json"
    result_packet = json.loads(result_path.read_text(encoding="utf-8"))

    _assert_success(completed)
    assert payload["command"] == "verify-static-export"
    assert result_packet["schema_version"] == "governed_authoring.prototype_result.v1"
    assert result_packet["output_status"] == "approved"
    assert result_packet["review_status"] == "Approved by backend review"
    assert not list((workspace / "ledgers").glob("*.jsonl"))


def test_cli_router_run_demo_bundle_writes_outputs_into_temp_workspace_only(tmp_path: Path) -> None:
    workspace = tmp_path / "demo_workspace"

    completed, payload, _error = _run_router(["run-demo-bundle", "--workspace", str(workspace)])

    _assert_success(completed)
    assert payload["command"] == "run-demo-bundle"
    assert (workspace / "summaries" / "proof_summary.md").exists()
    for fixture in DEMO_FIXTURES:
        assert (workspace / "results" / f"{Path(fixture.filename).stem}.result.json").exists()
    assert not list((workspace / "ledgers").glob("*.jsonl"))


def test_cli_router_inspect_result_packet_reads_without_production_write(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    workspace = tmp_path / "workspace"
    result_path = workspace / "results" / "approved.result.json"
    verify_completed, _payload, _error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--output",
            str(result_path),
        ]
    )

    _assert_success(verify_completed)
    completed, payload, _error = _run_router(["inspect-result-packet", "--input", str(result_path)])

    _assert_success(completed)
    assert payload["command"] == "inspect-result-packet"
    assert payload["payload"]["output_status"] == "approved"
    assert payload["output_paths"] == []
    assert _production_jsonl_snapshot() == before


def test_cli_router_validate_output_directory_accepts_temp_workspace(tmp_path: Path) -> None:
    completed, payload, _error = _run_router(["validate-output-directory", "--workspace", str(tmp_path / "workspace")])

    _assert_success(completed)
    assert payload["command"] == "validate-output-directory"
    assert payload["payload"]["classification"]["classification"] in {
        "allowed_workspace_path",
        "allowed_temp_path",
    }


def test_cli_router_validate_output_directory_rejects_repo_data() -> None:
    completed, _payload, error = _run_router(["validate-output-directory", "--workspace", str(ROOT / "data")])

    assert completed.returncode != 0
    assert error["code"] == "FORBIDDEN_OUTPUT_PATH"
    assert error["category"] == "path"


def test_cli_router_summarize_proof_output_reads_temp_workspace_results(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    verify_completed, _payload, _error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_provisional.json"),
            "--workspace",
            str(workspace),
        ]
    )

    _assert_success(verify_completed)
    completed, payload, _error = _run_router(["summarize-proof-output", "--workspace", str(workspace)])

    _assert_success(completed)
    assert payload["command"] == "summarize-proof-output"
    assert payload["payload"]["result_count"] == 1
    assert (workspace / "summaries" / "proof_output_summary.md").exists()


def test_cli_router_rejects_forbidden_repo_data_output_path(tmp_path: Path) -> None:
    forbidden = ROOT / "data" / f"phase29_router_cli_{tmp_path.name}.result.json"
    assert not forbidden.exists()

    completed, _payload, error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(forbidden),
        ]
    )

    assert completed.returncode != 0
    assert error["code"] == "FORBIDDEN_OUTPUT_PATH"
    assert not forbidden.exists()


def test_cli_router_rejects_parent_traversal_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.result.json"

    completed, _payload, error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--output",
            str(workspace / "results" / ".." / ".." / "outside.result.json"),
        ]
    )

    assert completed.returncode != 0
    assert error["code"] == "FORBIDDEN_OUTPUT_PATH"
    assert not outside.exists()


def test_cli_router_rejects_overwrite_by_default(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result_path = workspace / "results" / "approved.result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text("existing\n", encoding="utf-8")

    completed, _payload, error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--output",
            str(result_path),
        ]
    )

    assert completed.returncode != 0
    assert error["code"] == "OVERWRITE_DENIED"
    assert result_path.read_text(encoding="utf-8") == "existing\n"


def test_cli_router_rejects_implicit_ledger_request_without_explicit_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    completed, _payload, error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--with-canonical-ledger",
        ]
    )

    assert completed.returncode != 0
    assert error["code"] == "LEDGER_PATH_REQUIRED"
    assert not workspace.exists()


def test_cli_router_rejects_forbidden_ledger_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    completed, _payload, error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--canonical-ledger",
            str(ROOT / "data" / "artifact_registry.jsonl"),
        ]
    )

    assert completed.returncode != 0
    assert error["code"] == "LEDGER_PATH_FORBIDDEN"


def test_cli_router_optional_explicit_ledger_writes_only_under_workspace_ledgers(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    workspace = tmp_path / "workspace"
    ledger = workspace / "ledgers" / "canonical.jsonl"

    completed, payload, _error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
            "--workspace",
            str(workspace),
            "--canonical-ledger",
            str(ledger),
        ]
    )

    _assert_success(completed)
    assert str(ledger) in payload["output_paths"]
    entries = read_ledger_entries(ledger)
    assert len(entries) == 1
    assert entries[0]["decision"] == "APPROVE_OUTPUT"
    assert _production_jsonl_snapshot() == before


def test_cli_router_reports_missing_invalid_and_unsupported_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json\n", encoding="utf-8")

    missing_completed, _payload, missing = _run_router(
        [
            "verify-static-export",
            "--input",
            str(tmp_path / "missing.json"),
            "--workspace",
            str(workspace),
        ]
    )
    invalid_completed, _payload, invalid_error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(invalid),
            "--workspace",
            str(workspace),
        ]
    )
    unsupported_completed, _payload, unsupported = _run_router(
        [
            "inspect-result-packet",
            "--input",
            str(FIXTURES / "static_export_valid_approved.json"),
        ]
    )

    assert missing_completed.returncode != 0
    assert invalid_completed.returncode != 0
    assert unsupported_completed.returncode != 0
    assert missing["code"] == "MISSING_INPUT"
    assert invalid_error["code"] == "INVALID_JSON"
    assert unsupported["code"] == "UNSUPPORTED_PACKET_SHAPE"


def test_cli_router_preserves_production_jsonl_and_static_prototype_files(tmp_path: Path) -> None:
    before_jsonl = _production_jsonl_snapshot()
    before_prototype = _prototype_snapshot()
    workspace = tmp_path / "workspace"

    completed, _payload, _error = _run_router(
        [
            "verify-static-export",
            "--input",
            str(FIXTURES / "static_export_valid_provisional.json"),
            "--workspace",
            str(workspace),
        ]
    )

    _assert_success(completed)
    assert _production_jsonl_snapshot() == before_jsonl
    assert _prototype_snapshot() == before_prototype


def test_cli_router_introduces_no_network_or_server_surface() -> None:
    text = CLI.read_text(encoding="utf-8")
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
