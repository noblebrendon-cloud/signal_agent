from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from signal_agent.formal_governance.ledger import read_ledger_entries
from signal_agent.governed_authoring.command_router import LocalAuthoringCommandRouter, RouterErrorRaised
from signal_agent.governed_authoring.demo_bundle import DEMO_FIXTURES
from signal_agent.governed_authoring.path_policy import PathPolicyError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governed_authoring"
PROTOTYPE = ROOT / "products" / "governed_authoring_studio" / "prototype_v1a"
ROUTER_FILES = [
    ROOT / "signal_agent" / "governed_authoring" / "path_policy.py",
    ROOT / "signal_agent" / "governed_authoring" / "workspace.py",
    ROOT / "signal_agent" / "governed_authoring" / "command_router.py",
]


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


def _router(tmp_path: Path) -> LocalAuthoringCommandRouter:
    return LocalAuthoringCommandRouter(repo_root=ROOT, temp_root=tmp_path)


def test_validate_output_directory_accepts_temp_workspace(tmp_path: Path) -> None:
    router = _router(tmp_path)

    result = router.validate_output_directory(workspace_path=tmp_path / "workspace")

    assert result.result_code == 0
    assert result.payload["classification"]["classification"] in {
        "allowed_workspace_path",
        "allowed_temp_path",
    }


def test_validate_output_directory_rejects_repo_data_workspace(tmp_path: Path) -> None:
    router = _router(tmp_path)

    with pytest.raises(PathPolicyError):
        router.validate_output_directory(workspace_path=ROOT / "data")


def test_verify_static_export_routes_fixture_to_result_inside_temp_workspace(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"
    output_path = workspace / "results" / "approved.result.json"

    result = router.verify_static_export(
        input_path=FIXTURES / "static_export_valid_approved.json",
        workspace_path=workspace,
        result_path=output_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert result.result_code == 0
    assert payload["schema_version"] == "governed_authoring.prototype_result.v1"
    assert payload["output_status"] == "approved"
    assert payload["review_status"] == "Approved by backend review"
    assert not list((workspace / "ledgers").glob("*.jsonl"))


def test_verify_static_export_requires_explicit_ledger_path_when_requested(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"

    with pytest.raises(PathPolicyError) as exc:
        router.verify_static_export(
            input_path=FIXTURES / "static_export_valid_approved.json",
            workspace_path=workspace,
            result_path=workspace / "results" / "approved.result.json",
            canonical_ledger_requested=True,
        )

    assert exc.value.code == "LEDGER_PATH_REQUIRED"
    assert not workspace.exists()


def test_verify_static_export_optional_ledger_writes_only_to_explicit_workspace_ledgers_path(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"
    ledger_path = workspace / "ledgers" / "canonical.jsonl"

    result = router.verify_static_export(
        input_path=FIXTURES / "static_export_valid_approved.json",
        workspace_path=workspace,
        result_path=workspace / "results" / "approved.result.json",
        canonical_ledger_path=ledger_path,
    )

    assert result.result_code == 0
    assert ledger_path.exists()
    entries = read_ledger_entries(ledger_path)
    assert len(entries) == 1
    assert entries[0]["decision"] == "APPROVE_OUTPUT"
    assert _production_jsonl_snapshot() == before


def test_verify_static_export_rejects_repo_data_result_path(tmp_path: Path) -> None:
    router = _router(tmp_path)

    with pytest.raises(PathPolicyError):
        router.verify_static_export(
            input_path=FIXTURES / "static_export_valid_approved.json",
            workspace_path=tmp_path / "workspace",
            result_path=ROOT / "data" / "outputs" / "phase26.result.json",
        )


def test_verify_static_export_rejects_overwrite_by_default(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"
    output_path = workspace / "results" / "approved.result.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(PathPolicyError) as exc:
        router.verify_static_export(
            input_path=FIXTURES / "static_export_valid_approved.json",
            workspace_path=workspace,
            result_path=output_path,
        )

    assert exc.value.code == "OVERWRITE_DENIED"
    assert output_path.read_text(encoding="utf-8") == "existing\n"


def test_verify_static_export_can_raise_structured_governance_errors(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"

    with pytest.raises(RouterErrorRaised) as exc:
        router.verify_static_export(
            input_path=FIXTURES / "static_export_missing_evidence.json",
            workspace_path=workspace,
            result_path=workspace / "results" / "missing_evidence.result.json",
            raise_on_governance_error=True,
        )

    assert exc.value.error.code == "MISSING_EVIDENCE"
    assert not (workspace / "results" / "missing_evidence.result.json").exists()


@pytest.mark.parametrize(
    ("fixture_name", "expected_code"),
    [
        ("static_export_generator_self_approval.json", "SELF_CERTIFICATION_ATTEMPT"),
        ("static_export_blocking_tension.json", "BLOCKING_UNRESOLVED_TENSION"),
    ],
)
def test_verify_static_export_can_raise_other_structured_governance_errors(
    tmp_path: Path,
    fixture_name: str,
    expected_code: str,
) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / fixture_name

    with pytest.raises(RouterErrorRaised) as exc:
        router.verify_static_export(
            input_path=FIXTURES / fixture_name,
            workspace_path=workspace,
            result_path=workspace / "results" / "result.json",
            raise_on_governance_error=True,
        )

    assert exc.value.error.code == expected_code
    assert not (workspace / "results" / "result.json").exists()


def test_command_router_raises_structured_input_errors(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(RouterErrorRaised) as missing:
        router.verify_static_export(
            input_path=tmp_path / "missing.json",
            workspace_path=workspace,
            result_path=workspace / "results" / "result.json",
        )
    with pytest.raises(RouterErrorRaised) as invalid_json:
        router.verify_static_export(
            input_path=invalid,
            workspace_path=workspace,
            result_path=workspace / "results" / "invalid.result.json",
        )

    assert missing.value.error.code == "MISSING_INPUT"
    assert invalid_json.value.error.code == "INVALID_JSON"


def test_run_demo_bundle_routes_outputs_into_temp_workspace_only(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"

    result = router.run_demo_bundle(workspace_path=workspace)

    assert result.result_code == 0
    assert (workspace / "summaries" / "proof_summary.md").exists()
    for fixture in DEMO_FIXTURES:
        assert (workspace / "results" / f"{Path(fixture.filename).stem}.result.json").exists()
    assert not list((workspace / "ledgers").glob("*.jsonl"))


def test_run_demo_bundle_optional_ledger_requires_explicit_workspace_ledgers_path(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"

    with pytest.raises(PathPolicyError) as exc:
        router.run_demo_bundle(workspace_path=workspace, canonical_ledger_requested=True)
    assert exc.value.code == "LEDGER_PATH_REQUIRED"

    ledger_path = workspace / "ledgers" / "canonical_governed_authoring.jsonl"
    result = router.run_demo_bundle(workspace_path=workspace, canonical_ledger_path=ledger_path)
    entries = read_ledger_entries(ledger_path)

    assert result.result_code == 0
    assert len(entries) == len(DEMO_FIXTURES)


def test_inspect_and_summarize_result_packets_use_explicit_workspace_paths(tmp_path: Path) -> None:
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"
    result_path = workspace / "results" / "approved.result.json"
    report_path = workspace / "summaries" / "inspection.md"
    summary_path = workspace / "summaries" / "proof_output_summary.md"

    router.verify_static_export(
        input_path=FIXTURES / "static_export_valid_approved.json",
        workspace_path=workspace,
        result_path=result_path,
    )
    inspection = router.inspect_result_packet(
        input_path=result_path,
        workspace_path=workspace,
        report_path=report_path,
    )
    summary = router.summarize_proof_output(workspace_path=workspace, summary_path=summary_path)

    assert inspection.result_code == 0
    assert inspection.payload["output_status"] == "approved"
    assert report_path.exists()
    assert summary.result_code == 0
    assert summary.payload["result_count"] == 1
    assert summary_path.exists()


def test_command_router_preserves_production_jsonl_and_static_prototype_files(tmp_path: Path) -> None:
    before_jsonl = _production_jsonl_snapshot()
    before_prototype = _prototype_snapshot()
    router = _router(tmp_path)
    workspace = tmp_path / "workspace"

    router.verify_static_export(
        input_path=FIXTURES / "static_export_valid_provisional.json",
        workspace_path=workspace,
        result_path=workspace / "results" / "provisional.result.json",
    )
    router.run_demo_bundle(workspace_path=tmp_path / "demo_workspace")

    assert _production_jsonl_snapshot() == before_jsonl
    assert _prototype_snapshot() == before_prototype


def test_command_router_introduces_no_server_or_network_surface() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ROUTER_FILES)
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
        assert token not in combined


def test_command_router_introduces_no_production_authoring_artifact_write_path() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8").replace("\\", "/") for path in ROUTER_FILES)
    forbidden_fragments = [
        "data/governed_authoring",
        "data/authoring",
        "data/outputs/governed_authoring",
        "data/outputs/authoring",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in combined
