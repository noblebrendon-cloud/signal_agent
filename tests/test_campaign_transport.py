"""Real HTTP and CLI contracts for local campaign proposals and handoffs."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from signal_agent.campaigns import server as campaign_server
from signal_agent.campaigns.server import MAX_BODY_BYTES, create_server


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "campaigns" / "exploratory_campaign.json"
EVALUATED_AT = "2026-11-10T00:00:00Z"


@pytest.fixture
def campaign() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def api():
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def request(api, method: str, path: str, *, body: bytes | None = None, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", api.server_address[1], timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"
        assert response.getheader("Access-Control-Allow-Origin") is None
        assert b"Traceback" not in raw
        return response.status, json.loads(raw), dict(response.getheaders())
    finally:
        connection.close()


def post(api, path: str, payload: object):
    return request(api, "POST", path, body=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})


def run_cli(*args: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "signal_agent.campaigns", *args],
        cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=15, check=False,
    )


def test_http_health_and_catalog_are_json_without_cors(api) -> None:
    status, health, headers = request(api, "GET", "/health")
    assert status == 200
    assert health == {"status": "ok", "service": "signal-agent-campaigns", "mode": "local_provisional"}
    assert headers["Cache-Control"] == "no-store"

    status, catalog, _ = request(api, "GET", "/api/campaigns/principles")
    assert status == 200
    assert catalog["schema_version"]
    assert catalog["principles"]


def test_http_evaluation_preserves_explicit_time_and_proposal_limits(api, campaign) -> None:
    envelope = {"campaign": campaign, "evaluated_at": EVALUATED_AT}
    status, decision, _ = post(api, "/api/campaigns/evaluate", envelope)
    assert status == 200
    assert decision["schema_version"] == "campaign_decision.v1"
    assert decision["campaign_id"] == campaign["campaign_id"]
    assert decision["evaluated_at"] == EVALUATED_AT
    assert decision["proposed_action"] == "run_small_test"
    assert decision["production_eligible"] is True
    assert decision["authority_status"] == "not_granted_by_evaluation"
    assert decision["execution_status"] == "not_executed"
    assert decision["evidence_quality"]["criteria_met"] is False
    assert post(api, "/api/campaigns/evaluate", envelope)[1] == decision


def test_http_handoff_keeps_sources_and_tasks_in_memory(api, campaign, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    status, packet, _ = post(api, "/api/campaigns/handoff", {"campaign": campaign, "evaluated_at": EVALUATED_AT})
    assert status == 200
    assert packet["schema_version"] == "campaign_handoff.v1"
    assert packet["execution_status"] == "prepared_not_executed"
    assert packet["publication_authorized"] is False
    assert packet["authoring_result"]["output_manifest"]["output_status"] == "provisional"
    assert packet["authoring_result"]["canonical_ledger_entry"] is None
    assert packet["production_packet"]["execution_status"] == "pending_external_executor"
    assert packet["production_packet"]["tasks"]
    assert all(task["status"] == "pending" for task in packet["production_packet"]["tasks"])
    source = packet["source_packet"]["source_material"][0]
    assert source["text"] == campaign["sources"][0]["text"]
    assert source["content_hash"] == hashlib.sha256(source["text"].encode("utf-8")).hexdigest()
    assert "workspace" not in packet
    assert list(tmp_path.iterdir()) == []


def test_http_not_ready_is_a_conflict_with_the_actual_decision(api, campaign) -> None:
    campaign["phase"] = "paused"
    status, payload, _ = post(api, "/api/campaigns/handoff", {"campaign": campaign, "evaluated_at": EVALUATED_AT})
    assert status == 409
    assert payload["error"]["code"] == "campaign_not_ready"
    assert payload["error"]["decision"]["proposed_action"] == "pause"
    assert payload["error"]["decision"]["production_eligible"] is False


@pytest.mark.parametrize("evaluated_at", [None, "now", "2026-11-10", "2026-11-10T00:00:00"])
def test_http_invalid_timestamps_reach_core_validation(api, campaign, evaluated_at) -> None:
    status, payload, _ = post(api, "/api/campaigns/evaluate", {"campaign": campaign, "evaluated_at": evaluated_at})
    assert status == 400
    assert payload["error"]["code"] == "invalid_campaign"


@pytest.mark.parametrize("payload", [
    [], {}, {"campaign": {}}, {"campaign": {}, "evaluated_at": EVALUATED_AT, "workspace": "/tmp/forbidden"},
    {"campaign": {}, "evaluated_at": EVALUATED_AT, "output_dir": "/tmp/forbidden"},
])
def test_http_requires_an_exact_envelope_with_no_filesystem_destination(api, payload) -> None:
    status, response, _ = post(api, "/api/campaigns/handoff", payload)
    assert status == 400
    assert response["error"]["code"] == "invalid_envelope"


@pytest.mark.parametrize(("raw", "error_code"), [
    (b"not json", "invalid_json"),
    (b"\xff", "invalid_json"),
    (b'{"campaign":{},"campaign":{},"evaluated_at":"2026-11-10T00:00:00Z"}', "duplicate_json_key"),
    (b'{"campaign":{"title":"first","title":"second"},"evaluated_at":"2026-11-10T00:00:00Z"}', "duplicate_json_key"),
    (b'{"campaign":NaN,"evaluated_at":"2026-11-10T00:00:00Z"}', "invalid_json_number"),
    (b'{"campaign":Infinity,"evaluated_at":"2026-11-10T00:00:00Z"}', "invalid_json_number"),
    (b'{"campaign":-Infinity,"evaluated_at":"2026-11-10T00:00:00Z"}', "invalid_json_number"),
    (b'{"campaign":1e9999,"evaluated_at":"2026-11-10T00:00:00Z"}', "invalid_json_number"),
])
def test_http_rejects_ambiguous_or_nonfinite_json(api, raw, error_code) -> None:
    status, payload, _ = request(api, "POST", "/api/campaigns/evaluate", body=raw, headers={"Content-Type": "application/json"})
    assert status == 400
    assert payload["error"]["code"] == error_code


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "application/json; charset=utf-16"])
def test_http_requires_json_content_type(api, content_type) -> None:
    status, payload, _ = request(api, "POST", "/api/campaigns/evaluate", body=b"{}", headers={"Content-Type": content_type})
    assert status == 415
    assert payload["error"]["code"] == "unsupported_media_type"


def test_http_rejects_oversized_body_before_reading_it(api) -> None:
    status, payload, _ = request(
        api, "POST", "/api/campaigns/evaluate", body=b"",
        headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)},
    )
    assert status == 413
    assert payload["error"]["code"] == "body_too_large"


@pytest.mark.parametrize(("headers", "error_code"), [
    ({"Content-Length": "-1"}, "invalid_length"),
    ({"Content-Length": "1,1"}, "invalid_length"),
    ({"Transfer-Encoding": "chunked"}, "invalid_framing"),
])
def test_http_rejects_ambiguous_body_framing(api, headers, error_code) -> None:
    status, payload, _ = request(
        api, "POST", "/api/campaigns/evaluate", body=b"",
        headers={"Content-Type": "application/json", **headers},
    )
    assert status == 400
    assert payload["error"]["code"] == error_code


def test_http_rejects_duplicate_length_and_host_headers(api) -> None:
    port = api.server_address[1]
    for duplicate in ("Content-Length", "Host"):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.putrequest("POST", "/api/campaigns/evaluate", skip_host=True)
            connection.putheader("Host", f"127.0.0.1:{port}")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", "0")
            connection.putheader(duplicate, "0" if duplicate == "Content-Length" else f"127.0.0.1:{port}")
            connection.endheaders()
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == (400 if duplicate == "Content-Length" else 403)
            assert payload["error"]["code"] == ("invalid_length" if duplicate == "Content-Length" else "invalid_host")
        finally:
            connection.close()


@pytest.mark.parametrize("header_kind", ["foreign_host", "wrong_port", "foreign_origin", "null_origin", "different_local_origin", "cross_site"])
def test_http_denies_host_rebinding_and_cross_origin_requests(api, header_kind) -> None:
    port = api.server_address[1]
    headers = {
        "foreign_host": {"Host": f"attacker.invalid:{port}"},
        "wrong_port": {"Host": "127.0.0.1:1"},
        "foreign_origin": {"Origin": "https://attacker.invalid"},
        "null_origin": {"Origin": "null"},
        "different_local_origin": {"Origin": f"http://localhost:{port}"},
        "cross_site": {"Sec-Fetch-Site": "cross-site"},
    }[header_kind]
    status, payload, _ = request(api, "GET", "/health", headers=headers)
    assert status == 403
    assert payload["error"]["code"] in {"invalid_host", "invalid_origin"}


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_http_accepts_only_matching_local_origin_and_host(api, host) -> None:
    authority = f"{host}:{api.server_address[1]}"
    status, payload, _ = request(api, "GET", "/health", headers={
        "Host": authority, "Origin": f"http://{authority}", "Sec-Fetch-Site": "same-origin",
    })
    assert status == 200
    assert payload["status"] == "ok"


@pytest.mark.parametrize("host", ["", "0.0.0.0", "::", "::1", "127.0.0.2", "localhost.attacker.invalid"])
def test_server_cannot_bind_to_nonpermitted_addresses(host) -> None:
    with pytest.raises(ValueError, match="127.0.0.1 or localhost"):
        create_server(host, 0)


@pytest.mark.parametrize(("method", "path", "expected"), [
    ("GET", "/unknown", 404),
    ("POST", "/api/campaigns/publish", 404),
    ("POST", "/api/campaigns/approve", 404),
    ("GET", "/api/campaigns/evaluate", 405),
    ("OPTIONS", "/api/campaigns/evaluate", 405),
])
def test_http_route_and_method_errors_are_json(api, method, path, expected) -> None:
    status, payload, _ = request(api, method, path)
    assert status == expected
    assert payload["error"]["code"] in {"not_found", "method_not_allowed"}


def test_unexpected_server_errors_do_not_expose_internal_exception_text(api, campaign, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("private exception detail that must not be returned")

    monkeypatch.setattr(campaign_server, "evaluate_campaign", fail)
    status, payload, _ = post(api, "/api/campaigns/evaluate", {"campaign": campaign, "evaluated_at": EVALUATED_AT})
    assert status == 500
    assert payload == {"error": {"code": "internal_error", "message": "The campaign request could not be completed."}}


def test_cli_evaluates_the_example_as_json_in_a_real_subprocess(campaign) -> None:
    completed = run_cli("evaluate", "--campaign", str(EXAMPLE), "--at", EVALUATED_AT)
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    decision = json.loads(completed.stdout)
    assert decision["campaign_id"] == campaign["campaign_id"]
    assert decision["proposed_action"] == "run_small_test"
    assert decision["evaluated_at"] == EVALUATED_AT
    assert decision["authority_status"] == "not_granted_by_evaluation"


def test_cli_catalog_and_help_are_machine_readable() -> None:
    completed = run_cli("catalog")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["principles"]
    help_result = run_cli("--help")
    assert help_result.returncode == 0
    assert "catalog" in json.loads(help_result.stdout)["help"]


def test_cli_serve_reports_its_actual_loopback_listener() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "signal_agent.campaigns", "serve", "--host", "localhost", "--port", "0"],
        cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        ready = json.loads(lines.get(timeout=10))
        assert ready["status"] == "listening"
        assert ready["url"].startswith("http://127.0.0.1:")
        port = int(ready["url"].rsplit(":", 1)[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            assert response.status == 200
            assert json.loads(response.read())["mode"] == "local_provisional"
        finally:
            connection.close()
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
        reader.join(timeout=1)


def test_cli_handoff_writes_a_guarded_traceable_workspace_and_refuses_retry(tmp_path, campaign) -> None:
    workspace = tmp_path / "campaign-handoff"
    arguments = ("handoff", "--campaign", str(EXAMPLE), "--at", EVALUATED_AT, "--workspace", str(workspace))
    completed = run_cli(*arguments)
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    receipt = json.loads(completed.stdout)
    assert receipt["schema_version"] == "campaign_export_receipt.v1"
    assert receipt["status"] == "prepared_not_executed"
    assert receipt["publication_authorized"] is False
    for name, path in receipt["files"].items():
        artifact = Path(path)
        assert artifact.is_relative_to(workspace)
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == receipt["sha256"][name]
    source_packet = json.loads((workspace / "inputs" / "source_packet.json").read_text(encoding="utf-8"))
    assert source_packet["source_material"][0]["text"] == campaign["sources"][0]["text"]
    production = json.loads((workspace / "metadata" / "source_to_series_task_packet.json").read_text(encoding="utf-8"))
    assert all(task["status"] == "pending" for task in production["tasks"])
    before = {name: Path(path).read_bytes() for name, path in receipt["files"].items()}
    retry = run_cli(*arguments)
    assert retry.returncode != 0
    assert retry.stdout == ""
    assert json.loads(retry.stderr)["error"]
    assert {name: Path(path).read_bytes() for name, path in receipt["files"].items()} == before


@pytest.mark.parametrize("arguments", [
    (), ("publish",), ("approve",),
    ("evaluate", "--campaign", str(EXAMPLE)),
    ("evaluate", "--campaign", str(EXAMPLE), "--at", "now"),
    ("serve", "--host", "0.0.0.0"),
    ("serve", "--port", "-1"),
])
def test_cli_errors_are_json_on_stderr_with_nonzero_exit(arguments) -> None:
    completed = run_cli(*arguments)
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    assert json.loads(completed.stderr)["error"]["code"]


def test_cli_rejects_duplicate_json_keys_before_evaluation(tmp_path) -> None:
    source = tmp_path / "ambiguous.json"
    source.write_text('{"campaign_id":"first","campaign_id":"second"}', encoding="utf-8")
    completed = run_cli("evaluate", "--campaign", str(source), "--at", EVALUATED_AT)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr)["error"]["code"] == "duplicate_json_key"
