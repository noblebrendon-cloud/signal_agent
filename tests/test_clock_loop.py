from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.daemon.clock import SystemHalt, tick_once


class DummySnap:
    def __init__(self, regime: str):
        self.regime = regime


class DummyKernel:
    def __init__(self, regime: str):
        self._regime = regime

    def snapshot(self):
        return DummySnap(self._regime)


class DummyGovernor:
    def __init__(self, allow: bool):
        self.allow = allow

    def enforce(self, scope: str):
        return {"decision": "ALLOW" if self.allow else "BLOCK"}


class DummyBreakerStore:
    def __init__(self, state: str):
        self._state = state

    def required_breakers(self):
        return ["default"]

    def get_state(self, name: str):
        return {"state": self._state}


def test_tick_once_breaker_open_noop(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    kernel = DummyKernel(regime="STABLE")
    gov = DummyGovernor(allow=True)
    breakers = DummyBreakerStore(state="OPEN")

    status = tick_once(kernel=kernel, governor=gov, breaker_store=breakers, contract_path=tmp_path / "task_contract.yaml")
    assert status == "NO_OP_BREAKER_OPEN"


def test_tick_once_kernel_failure_halts(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    kernel = DummyKernel(regime="FAILURE")
    gov = DummyGovernor(allow=True)
    breakers = DummyBreakerStore(state="CLOSED")

    with pytest.raises(SystemHalt):
        tick_once(kernel=kernel, governor=gov, breaker_store=breakers, contract_path=tmp_path / "task_contract.yaml")


def test_tick_once_governor_blocks_noop(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    kernel = DummyKernel(regime="STABLE")
    gov = DummyGovernor(allow=False)
    breakers = DummyBreakerStore(state="CLOSED")

    status = tick_once(kernel=kernel, governor=gov, breaker_store=breakers, contract_path=tmp_path / "task_contract.yaml")
    assert status == "NO_OP_GOVERNOR_LOCKED"


def test_tick_once_success_appends_eval(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    contract_path = tmp_path / "task_contract.yaml"
    contract_path.write_text("{}", encoding="utf-8")

    kernel = DummyKernel(regime="STABLE")
    gov = DummyGovernor(allow=True)
    breakers = DummyBreakerStore(state="CLOSED")

    import app.pipeline.contract_evaluator as ce
    monkeypatch.setattr(ce, "run_pipeline_cycle", lambda **kw: {"ok": True})
    
    import app.audit.runtime_audit as ra
    monkeypatch.setattr(ra, "verify_contract", lambda contract, preflight, postflight: (True, {"cycle_ok": True}))

    status = tick_once(kernel=kernel, governor=gov, breaker_store=breakers, contract_path=contract_path)
    assert status == "SUCCESS"

    jsonl_path = tmp_path / "data" / "state" / "contract_eval.jsonl"
    assert jsonl_path.exists()
    
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    eval_obj = json.loads(lines[-1])
    assert eval_obj.get("ok") is True
