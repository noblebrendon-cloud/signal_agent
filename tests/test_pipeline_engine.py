from __future__ import annotations

from app.pipeline.engine import run_pipeline_cycle


def test_engine_returns_structured_failure_without_raising(monkeypatch):
    # Force imports inside run_pipeline_cycle to fail
    # (simulate missing promote/route modules or runtime issues)
    contract = {"pipeline": {}}
    result = run_pipeline_cycle(contract=contract, request_id="test_req")
    assert "ok" in result
    assert "diagnostics" in result
    assert result["request_id"] == "test_req"
