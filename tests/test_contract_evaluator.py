from __future__ import annotations

import json
from pathlib import Path

import pytest


class DummySnap:
    def __init__(self, regime: str):
        self.regime = regime


def test_evaluate_cycle_writes_artifacts_and_appends_jsonl_with_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    # Minimal contract file
    contract_path = tmp_path / "task_contract.yaml"
    contract_path.write_text("request_id: test_req\npipeline: {}\n", encoding="utf-8")
    
    # Mocking pipeline cycle and runtime audit to run cleanly inside isolated tests without real logic bindings
    import app.pipeline.contract_evaluator as ce
    monkeypatch.setattr(ce, "run_pipeline_cycle", lambda **kw: {"ok": True})
    
    import app.audit.runtime_audit as ra
    monkeypatch.setattr(ra, "verify_contract", lambda contract, preflight, postflight: (True, {"cycle_ok": True}), raising=False)

    # Let's write a mock config so the registry loads correctly from current 'chdir' tmp directory
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "model_pool.yaml"
    config_path.write_text("default_provider: stub\nproviders:\n  stub:\n    deterministic_stub: true\n", encoding="utf-8")

    snap = DummySnap(regime="STABLE")

    from app.pipeline.contract_evaluator import evaluate_cycle
    out = evaluate_cycle(contract_path=contract_path, kernel_snap=snap)
    assert out["request_id"] == "test_req"

    preflight_file = tmp_path / "data/state/preflight.json"
    postflight_file = tmp_path / "data/state/postflight.json"
    contract_eval_file = tmp_path / "data/state/contract_eval.json"
    contract_eval_jsonl = tmp_path / "data/state/contract_eval.jsonl"

    assert preflight_file.exists()
    assert postflight_file.exists()
    assert contract_eval_file.exists()
    assert contract_eval_jsonl.exists()
    
    kernel_history_file = tmp_path / "data/state/kernel_history.jsonl"
    assert kernel_history_file.exists()
    kh_lines = kernel_history_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(kh_lines) >= 1
    kh_obj = json.loads(kh_lines[-1])
    assert kh_obj["request_id"] == "test_req"
    assert kh_obj["provider"]["name"] == "stub"
    assert "regime" in kh_obj["kernel"]
    assert "phi1" in kh_obj["kernel"]
    assert "engine_version" in kh_obj
    
    preflight_data = json.loads(preflight_file.read_text(encoding="utf-8"))
    assert "provider" in preflight_data
    assert preflight_data["provider"]["name"] == "stub"
    assert "profile_hash" in preflight_data["provider"]

    eval_data = json.loads(contract_eval_file.read_text(encoding="utf-8"))
    assert "provider" in eval_data
    assert eval_data["provider"]["name"] == "stub"
    assert "profile_hash" in eval_data["provider"]
