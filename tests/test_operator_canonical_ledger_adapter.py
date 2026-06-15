from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from signal_agent.formal_governance.adapters import append_operator_decision_entry
from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger
from signal_agent.operator.intent import IntentParser, ParsedIntent
from signal_agent.operator.planner import OperatorPlan, OperatorPlanner, PlanStep
from signal_agent.operator.registry import (
    OperatorRegistry,
    ToolDefinition,
    WorkflowDefinition,
)
from signal_agent.operator.runtime import OperatorRuntime, OperatorRunResult, ToolExecution


SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "formal_governance"
    / "governed_transition_ledger_entry.v1.schema.json"
)


def _setup_fake_root(tmp_path: Path) -> tuple[Path, OperatorRegistry]:
    repo_root = Path(__file__).resolve().parents[1]
    fake_root = tmp_path / "fake_repo"
    (fake_root / "config").mkdir(parents=True)
    shutil.copytree(repo_root / "config" / "policies", fake_root / "config" / "policies")
    shutil.copy2(repo_root / "config" / "state_machine.yaml", fake_root / "config" / "state_machine.yaml")
    shutil.copy2(repo_root / "config" / "lanes.yaml", fake_root / "config" / "lanes.yaml")
    shutil.copytree(repo_root / "config" / "operator", fake_root / "config" / "operator")
    registry = OperatorRegistry.load(fake_root)
    return fake_root, registry


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _with_signal_agent_root(fake_root: Path):
    class _RootContext:
        def __enter__(self) -> None:
            self.old_root = os.environ.get("SIGNAL_AGENT_ROOT")
            os.environ["SIGNAL_AGENT_ROOT"] = str(fake_root)

        def __exit__(self, exc_type, exc, tb) -> None:
            if self.old_root is None:
                os.environ.pop("SIGNAL_AGENT_ROOT", None)
            else:
                os.environ["SIGNAL_AGENT_ROOT"] = self.old_root

    return _RootContext()


def _assert_schema_valid(entry: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["required"]) <= set(entry)
    assert set(entry) <= set(schema["properties"])
    assert entry["schema_version"] == "governed_transition_ledger_entry.v1"
    assert isinstance(entry["subsystem_refs"], list)
    assert entry["content_hash"].startswith("sha256:")
    assert entry["record_hash"].startswith("sha256:")


def _assert_ref(entry: dict, subsystem: str, ref_type: str) -> None:
    assert any(
        ref.get("subsystem") == subsystem and ref.get("ref_type") == ref_type
        for ref in entry["subsystem_refs"]
    )


def _parse_plan(registry: OperatorRegistry, command: str) -> OperatorPlan:
    parser = IntentParser(registry)
    planner = OperatorPlanner(registry)
    return planner.plan(parser.parse(command))


def _forbidden_record_state_plan(registry: OperatorRegistry) -> OperatorPlan:
    base_wf = registry.workflows["record_state_append"]
    forbidden_wf = WorkflowDefinition(
        workflow_id=base_wf.workflow_id,
        description=base_wf.description,
        intent_ids=base_wf.intent_ids,
        tool_chain=base_wf.tool_chain,
        aliases=base_wf.aliases,
        authority_paths=base_wf.authority_paths,
        writes_paths=base_wf.writes_paths,
        notes=base_wf.notes,
        mode="write",
        resumable=False,
        transition_context={
            "current_state": "captured",
            "next_state": "routed",
            "lane_id": "volatile_capture",
        },
    )
    intent = ParsedIntent(
        command_text="record state routed for canonical_denied",
        intent_id="record_artifact_state",
        confidence=1.0,
        requested_workflow="record_state_append",
        requested_target="canonical_denied",
        requested_target_kind="routed",
    )
    return OperatorPlan(
        intent=intent,
        workflow=forbidden_wf,
        target_workflow=forbidden_wf,
        steps=tuple(PlanStep(tool_id=tid, description=tid) for tid in forbidden_wf.tool_chain),
        status="ready",
        notes=(),
    )


def _contract_violation_registry(base_registry: OperatorRegistry) -> OperatorRegistry:
    tools = dict(base_registry.tools)
    tools["dangerous_mutator"] = ToolDefinition(
        tool_id="dangerous_mutator",
        description="A lifecycle mutator placed in a read-only workflow.",
        kind="mutator",
        reads=("config/lanes.yaml",),
        writes=("data/state/artifact_registry.jsonl",),
    )
    workflows = dict(base_registry.workflows)
    workflows["bad_readonly_write_contract"] = WorkflowDefinition(
        workflow_id="bad_readonly_write_contract",
        description="Read-only workflow containing a mutating tool.",
        intent_ids=("test_contract_violation",),
        tool_chain=("dangerous_mutator",),
        aliases=("bad readonly write contract",),
        authority_paths=("config/operator/tools.yaml", "config/operator/workflows.yaml"),
        writes_paths=(),
        notes=(),
        mode="read_only",
        resumable=False,
    )
    lookup = dict(base_registry._workflow_lookup)
    lookup["bad_readonly_write_contract"] = "bad_readonly_write_contract"
    lookup["bad readonly write contract"] = "bad_readonly_write_contract"
    return OperatorRegistry(
        repo_root=base_registry.repo_root,
        intents=base_registry.intents,
        tools=tools,
        workflows=workflows,
        _workflow_lookup=lookup,
    )


def _contract_violation_plan(registry: OperatorRegistry) -> OperatorPlan:
    workflow = registry.workflows["bad_readonly_write_contract"]
    intent = ParsedIntent(
        command_text="bad readonly write contract",
        intent_id="test_contract_violation",
        confidence=1.0,
        requested_workflow="bad_readonly_write_contract",
    )
    return OperatorPlan(
        intent=intent,
        workflow=workflow,
        target_workflow=workflow,
        steps=(PlanStep(tool_id="dangerous_mutator", description="dangerous_mutator"),),
        status="ready",
        notes=(),
    )


def test_valid_operator_write_decision_appends_canonical_entry(tmp_path: Path) -> None:
    fake_root, registry = _setup_fake_root(tmp_path)
    canonical_ledger = tmp_path / "canonical" / "operator.jsonl"
    plan = _parse_plan(registry, "append intake record canonical_operator_allowed")

    with _with_signal_agent_root(fake_root):
        runtime = OperatorRuntime(
            registry,
            runs_dir=tmp_path / "runs",
            state_dir=tmp_path / "state",
            canonical_ledger_path=canonical_ledger,
        )
        result = runtime.execute(plan)

    entries = read_ledger_entries(canonical_ledger)
    assert result.status == "ok"
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_valid(entry)
    _assert_ref(entry, "operator_runtime", "operator_run")
    _assert_ref(entry, "operator_runtime", "transition_gate")
    _assert_ref(entry, "operator_registry", "workflow_manifest")
    assert entry["decision"] == "PROMOTE_TO_STATE"
    assert entry["subsystem_refs"][0]["run_id"] == result.run_id
    assert entry["subsystem_refs"][0]["workflow_id"] == "intake_log_append"
    assert "observed_as_declared" in entry["subsystem_refs"][0]["consistency_status"]
    assert _read_jsonl(tmp_path / "runs" / "operator_runs.jsonl")
    assert not any("schema_version" in row for row in _read_jsonl(tmp_path / "runs" / "operator_runs.jsonl"))
    assert verify_ledger(canonical_ledger)["clean"] is True


def test_rejected_operator_write_decision_appends_canonical_entry(tmp_path: Path) -> None:
    fake_root, registry = _setup_fake_root(tmp_path)
    canonical_ledger = tmp_path / "canonical" / "operator.jsonl"
    plan = _forbidden_record_state_plan(registry)

    with _with_signal_agent_root(fake_root):
        runtime = OperatorRuntime(
            registry,
            runs_dir=tmp_path / "runs",
            state_dir=tmp_path / "state",
            canonical_ledger_path=canonical_ledger,
        )
        result = runtime.execute(plan)

    entries = read_ledger_entries(canonical_ledger)
    assert result.status in {"rejected", "held"}
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_valid(entry)
    _assert_ref(entry, "operator_runtime", "operator_run")
    _assert_ref(entry, "operator_runtime", "transition_gate")
    assert entry["decision"] == "MANUAL_REVIEW_REQUIRED"
    assert entry["decision_reason"]
    assert _read_jsonl(fake_root / "data" / "state" / "artifact_registry.jsonl") == []


def test_duplicate_intake_rejection_appends_canonical_entry(tmp_path: Path) -> None:
    fake_root, registry = _setup_fake_root(tmp_path)
    plan = _parse_plan(registry, "append intake record canonical_duplicate_target")

    with _with_signal_agent_root(fake_root):
        first_runtime = OperatorRuntime(
            registry,
            runs_dir=tmp_path / "first_runs",
            state_dir=tmp_path / "first_state",
        )
        first = first_runtime.execute(plan)
        assert first.status == "ok"

        canonical_ledger = tmp_path / "canonical" / "operator_duplicate.jsonl"
        second_runtime = OperatorRuntime(
            registry,
            runs_dir=tmp_path / "second_runs",
            state_dir=tmp_path / "second_state",
            canonical_ledger_path=canonical_ledger,
        )
        duplicate = second_runtime.execute(plan)

    entries = read_ledger_entries(canonical_ledger)
    assert duplicate.status == "rejected"
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_valid(entry)
    assert entry["decision"] == "BLOCK_DUPLICATE"
    assert entry["decision_reason"] == "duplicate_record_detected"
    _assert_ref(entry, "operator_runtime", "operator_run")
    assert entry["subsystem_refs"][0]["transition_status"] == "rejected"


def test_operator_contract_violation_appends_canonical_entry(tmp_path: Path) -> None:
    fake_root, base_registry = _setup_fake_root(tmp_path)
    registry = _contract_violation_registry(base_registry)
    plan = _contract_violation_plan(registry)
    canonical_ledger = tmp_path / "canonical" / "operator_contract.jsonl"

    runtime = OperatorRuntime(
        registry,
        runs_dir=tmp_path / "runs",
        state_dir=tmp_path / "state",
        canonical_ledger_path=canonical_ledger,
    )
    result = runtime.execute(plan)

    entries = read_ledger_entries(canonical_ledger)
    assert result.status == "contract_violation"
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_valid(entry)
    _assert_ref(entry, "operator_runtime", "operator_run")
    assert entry["decision"] == "MANUAL_REVIEW_REQUIRED"
    assert entry["decision_reason"] == "non_write_workflow_with_mutating_tool"
    assert entry["subsystem_refs"][0]["tool_ids"] == ["dangerous_mutator"]
    assert not (fake_root / "data" / "state" / "artifact_registry.jsonl").exists()


def test_operator_deterministic_decision_id_stable_entry_id_varies(tmp_path: Path) -> None:
    fake_root, registry = _setup_fake_root(tmp_path)
    plan = _parse_plan(registry, "append intake record deterministic_operator")
    tool = ToolExecution(
        tool_id="intake_log_append",
        status="ok",
        summary="Appended intake record.",
        highlights=(),
        authority_paths=("data/intake/intake.jsonl",),
        notes=(),
        details={
            "_consistency_status": "observed_as_declared",
            "_tool_contract": {"verification_status": "boundary_observable"},
        },
    )
    result_a = OperatorRunResult(
        run_id="operator_a",
        command_text=plan.intent.command_text,
        status="ok",
        started_at="2026-06-14T00:00:00+00:00",
        completed_at="2026-06-14T00:00:00+00:00",
        intent_id=plan.intent.intent_id,
        workflow_id=plan.workflow.workflow_id if plan.workflow else None,
        target_workflow_id=plan.target_workflow.workflow_id if plan.target_workflow else None,
        summary="ok",
        highlights=(),
        authority_paths=(),
        notes=(),
        tool_results=(tool,),
        ledger_path=str(tmp_path / "operator_runs.jsonl"),
        run_record_path=str(tmp_path / "operator_a.json"),
    )
    result_b = OperatorRunResult(
        run_id="operator_b",
        command_text=plan.intent.command_text,
        status="ok",
        started_at="2026-06-14T00:00:01+00:00",
        completed_at="2026-06-14T00:00:01+00:00",
        intent_id=plan.intent.intent_id,
        workflow_id=plan.workflow.workflow_id if plan.workflow else None,
        target_workflow_id=plan.target_workflow.workflow_id if plan.target_workflow else None,
        summary="ok",
        highlights=(),
        authority_paths=(),
        notes=(),
        tool_results=(tool,),
        ledger_path=str(tmp_path / "operator_runs.jsonl"),
        run_record_path=str(tmp_path / "operator_b.json"),
    )

    entry_a = append_operator_decision_entry(
        tmp_path / "a.jsonl",
        plan=plan,
        result=result_a,
        timestamp="2026-06-14T00:00:00Z",
    )
    entry_b = append_operator_decision_entry(
        tmp_path / "b.jsonl",
        plan=plan,
        result=result_b,
        timestamp="2026-06-14T00:00:01Z",
    )

    assert entry_a["deterministic_decision_id"] == entry_b["deterministic_decision_id"]
    assert entry_a["ledger_entry_id"] != entry_b["ledger_entry_id"]


def test_temp_operator_canonical_adapter_does_not_modify_production_jsonl_ledgers(
    tmp_path: Path,
) -> None:
    before = _production_jsonl_snapshot()
    fake_root, registry = _setup_fake_root(tmp_path)
    canonical_ledger = tmp_path / "canonical" / "operator.jsonl"
    plan = _parse_plan(registry, "append intake record production_ledger_guard")

    with _with_signal_agent_root(fake_root):
        runtime = OperatorRuntime(
            registry,
            runs_dir=tmp_path / "runs",
            state_dir=tmp_path / "state",
            canonical_ledger_path=canonical_ledger,
        )
        result = runtime.execute(plan)

    assert result.status == "ok"
    assert read_ledger_entries(canonical_ledger)
    after = _production_jsonl_snapshot()
    assert after == before
